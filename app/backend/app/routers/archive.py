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
