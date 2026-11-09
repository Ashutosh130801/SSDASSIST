"""Monthly archive — admin only.

Once a case passes its close date it disappears from every live view (FOS, caller,
manager, head office). This router lets an ADMIN look back at any month: which products
ran, the product-wise numbers, cycle-wise breakdown, and per-staff performance for that
period. The raw case rows for a month come from GET /api/cases?period=YYYY-MM, and the
audit trail from GET /api/audit?period=YYYY-MM."""
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..deps import require_roles

router = APIRouter(prefix="/api/archive", tags=["archive"])


def _d(x) -> float:
    return float(x or 0)


@router.get("/periods")
def periods(db: Session = Depends(get_db),
            admin: models.User = Depends(require_roles("admin"))):
    """Every month that has cases, newest first, with open/closed counts."""
    today = date.today()
    rows = db.query(models.Case.period, models.Case.close_date).filter(
        models.Case.period.isnot(None), models.Case.removed.isnot(True)).all()
    agg = {}
    for period, cd in rows:
        a = agg.setdefault(period, {"period": period, "total": 0, "open": 0, "closed": 0})
        a["total"] += 1
        if cd is None or cd >= today:
            a["open"] += 1
        else:
            a["closed"] += 1
    return sorted(agg.values(), key=lambda x: x["period"], reverse=True)


@router.get("/summary")
def summary(period: str, product: str | None = None, bank: str | None = None,
            closing_type: str | None = None, cyc: int | None = None,
            db: Session = Depends(get_db),
            admin: models.User = Depends(require_roles("admin"))):
    """Full detail for one month: product-wise numbers, cycle breakdown, and per-staff
    performance. Optional filters narrow to a bank / product / closing type / cycle day."""
    today = date.today()
    q = db.query(models.Case).filter(models.Case.period == period,
                                     models.Case.removed.isnot(True))
    if bank:
        q = q.filter(models.Case.bank == bank)
    if product:
        q = q.filter(models.Case.product == product)
    if closing_type:
        q = q.filter(models.Case.closing_type == closing_type)
    cases = q.all()
    if cyc:
        cases = [c for c in cases if c.close_date and c.close_date.day == cyc]

    users = {u.id: u.name for u in db.query(models.User.id, models.User.name).all()}

    prod, callers, foses = {}, {}, {}
    tot = {"cases": 0, "open": 0, "closed": 0, "paid": 0,
           "target": 0.0, "received": 0.0, "pending": 0.0}
    cyc_break = {}
    for c in cases:
        paid = (c.paid_status or "").upper() == "PAID"
        is_open = c.close_date is None or c.close_date >= today
        tot["cases"] += 1
        tot["open"] += int(is_open)
        tot["closed"] += int(not is_open)
        tot["paid"] += int(paid)
        tot["target"] += _d(c.funding_amount) or _d(c.enr)
        tot["received"] += _d(c.received_amount)
        tot["pending"] += _d(c.pending_amount)

        key = (c.bank or "—", c.product or "—")
        p = prod.setdefault(key, {"bank": key[0], "product": key[1],
                                  "closing_type": c.closing_type, "cases": 0, "paid": 0,
                                  "target": 0.0, "received": 0.0, "pending": 0.0,
                                  "close_days": set()})
        p["cases"] += 1
        p["paid"] += int(paid)
        p["target"] += _d(c.funding_amount) or _d(c.enr)
        p["received"] += _d(c.received_amount)
        p["pending"] += _d(c.pending_amount)
        if c.close_date:
            p["close_days"].add(c.close_date.isoformat())

        # cycle-wise breakdown (day of month it closed)
        label = (c.close_date.isoformat() if c.close_date else "—") + f" · {c.closing_type or '—'}"
        cb = cyc_break.setdefault(label, {"closes": label, "cases": 0, "received": 0.0})
        cb["cases"] += 1
        cb["received"] += _d(c.received_amount)

        if c.assigned_caller_id:
            cc = callers.setdefault(c.assigned_caller_id, {
                "id": c.assigned_caller_id, "name": users.get(c.assigned_caller_id, "—"),
                "cases": 0, "paid": 0, "received": 0.0})
            cc["cases"] += 1; cc["paid"] += int(paid); cc["received"] += _d(c.received_amount)
        if c.assigned_fos_id:
            fc = foses.setdefault(c.assigned_fos_id, {
                "id": c.assigned_fos_id, "name": users.get(c.assigned_fos_id, "—"),
                "cases": 0, "paid": 0, "received": 0.0})
            fc["cases"] += 1; fc["paid"] += int(paid); fc["received"] += _d(c.received_amount)

    products = []
    for p in prod.values():
        p["close_days"] = sorted(p.pop("close_days"))
        products.append(p)
    products.sort(key=lambda x: (x["bank"], x["product"]))

    return {
        "period": period,
        "totals": tot,
        "products": products,
        "by_close": sorted(cyc_break.values(), key=lambda x: x["closes"]),
        "performance": {
            "callers": sorted(callers.values(), key=lambda x: x["received"], reverse=True),
            "fos": sorted(foses.values(), key=lambda x: x["received"], reverse=True),
        },
    }


@router.get("/cycle-report")
def cycle_report(period: str, db: Session = Depends(get_db),
                 admin: models.User = Depends(require_roles("admin"))):
    """Cycle-wise closing insight for a month: how many cases close on each cycle day,
    how much was recovered by then, and the split across closing types."""
    today = date.today()
    cases = db.query(models.Case).filter(models.Case.period == period,
                                         models.Case.removed.isnot(True)).all()
    days, by_type = {}, {}
    for c in cases:
        bt = by_type.setdefault(c.closing_type or "month_end",
                                {"closing_type": c.closing_type or "month_end",
                                 "cases": 0, "closed": 0, "received": 0.0})
        bt["cases"] += 1
        bt["closed"] += int(bool(c.close_date and c.close_date < today))
        bt["received"] += _d(c.received_amount)
        if (c.closing_type or "") == "cyc" and c.close_date:
            d = days.setdefault(c.close_date.day, {
                "day": c.close_date.day, "close_date": c.close_date.isoformat(),
                "cases": 0, "closed": 0, "open": 0, "received": 0.0, "target": 0.0, "products": set()})
            d["cases"] += 1
            is_closed = c.close_date < today
            d["closed"] += int(is_closed)
            d["open"] += int(not is_closed)
            d["received"] += _d(c.received_amount)
            d["target"] += _d(c.funding_amount) or _d(c.enr)
            if c.product:
                d["products"].add(c.product)
    day_rows = []
    for d in days.values():
        d["products"] = sorted(d.pop("products"))
        day_rows.append(d)
    day_rows.sort(key=lambda x: x["day"])
    return {
        "period": period,
        "cycle_days": day_rows,
        "by_type": sorted(by_type.values(), key=lambda x: x["closing_type"]),
    }


# ───────────────────────── 📦 one-month ZIP export ─────────────────────────
def _safe_name(s: str) -> str:
    import re as _re
    return _re.sub(r"[^A-Za-z0-9._-]+", "_", str(s or "NA")).strip("_")[:60] or "NA"


def _cellv(v):
    """Anything → a value Excel accepts (lists/sets joined, tz-aware times made local-naive)."""
    from datetime import date as _date, datetime as _dt, timedelta as _td, timezone as _tz
    from decimal import Decimal
    if v is None:
        return ""
    if isinstance(v, _dt):
        # stored timestamps are UTC (SQLite drops the zone) → show Indian time in the sheet
        return (v if v.tzinfo else v.replace(tzinfo=_tz.utc)).astimezone(_tz(_td(hours=5, minutes=30))).replace(tzinfo=None)
    if isinstance(v, (_date, int, float, Decimal, str, bool)):
        return v
    if isinstance(v, (list, tuple, set)):
        return ", ".join(str(x) for x in v)
    return str(v)


def _sheet_xlsx(sheets: list[tuple[str, list[str], list[list]]]) -> bytes:
    """Simple styled workbook: [(sheet title, headers, rows)]."""
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    wb = Workbook(); wb.remove(wb.active)
    for title, headers, rows in sheets:
        ws = wb.create_sheet(title[:31])
        ws.append(headers)
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="1E3A8A")
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        for r in rows:
            ws.append([_cellv(v) for v in r])
        for j, h in enumerate(headers, 1):
            w = max([len(str(h))] + [len(str(r[j - 1] or "")) for r in rows[:300]])
            ws.column_dimensions[get_column_letter(j)].width = max(9, min(45, w + 2))
        ws.freeze_panes = "A2"
        if rows:
            ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(rows) + 1}"
    buf = io.BytesIO(); wb.save(buf)
    return buf.getvalue()


def build_month_zip(db, period: str, fileobj, include_mis: bool = True) -> dict:
    """Write the whole month into `fileobj` as a ZIP. Returns counts for the audit line."""
    import zipfile
    from collections import defaultdict
    from datetime import datetime as _dt
    from .. import portfolio_export
    cases = (db.query(models.Case).filter(models.Case.period == period, models.Case.removed.isnot(True))
             .order_by(models.Case.bank, models.Case.product, models.Case.id).all())
    root = f"RecoverIQ_Archive_{period}/"
    users = {u.id: u for u in db.query(models.User).all()}
    uname = lambda i: (users[i].name + (f" ({users[i].emp_code})" if users[i].emp_code else "")) if i in users else ""
    ids = [c.id for c in cases]
    by_id = {c.id: c for c in cases}
    groups = defaultdict(list)
    for c in cases:
        groups[(c.bank or "NA", c.product or "NA")].append(c)
    problems = []
    with zipfile.ZipFile(fileobj, "w", zipfile.ZIP_DEFLATED) as z:
        # 1. summary (same numbers as the Archive screen)
        s = summary(period=period, db=db, admin=None)
        cyc = cycle_report(period=period, db=db, admin=None)
        t = s["totals"]
        sheets = [
            ("Totals", ["Metric", "Value"], [[k.replace("_", " ").title(), v] for k, v in t.items()]),
            ("Product-wise", ["Bank", "Product", "Closing type", "Closes on", "Cases", "Paid", "Target", "Recovered", "Pending", "Recovery %"],
             [[p["bank"], p["product"], p.get("closing_type"), ", ".join(p["close_days"]), p["cases"], p["paid"], round(p["target"], 2),
               round(p["received"], 2), round(p["pending"], 2),
               round(100 * p["received"] / p["target"], 1) if p["target"] else None] for p in s["products"]]),
            ("By close date", ["Closes", "Cases", "Recovered"], [[b["closes"], b["cases"], round(b["received"], 2)] for b in s["by_close"]]),
            ("Callers", ["Caller", "Cases", "Paid", "Recovered"], [[x["name"], x["cases"], x["paid"], round(x["received"], 2)] for x in s["performance"]["callers"]]),
            ("FOS", ["FOS", "Cases", "Paid", "Recovered"], [[x["name"], x["cases"], x["paid"], round(x["received"], 2)] for x in s["performance"]["fos"]]),
        ]
        if isinstance(cyc, dict):
            for key, val in cyc.items():
                if isinstance(val, list) and val and isinstance(val[0], dict):
                    hdr = list(val[0].keys())
                    sheets.append((("Cycle - " + key.replace("_", " ")).title()[:31], [h.replace("_", " ").title() for h in hdr], [[r.get(h) for h in hdr] for r in val]))
        z.writestr(root + "00_Month_Summary.xlsx", _sheet_xlsx(sheets))

        # 2. one full portfolio workbook (+ MIS pivot) per bank / product
        for (bank, prod), cs in sorted(groups.items()):
            name = f"{_safe_name(bank)}_{_safe_name(prod)}"
            try:
                z.writestr(f"{root}Portfolios/{name}.xlsx",
                           portfolio_export.build(db, cs, f"{bank} · {prod}", f"{period} · {len(cs)} cases · archive export"))
            except Exception as e:
                problems.append(f"Portfolio {bank}/{prod}: {e}")
            if include_mis:
                try:
                    from .. import mis_pivot
                    rows = mis_pivot.build_rows(db, cs)
                    z.writestr(f"{root}MIS/{name}_MIS_Pivot.xlsx",
                               mis_pivot.render_xlsx(rows, f"{bank} · {prod} · {period}", mis_pivot.targets_for(db, bank, prod, rows)))
                except Exception as e:
                    problems.append(f"MIS {bank}/{prod}: {e}")

        # 3. activity for these cases (calls, payments, visits, audit history)
        calls, visits, audits = [], [], []
        for i in range(0, len(ids), 800):
            chunk = ids[i:i + 800]
            calls += db.query(models.CallLog).filter(models.CallLog.case_id.in_(chunk)).all()
            visits += db.query(models.Visit).filter(models.Visit.case_id.in_(chunk)).all()
            audits += db.query(models.AuditLog).filter(models.AuditLog.case_id.in_(chunk)).all()
        cinfo = lambda cid: (by_id[cid].bank, by_id[cid].product, by_id[cid].account_no, by_id[cid].customer_name) if cid in by_id else ("", "", "", "")
        pay = [c for c in calls if (c.disposition or "").upper() in ("PAYMENT", "PAID")]
        oth = [c for c in calls if c not in pay]
        call_rows = lambda lst: [[c.created_at, *cinfo(c.case_id), c.case_id, uname(c.caller_id), c.disposition,
                                  float(c.ptp_amount or 0), c.ptp_date, c.note, c.recording_url] for c in sorted(lst, key=lambda x: x.created_at or _dt.min)]
        hdr = ["When", "Bank", "Product", "Account", "Customer", "Case id", "By", "Disposition", "Amount / PTP ₹", "PTP date", "Note", "Recording"]
        z.writestr(root + "Activity/Calls_and_PTPs.xlsx", _sheet_xlsx([("Calls", hdr, call_rows(oth))]))
        z.writestr(root + "Activity/Payments.xlsx", _sheet_xlsx([("Payments", hdr, call_rows(pay))]))
        z.writestr(root + "Activity/Field_visits.xlsx", _sheet_xlsx([("Visits",
            ["When", "Bank", "Product", "Account", "Customer", "Case id", "FOS", "Disposition", "Paid", "Collected ₹", "Address slot",
             "Distance from address (m)", "Trust", "Review", "GPS lat", "GPS lng", "Note", "Photo"],
            [[v.created_at, *cinfo(v.case_id), v.case_id, uname(v.officer_id), v.disposition, "Yes" if v.paid else "", float(v.amount_collected or 0),
              v.address_slot, round(v.distance_from_case_m) if v.distance_from_case_m is not None else None, v.trust_level, v.review_status,
              v.latitude, v.longitude, v.note, v.photo_path] for v in sorted(visits, key=lambda x: x.created_at or _dt.min)])]))
        z.writestr(root + "Activity/Case_history_audit.xlsx", _sheet_xlsx([("History",
            ["When", "Bank", "Product", "Account", "Customer", "Case id", "By", "Role", "Action", "Field", "Old", "New", "Detail"],
            [[a.at, *cinfo(a.case_id), a.case_id, a.actor_name, a.actor_role, a.action, a.field, a.old_value, a.new_value, a.detail]
             for a in sorted(audits, key=lambda x: x.at or _dt.min)])]))

        # 4. readme
        z.writestr(root + "README.txt", "\n".join([
            f"RecoverIQ monthly archive — {period}",
            f"Exported {_dt.now():%d-%b-%Y %H:%M}",
            f"Cases: {len(cases)} in {len(groups)} portfolio(s) · Calls: {len(oth)} · Payments: {len(pay)} · Visits: {len(visits)} · History rows: {len(audits)}",
            "",
            "00_Month_Summary.xlsx   totals, product-wise, by close date, caller & FOS performance, cycle report",
            "Portfolios/             full case data per bank / product (same as the portfolio Excel export)",
            "MIS/                    MIS pivot workbook per bank / product",
            "Activity/               every call, PTP, payment, field visit and case-history entry for the month's cases",
            "",
            "Contains customer personal data — store securely and share only with authorised people.",
            *([""] + ["Problems:"] + problems if problems else []),
        ]))
    return {"cases": len(cases), "portfolios": len(groups), "calls": len(oth), "payments": len(pay), "visits": len(visits), "problems": problems}


@router.get("/export.zip")
def export_month(period: str, include_mis: bool = True, db: Session = Depends(get_db),
                 admin: models.User = Depends(require_roles("admin"))):
    """📦 Everything for one month in a single ZIP: summary, every portfolio, MIS pivots, calls,
    payments, visits and case history."""
    import re as _re
    import tempfile
    from fastapi import HTTPException
    from fastapi.responses import StreamingResponse
    from .. import audit
    if not _re.fullmatch(r"\d{4}-\d{2}", period or ""):
        raise HTTPException(400, "period must be YYYY-MM")
    if not db.query(models.Case.id).filter(models.Case.period == period).first():
        raise HTTPException(404, "No cases for that month")
    tmp = tempfile.SpooledTemporaryFile(max_size=50 * 1024 * 1024)
    info = build_month_zip(db, period, tmp, include_mis)
    size = tmp.tell(); tmp.seek(0)
    audit.record(db, admin, "download", None, entity_type="download",
                 detail=f"Monthly archive ZIP {period}: {info['cases']} cases, {info['portfolios']} portfolios, {size // 1024} KB")
    db.commit()

    def stream():
        try:
            while True:
                chunk = tmp.read(1024 * 256)
                if not chunk:
                    break
                yield chunk
        finally:
            tmp.close()
    return StreamingResponse(stream(), media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="RecoverIQ_Archive_{period}.zip"',
                                      "Content-Length": str(size)})
