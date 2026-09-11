"""
One-time DPR cleanup — wipe ALL previous DPR uploads' effect, keep caller/FOS collections.

WHY: before the DPR snapshot-reconcile rework, every DPR upload ADDED its amount as dated
payment events. Re-uploading a DPR therefore double-counted, inflating FTD/MTD/Overall. This
script removes only the DPR-created payment events (identified by "DPR" in the note), rebuilds
each case's collected total from the REAL caller + field-visit collections that remain, and
recomputes status — leaving caller/FOS data exactly as it was.

AFTER running this, re-upload the CURRENT DPR file for each portfolio (per month). The new
snapshot-reconcile logic then sets each case to the DPR's total once, so MTD shows the current
DPR file's actual amount with no hallucinated double counts.

SCOPE (which months' DPR uploads to clean — by the DPR event's own date, IST):
    this   (default)  only THIS calendar month's DPR uploads — leaves last month untouched
    last              only LAST calendar month's DPR uploads
    all               every DPR upload ever (all months)

USAGE (from app/backend):
    python dpr_reset.py                 # DRY RUN, THIS month — shows what would change, changes nothing
    python dpr_reset.py --apply         # clean THIS month's DPR uploads (default scope)
    python dpr_reset.py last            # DRY RUN for last month
    python dpr_reset.py all --apply     # clean every month's DPR uploads
Prior months you don't clean stay exactly as they are (their DPR cash is preserved).
Safe to re-run; it only removes DPR-tagged events in the chosen window and recomputes from what's left.
"""
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal

sys.path.insert(0, ".")
from app.database import SessionLocal            # noqa: E402
from app import models, paymath                  # noqa: E402

APPLY = "--apply" in sys.argv
PAY = ("PAYMENT", "PAID")
IST = timezone(timedelta(hours=5, minutes=30))
SCOPE = next((a for a in sys.argv[1:] if a in ("this", "last", "all")), "this")


def _window_utc(scope: str):
    """UTC [start, end) for the chosen scope. 'all' -> (None, None)."""
    if scope == "all":
        return (None, None)
    now = datetime.now(IST)
    y, m = now.year, now.month
    if scope == "last":
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    ny, nm = (y, m + 1) if m < 12 else (y + 1, 1)
    start = datetime(y, m, 1, tzinfo=IST).astimezone(timezone.utc)
    end = datetime(ny, nm, 1, tzinfo=IST).astimezone(timezone.utc)
    return (start, end)


WIN_START, WIN_END = _window_utc(SCOPE)


def _in_window(dt) -> bool:
    if WIN_START is None:            # scope == all
        return True
    if dt is None:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return WIN_START <= dt < WIN_END


def _is_dpr(note: str) -> bool:
    return "dpr" in (note or "").lower()


def _is_autodebit(note: str) -> bool:
    n = (note or "").lower()
    return "auto-debit" in n or "auto debit" in n


def main() -> int:
    db = SessionLocal()
    try:
        cases = db.query(models.Case).all()
        by_case_calls = defaultdict(list)
        for cl in db.query(models.CallLog).filter(models.CallLog.disposition.in_(PAY)).all():
            by_case_calls[cl.case_id].append(cl)
        visit_sum = defaultdict(Decimal)
        for v in db.query(models.Visit).filter(models.Visit.amount_collected > 0).all():
            visit_sum[v.case_id] += Decimal(str(v.amount_collected or 0))

        stats = defaultdict(lambda: {"cases": 0, "dpr_events": 0,
                                     "recv_before": Decimal(0), "recv_after": Decimal(0)})
        tot_events = tot_cases = 0
        recv_before_all = recv_after_all = Decimal(0)

        for c in cases:
            calls = by_case_calls.get(c.id, [])
            # DPR cash events IN the chosen month-window → these get removed.
            dpr_kill = [e for e in calls if _is_dpr(e.note) and _in_window(e.created_at)]
            if not dpr_kill:
                # No DPR uploads to clean for this case in the chosen window → leave it alone
                # (this also preserves prior months' DPR cash, which lives in the kept events).
                continue
            # Everything we keep: caller/FOS events + DPR events from OTHER months (untouched).
            kept = [e for e in calls if e not in dpr_kill]
            baseline = sum((Decimal(str(e.ptp_amount or 0)) for e in kept), Decimal(0)) + visit_sum.get(c.id, Decimal(0))
            keep_autodebit = any(_is_autodebit(e.note) for e in kept)   # keep a mandate we still have

            key = f"{c.bank or '—'} / {c.product or '—'}"
            s = stats[key]
            s["cases"] += 1
            s["dpr_events"] += len(dpr_kill)
            s["recv_before"] += Decimal(str(c.received_amount or 0))
            recv_before_all += Decimal(str(c.received_amount or 0))
            tot_cases += 1
            tot_events += len(dpr_kill)

            if APPLY:
                for e in dpr_kill:
                    db.delete(e)
                c.received_amount = baseline
                if not keep_autodebit:
                    c.auto_debit = False
                c.paid_locked = False          # this window's DPR set it; re-upload re-confirms if still settled
                paymath.recompute(c)
            s["recv_after"] += baseline
            recv_after_all += baseline

        if APPLY:
            db.commit()

        mode = "APPLIED" if APPLY else "DRY RUN (nothing changed)"
        win = "ALL months" if WIN_START is None else \
            f"{WIN_START.astimezone(IST):%d-%b-%Y} .. {WIN_END.astimezone(IST):%d-%b-%Y}"
        print(f"\n=== DPR cleanup — scope: {SCOPE.upper()} ({win}) — {mode} ===")
        print(f"Cases affected: {tot_cases}   DPR events removed: {tot_events}")
        print(f"Received total  before: Rs {recv_before_all:,.0f}   after: Rs {recv_after_all:,.0f}"
              f"   (removed Rs {recv_before_all - recv_after_all:,.0f} of DPR-inflated cash)\n")
        print(f"{'Portfolio':<40}{'cases':>7}{'events':>8}{'before':>16}{'after':>16}")
        print("-" * 87)
        for key in sorted(stats):
            s = stats[key]
            print(f"{key[:39]:<40}{s['cases']:>7}{s['dpr_events']:>8}"
                  f"{float(s['recv_before']):>16,.0f}{float(s['recv_after']):>16,.0f}")
        if not APPLY:
            print("\nThis was a DRY RUN. Re-run with  --apply  to make the changes, then re-upload")
            print("the current DPR file for each portfolio so MTD reflects the actual DPR total.")
        else:
            print("\nDone. Now re-upload the CURRENT DPR file for each portfolio (per month).")
        return 0
    except Exception as e:
        db.rollback()
        print("ERROR:", e)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
