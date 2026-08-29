from decimal import Decimal
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..deps import get_current_user, require_roles
from ..config import get_settings
from ..storage import resolve as resolve_photo

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _d(v) -> float:
    return float(Decimal(str(v or 0)))


def _scope(q, user, branch=None, period=None):
    q = q.filter(models.Case.removed.isnot(True))     # soft-deleted cases never count
    if user.role == "fos":
        q = q.filter(models.Case.assigned_fos_id == user.id)
    elif user.role == "telecaller":
        q = q.filter(models.Case.assigned_caller_id == user.id)
    elif user.role == "manager":
        from sqlalchemy import or_, select
        ids = select(models.User.id).where(models.User.branch == user.branch)
        q = q.filter(or_(models.Case.branch == user.branch,
                         models.Case.assigned_fos_id.in_(ids), models.Case.assigned_caller_id.in_(ids)))
    # Admin (or manager) drilling into a specific branch card.
    if branch:
        q = q.filter(models.Case.branch == branch)
    # Month-wise separation (This month / Next month) so a person's stats aren't merged across months.
    if period:
        q = q.filter(models.Case.period == period)
    return q


@router.get("/dashboard")
def dashboard(branch: str | None = None, month_bucket: str | None = None,
              db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    # Month-wise separation so a person's stats/analytics aren't merged across months.
    from .cases import _current_period, _next_period
    period = _current_period() if month_bucket == "current" else _next_period() if month_bucket == "next" else None
    def sc(q):
        return _scope(q, user, branch, period=period)
    base = sc(db.query(models.Case))

    from .. import paymath
    total_cases = base.count()
    # Cash collection excludes below-settlement partials on NORM/STAB cases; those are surfaced
    # separately as `partial_payments`. Plain (no NORM/STAB) cases count all received as cash.
    cash = _d(base.with_entities(func.coalesce(func.sum(paymath.cash_expr()), 0)).scalar())
    partial_payments = _d(base.with_entities(func.coalesce(func.sum(paymath.partial_expr()), 0)).scalar())
    # ENR is the recovery base for credit-card/PL-BL data; fall back to funding for older loads.
    total_enr = _d(base.with_entities(func.coalesce(func.sum(models.Case.enr), 0)).scalar())
    paid_enr = _d(sc(db.query(models.Case))
                  .filter(models.Case.paid_status == "PAID")
                  .with_entities(func.coalesce(func.sum(models.Case.enr), 0)).scalar())
    funding = _d(base.with_entities(func.coalesce(func.sum(models.Case.funding_amount), 0)).scalar())

    paid = sc(db.query(models.Case)).filter(models.Case.paid_status == "PAID").count()
    unpaid = sc(db.query(models.Case)).filter(models.Case.paid_status == "UNPAID").count()
    partial = sc(db.query(models.Case)).filter(models.Case.paid_status == "PARTIAL").count()

    if total_enr > 0:                       # ENR-based (matches the MIS sheet)
        target_f = round(total_enr, 2)
        received_f = round(paid_enr, 2)
        pending_f = round(total_enr - paid_enr, 2)
        recovery_rate = round(paid_enr / total_enr * 100, 2)
    else:                                    # funding-based fallback
        target_f = funding
        received_f = cash
        pending_f = _d(base.with_entities(func.coalesce(func.sum(models.Case.pending_amount), 0)).scalar())
        recovery_rate = round((cash / funding * 100), 2) if funding else 0.0

    # by bank
    bank_rows = (
        sc(db.query(models.Case.bank,
                    func.count(models.Case.id),
                    func.coalesce(func.sum(models.Case.received_amount), 0),
                    func.coalesce(func.sum(models.Case.pending_amount), 0)))
        .group_by(models.Case.bank).all()
    )
    by_bank = [
        {"bank": b or "—", "cases": c, "received": _d(r), "pending": _d(p)}
        for b, c, r, p in bank_rows
    ]

    # by status
    status_rows = (
        sc(db.query(models.Case.status, func.count(models.Case.id)))
        .group_by(models.Case.status).all()
    )
    by_status = [{"status": s or "—", "count": c} for s, c in status_rows]

    # Collections Pipeline — a REAL funnel, not the raw `status` column (which stays "new" until a
    # case is actively worked and only flips to "allocated" on a paid→unpaid reversal, so it badly
    # under-counts allocation). Each case falls in exactly one stage, derived live:
    #   paid        → settled (paid_status PAID)
    #   ptp         → promised to pay (status ptp or a PTP disposition), not yet paid
    #   in_progress → contacted / visited but no PTP or payment yet
    #   allocated   → assigned to an FOS or caller but not touched yet
    #   new         → not assigned and not touched
    C = models.Case
    prows = sc(db.query(C.paid_status, C.status, C.disposition, C.last_contacted_at,
                        C.visited, C.assigned_fos_id, C.assigned_caller_id)).all()
    pipe = {"new": 0, "allocated": 0, "in_progress": 0, "ptp": 0, "paid": 0}
    for ps, st, dp, lc, vis, fid, cid in prows:
        if (ps or "").upper() == "PAID":
            pipe["paid"] += 1
        elif st == "ptp" or "ptp" in (dp or "").lower():
            pipe["ptp"] += 1
        elif lc is not None or st == "in_progress" or vis is True:
            pipe["in_progress"] += 1
        elif fid is not None or cid is not None:
            pipe["allocated"] += 1
        else:
            pipe["new"] += 1
    pipeline = [{"key": k, "count": pipe[k]} for k in ("new", "allocated", "in_progress", "ptp", "paid")]

    # by disposition
    disp_rows = (
        sc(db.query(models.Case.disposition, func.count(models.Case.id)))
        .filter(models.Case.disposition.isnot(None))
        .group_by(models.Case.disposition).order_by(func.count(models.Case.id).desc()).limit(8).all()
    )
    by_disposition = [{"disposition": d, "count": c} for d, c in disp_rows]

    # Collections trend (last 14 days) — ALL money in: field-visit collections + call-log
    # collections (caller payments, head-office mark-paid, DPR — logged as PAYMENT/PAID), so the
    # trend reflects every payment path, not just visits.
    since = datetime.now(timezone.utc) - timedelta(days=14)
    from sqlalchemy import select as _select
    day_map: dict[str, dict] = {}
    vq = db.query(
        func.date(models.Visit.created_at).label("d"),
        func.coalesce(func.sum(models.Visit.amount_collected), 0),
        func.count(models.Visit.id),
    ).filter(models.Visit.created_at >= since)
    if user.role == "fos":
        vq = vq.filter(models.Visit.officer_id == user.id)
    if branch:
        vq = vq.filter(models.Visit.officer_id.in_(
            _select(models.User.id).where(models.User.branch == branch)))
    for d, a, v in vq.group_by("d").all():
        day_map.setdefault(str(d), {"collected": 0.0, "visits": 0})
        day_map[str(d)]["collected"] += _d(a); day_map[str(d)]["visits"] += int(v or 0)
    cq = db.query(
        func.date(models.CallLog.created_at).label("d"),
        func.coalesce(func.sum(models.CallLog.ptp_amount), 0),
    ).filter(models.CallLog.created_at >= since, models.CallLog.disposition.in_(("PAYMENT", "PAID")))
    if user.role == "fos":
        cq = cq.filter(models.CallLog.caller_id == user.id)
    if branch:
        cq = cq.filter(models.CallLog.caller_id.in_(
            _select(models.User.id).where(models.User.branch == branch)))
    for d, a in cq.group_by("d").all():
        day_map.setdefault(str(d), {"collected": 0.0, "visits": 0})
        day_map[str(d)]["collected"] += _d(a)
    trend = [{"date": k, "collected": round(v["collected"], 2), "visits": v["visits"]}
             for k, v in sorted(day_map.items())]

    # FO leaderboard (admin-only useful) — rank by EVERY rupee attributed to the agent, not just
    # field-visit cash: visit collections + any payment logged against them (mark-paid, DPR,
    # caller payment) via CallLog credited to their id. Otherwise agents whose recoveries land
    # through the office/DPR path read ₹0 and the board looks empty.
    fq = db.query(models.User.id, models.User.name).filter(models.User.role == "fos")
    if branch:
        fq = fq.filter(models.User.branch == branch)
    fos_users = fq.all()
    fos_ids = [u.id for u in fos_users]
    coll: dict[int, float] = {i: 0.0 for i in fos_ids}
    visit_ct: dict[int, int] = {i: 0 for i in fos_ids}
    if fos_ids:
        for oid, ct, amt in (
            db.query(models.Visit.officer_id, func.count(models.Visit.id),
                     func.coalesce(func.sum(models.Visit.amount_collected), 0))
            .filter(models.Visit.officer_id.in_(fos_ids))
            .group_by(models.Visit.officer_id).all()
        ):
            coll[oid] = coll.get(oid, 0.0) + _d(amt)
            visit_ct[oid] = int(ct or 0)
        for cid, amt in (
            db.query(models.CallLog.caller_id,
                     func.coalesce(func.sum(models.CallLog.ptp_amount), 0))
            .filter(models.CallLog.caller_id.in_(fos_ids),
                    models.CallLog.disposition.in_(("PAYMENT", "PAID")))
            .group_by(models.CallLog.caller_id).all()
        ):
            coll[cid] = coll.get(cid, 0.0) + _d(amt)
    fo_leaderboard = sorted(
        [{"name": u.name, "visits": visit_ct.get(u.id, 0), "collected": round(coll.get(u.id, 0.0), 2)}
         for u in fos_users],
        key=lambda x: x["collected"], reverse=True)[:10]

    return {
        "kpis": {
            "total_cases": total_cases,
            "target": target_f,
            "received": received_f,
            "pending": pending_f,
            "recovery_rate": recovery_rate,
            # Resolution % = share of a person's cases that are settled (PAID) — count-based,
            # so a caller sees "how many of my cases are done" independent of ₹ amounts.
            "resolution_rate": round(paid / total_cases * 100, 2) if total_cases else 0.0,
            "cash_collected": cash,
            "partial_payments": partial_payments,   # below-settlement money on NORM/STAB cases
            "paid": paid, "unpaid": unpaid, "partial": partial,
        },
        "by_bank": by_bank,
        "by_status": by_status,
        "pipeline": pipeline,
        "by_disposition": by_disposition,
        "trend": trend,
        "fo_leaderboard": fo_leaderboard,
    }


@router.get("/summary")
def db_summary(db: Session = Depends(get_db), admin: models.User = Depends(require_roles("admin"))):
    """Row counts for every stored record type — a quick 'what's in the database' view."""
    role_rows = db.query(models.User.role, func.count(models.User.id)).group_by(models.User.role).all()
    return {
        "users_total": db.query(models.User).count(),
        "users_by_role": {r: c for r, c in role_rows},
        "cases": db.query(models.Case).filter(models.Case.removed.isnot(True)).count(),
        "visits": db.query(models.Visit).count(),
        "calls": db.query(models.CallLog).count(),
        "payments": db.query(models.CallLog).filter(models.CallLog.disposition.in_(("PAYMENT", "PAID"))).count(),
        "location_pings": db.query(models.LocationPing).count(),
        "import_batches": db.query(models.ImportBatch).count(),
    }


@router.get("/activity/filters")
def activity_filters(db: Session = Depends(get_db),
                     viewer: models.User = Depends(require_roles("admin", "manager", "headoffice"))):
    """Distinct values to populate the Activity filters (scoped for managers)."""
    cq = db.query(models.Case)
    uq = db.query(models.User).filter(models.User.role.in_(("fos", "telecaller")))
    if viewer.role == "manager":
        cq = cq.filter(models.Case.branch == viewer.branch)
        uq = uq.filter(models.User.branch == viewer.branch)

    banks = sorted({c.bank for c in cq.with_entities(models.Case.bank).distinct() if c.bank})
    branches = sorted({c.branch for c in cq.with_entities(models.Case.branch).distinct() if c.branch})
    products = sorted({c.product for c in cq.with_entities(models.Case.product).distinct() if c.product})
    areas = sorted({c.team for c in cq.with_entities(models.Case.team).distinct() if c.team})
    employees = [{"id": u.id, "name": u.name, "role": u.role} for u in uq.order_by(models.User.name).all()]
    return {"banks": banks, "branches": branches, "products": products, "areas": areas, "employees": employees}


@router.get("/activity")
def activity(kind: str = "all", limit: int = 150,
             bank: str | None = None, branch: str | None = None, product: str | None = None,
             area: str | None = None, emp: int | None = None,
             db: Session = Depends(get_db),
             viewer: models.User = Depends(require_roles("admin", "manager"))):
    """Recent records across the system — visits, calls and payments — with filters
    for bank / branch / product / area / employee. Managers see only their branch."""
    users = {u.id: u.name for u in db.query(models.User).all()}
    items = []
    mbranch = viewer.branch if viewer.role == "manager" else None

    def apply_case_filters(q):
        q = q.filter(models.Case.removed.isnot(True))
        if bank:
            q = q.filter(models.Case.bank == bank)
        if product:
            q = q.filter(models.Case.product == product)
        if area:
            q = q.filter(models.Case.team == area)
        eff_branch = mbranch or branch
        if eff_branch:
            q = q.filter(models.Case.branch == eff_branch)
        return q

    if kind in ("all", "visits"):
        q = (db.query(models.Visit, models.Case.customer_name, models.Case.bank,
                      models.Case.branch, models.Case.product, models.Case.team)
             .join(models.Case, models.Case.id == models.Visit.case_id))
        q = apply_case_filters(q)
        if emp:
            q = q.filter(models.Visit.officer_id == emp)
        gm = get_settings().geofence_metres
        for v, name, bk, br, pr, tm in q.order_by(models.Visit.created_at.desc()).limit(limit).all():
            off = v.distance_from_case_m is not None and v.distance_from_case_m > gm
            items.append({
                "type": "visit", "at": v.created_at, "case_id": v.case_id, "customer": name,
                "bank": bk, "branch": br, "product": pr, "area": tm,
                "by": users.get(v.officer_id, ""), "amount": _d(v.amount_collected),
                "detail": (v.disposition or "") + (f" · paid ₹{_d(v.amount_collected):.0f}" if v.paid else "")
                          + (" · moved" if v.person_moved else "")
                          + (f" · ⚠ {int(v.distance_from_case_m)}m off-location" if off else ""),
                "lat": v.latitude, "lng": v.longitude, "photo": resolve_photo(v.photo_path), "note": v.note,
                "distance_m": v.distance_from_case_m, "off_location": off,
            })

    if kind in ("all", "calls", "payments"):
        q = (db.query(models.CallLog, models.Case.customer_name, models.Case.bank,
                      models.Case.branch, models.Case.product, models.Case.team)
             .join(models.Case, models.Case.id == models.CallLog.case_id))
        q = apply_case_filters(q)
        if kind == "payments":
            q = q.filter(models.CallLog.disposition.in_(("PAYMENT", "PAID")))
        if emp:
            q = q.filter(models.CallLog.caller_id == emp)
        for cl, name, bk, br, pr, tm in q.order_by(models.CallLog.created_at.desc()).limit(limit).all():
            items.append({
                "type": "payment" if (cl.disposition or "") in ("PAYMENT", "PAID") else "call",
                "at": cl.created_at, "case_id": cl.case_id, "customer": name,
                "bank": bk, "branch": br, "product": pr, "area": tm,
                "by": users.get(cl.caller_id, ""), "amount": _d(cl.ptp_amount),
                "detail": cl.disposition or "", "note": cl.note,
            })

    items.sort(key=lambda x: x["at"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return items[:limit]
