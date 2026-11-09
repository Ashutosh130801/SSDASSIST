"""
One-off check: find cases whose collections were booked twice (DPR / upload / caller + FOS).

It looks at every non-removed case and flags three patterns:

  A  OVER-BOOKED     collection entries (call PAYMENT/PAID + visit collections) add up to MORE
                     than the case's Received amount → FTD/MTD/MIS show too much.
                     --fix removes the extra entries (repeat DPR/upload entries first); if no exact
                     set of entries matches, it adds one correction entry for the excess.
  B  REPEAT DPR      the same amount was booked by DPR/upload two or more times → Received itself
                     is probably doubled (e.g. 40,000 when the bank says 20,000).
                     Not auto-fixed: re-upload the CURRENT DPR for that month — the DPR now lowers
                     Received to the bank's figure and books the matching minus entry.
  C  CALLER + FOS    the caller and the FOS each logged the same amount within 7 days → probably
                     the same payment recorded twice. Not auto-fixed: verify, then re-upload DPR.
  (also) RECEIVED > OUTSTANDING — shown as a hint on B/C rows.

Writes an Excel report: double_collections_report_<date>.xlsx (same folder).

USAGE (from app/backend, same DATABASE_URL as the app):
    python check_double_collections.py            # report only, changes nothing
    python check_double_collections.py --fix      # also correct pattern A
    python check_double_collections.py --month 2026-10   # only cases of that portfolio month
"""
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from itertools import combinations

sys.path.insert(0, ".")
from app.database import SessionLocal            # noqa: E402
from app import models                            # noqa: E402

FIX = "--fix" in sys.argv
MONTH = sys.argv[sys.argv.index("--month") + 1] if "--month" in sys.argv else None
PAY = ("PAYMENT", "PAID")
TOL = Decimal("1")
IST = timezone(timedelta(hours=5, minutes=30))
CORR_NOTE = "Correction: duplicate collection removed (check_double_collections)"


def D(v):
    try:
        return Decimal(str(v or 0))
    except Exception:
        return Decimal(0)


def _is_bulk(note):
    n = (note or "").lower()
    return "dpr" in n or "upload" in n or "import" in n or "backfill" in n


def _dt(x):
    if x is None:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    return x if x.tzinfo else x.replace(tzinfo=timezone.utc)


def _ist(x):
    return _dt(x).astimezone(IST).strftime("%d-%b-%Y %H:%M") if x else ""


def _pick_removals(events, excess):
    """Newest-first set of positive bulk entries whose amounts add up exactly to `excess`.
    Only entries whose amount also appears in an EARLIER entry (a true repeat) are candidates."""
    pos = sorted([e for e in events if e["kind"] == "call" and e["bulk"] and e["amt"] > 0],
                 key=lambda e: _dt(e["at"]), reverse=True)
    repeats = []
    for i, e in enumerate(pos):
        if any(abs(o["amt"] - e["amt"]) <= TOL for o in pos[i + 1:]):
            repeats.append(e)
    for pool in (repeats, pos):
        pool = pool[:12]
        for r in range(1, len(pool) + 1):
            for combo in combinations(pool, r):
                if abs(sum(e["amt"] for e in combo) - excess) <= TOL:
                    return list(combo)
    return None


def main():
    db = SessionLocal()
    try:
        q = db.query(models.Case).filter(models.Case.removed.isnot(True))
        if MONTH:
            q = q.filter(models.Case.period == MONTH)
        cases = {c.id: c for c in q.all()}
        users = {u.id: u for u in db.query(models.User).all()}

        ev = defaultdict(list)
        for cl in db.query(models.CallLog).filter(models.CallLog.disposition.in_(PAY)).all():
            if cl.case_id in cases:
                ev[cl.case_id].append({"kind": "call", "obj": cl, "amt": D(cl.ptp_amount), "at": cl.created_at,
                                       "note": cl.note or "", "bulk": _is_bulk(cl.note), "by": cl.caller_id})
        for v in db.query(models.Visit).filter(models.Visit.amount_collected != 0).all():
            if v.case_id in cases:
                ev[v.case_id].append({"kind": "visit", "obj": v, "amt": D(v.amount_collected), "at": v.created_at,
                                      "note": "Field visit collection", "bulk": False, "by": v.officer_id})

        rows = []          # report rows
        fixed_cases = removed_n = corr_n = 0
        fixed_amt = Decimal(0)
        for cid, c in cases.items():
            evs = ev.get(cid, [])
            recv = D(c.received_amount)
            booked = sum((e["amt"] for e in evs), Decimal(0))
            base = D(c.total_outstanding)
            flags, action = [], ""

            # A — entries add up to more than Received
            excess = booked - recv
            if excess > TOL:
                flags.append("A over-booked")
                if FIX:
                    kill = _pick_removals(evs, excess)
                    if kill:
                        for e in kill:
                            db.delete(e["obj"])
                        removed_n += len(kill)
                        action = f"removed {len(kill)} repeat entr{'y' if len(kill) == 1 else 'ies'}"
                    else:
                        last = max(evs, key=lambda e: _dt(e["at"]))
                        db.add(models.CallLog(case_id=cid, caller_id=last["by"] or (c.assigned_caller_id or c.assigned_fos_id),
                                              disposition="PAYMENT", ptp_amount=-excess, note=CORR_NOTE,
                                              created_at=last["at"]))
                        corr_n += 1
                        action = f"added correction −{excess:,.0f}"
                    fixed_cases += 1
                    fixed_amt += excess
                else:
                    action = "run with --fix"

            # B — same amount booked by DPR/upload more than once (Received likely doubled)
            bulk_amts = defaultdict(int)
            for e in evs:
                if e["kind"] == "call" and e["bulk"] and e["amt"] > 0:
                    bulk_amts[e["amt"].quantize(Decimal("1"))] += 1
            rep = {a: n for a, n in bulk_amts.items() if n >= 2}
            if rep:
                flags.append("B repeat DPR")
            # C — caller and FOS logged the same amount within 7 days
            calls = [e for e in evs if e["kind"] == "call" and not e["bulk"] and e["amt"] > 0]
            visits = [e for e in evs if e["kind"] == "visit" and e["amt"] > 0]
            if any(abs(a["amt"] - b["amt"]) <= TOL and abs(_dt(a["at"]) - _dt(b["at"])) <= timedelta(days=7)
                   for a in calls for b in visits):
                flags.append("C caller+FOS")
            if not flags:
                continue
            if ("B repeat DPR" in flags or "C caller+FOS" in flags) and not action:
                action = "verify, then re-upload current DPR"
            hint = "received > outstanding" if base > 0 and recv > base + TOL else ""
            rows.append({
                "case": c, "flags": ", ".join(flags), "recv": recv, "booked": booked,
                "excess": excess if excess > TOL else Decimal(0),
                "repeat": "; ".join(f"₹{a:,.0f} ×{n}" for a, n in rep.items()),
                "hint": hint, "action": action,
                "entries": " | ".join(f"{_ist(e['at'])} ₹{e['amt']:,.0f} "
                                      f"{'visit' if e['kind'] == 'visit' else ('DPR/upload' if e['bulk'] else 'call')}"
                                      f" ({(users.get(e['by']).name if users.get(e['by']) else '-')})"
                                      for e in sorted(evs, key=lambda e: _dt(e["at"]))),
            })

        if FIX:
            db.commit()

        # ---------------- console summary
        cnt = defaultdict(int)
        for r in rows:
            for f in r["flags"].split(", "):
                cnt[f[0]] += 1
        print(f"\n=== Double-collection check{' — month ' + MONTH if MONTH else ''} — "
              f"{'FIX APPLIED' if FIX else 'REPORT ONLY (nothing changed)'} ===")
        print(f"Cases checked: {len(cases)}   Flagged: {len(rows)}")
        print(f"  A over-booked (reports > Received): {cnt['A']}")
        print(f"  B same amount booked by DPR/upload twice: {cnt['B']}")
        print(f"  C caller + FOS same amount within 7 days: {cnt['C']}")
        if FIX:
            print(f"Fixed {fixed_cases} case(s), ₹{fixed_amt:,.0f} of extra entries: "
                  f"{removed_n} repeat entries removed, {corr_n} correction entries added.")

        out = _write_xlsx(rows)
        print(f"Report: {out}")
        if cnt["B"] or cnt["C"]:
            print("For B / C rows: check the case, then re-upload the CURRENT DPR for that month —"
                  " it resets Received to the bank's figure.")
        return 0
    except Exception as e:
        db.rollback()
        print("ERROR:", e)
        raise
    finally:
        db.close()


def _write_xlsx(rows):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
    wb = Workbook()
    ws = wb.active
    ws.title = "Flagged cases"
    head = ["Case ID", "Bank", "Product", "Month", "Account / Loan", "Card", "Customer",
            "Pattern", "Received ₹", "Entries total ₹", "Extra in reports ₹", "Repeated DPR amounts",
            "Hint", "Action", "All collection entries"]
    ws.append(head)
    hf = PatternFill("solid", fgColor="1F4E79")
    thin = Side(style="thin", color="BFBFBF")
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = hf
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    fills = {"A": "FCE4D6", "B": "FFF2CC", "C": "DDEBF7"}
    for r in sorted(rows, key=lambda r: (r["flags"], -(r["excess"] or 0))):
        c = r["case"]
        ws.append([c.id, c.bank, c.product, c.period, c.account_no, c.card_no, c.customer_name,
                   r["flags"], float(r["recv"]), float(r["booked"]), float(r["excess"]), r["repeat"],
                   r["hint"], r["action"], r["entries"]])
        fill = PatternFill("solid", fgColor=fills[r["flags"][0]])
        for cell in ws[ws.max_row]:
            cell.fill = fill
            cell.border = Border(top=thin, bottom=thin, left=thin, right=thin)
            cell.alignment = Alignment(vertical="top", wrap_text=cell.column == 15)
        for col in (9, 10, 11):
            ws.cell(ws.max_row, col).number_format = "#,##0"
    widths = [9, 10, 12, 9, 20, 20, 24, 22, 12, 14, 14, 20, 20, 30, 90]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    g = wb.create_sheet("How to read")
    for line in [
        ["Pattern", "Meaning", "What to do"],
        ["A over-booked", "Collection entries add up to more than Received, so FTD/MTD/MIS show too much.",
         "Run the script with --fix (removes the repeated entries)."],
        ["B repeat DPR", "The same amount was booked by DPR/upload two or more times — Received is probably doubled.",
         "Check against the bank's DPR, then re-upload the CURRENT DPR for that month."],
        ["C caller+FOS", "Caller and FOS each logged the same amount within 7 days — likely one payment logged twice.",
         "Confirm with the team, then re-upload the CURRENT DPR for that month."],
    ]:
        g.append(line)
    for cell in g[1]:
        cell.font = Font(bold=True)
    g.column_dimensions["A"].width = 18
    g.column_dimensions["B"].width = 80
    g.column_dimensions["C"].width = 60
    name = f"double_collections_report_{datetime.now(IST):%Y%m%d_%H%M}.xlsx"
    wb.save(name)
    return name


if __name__ == "__main__":
    raise SystemExit(main())
