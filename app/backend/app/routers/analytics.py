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


def _scope(q, user):
    if user.role == "fos":
        return q.filter(models.Case.assigned_fos_id == user.id)
    if user.role == "telecaller":
        return q.filter(models.Case.assigned_caller_id == user.id)
    if user.role == "manager":
        from sqlalchemy import or_, select
        ids = select(models.User.id).where(models.User.branch == user.branch)
        return q.filter(or_(models.Case.branch == user.branch,
                            models.Case.assigned_fos_id.in_(ids), models.Case.assigned_caller_id.in_(ids)))
    return q


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    base = _scope(db.query(models.Case), user)

    total_cases = base.count()
    target = base.with_entities(func.coalesce(func.sum(models.Case.funding_amount), 0)).scalar()
    received = base.with_entities(func.coalesce(func.sum(models.Case.received_amount), 0)).scalar()
    pending = base.with_entities(func.coalesce(func.sum(models.Case.pending_amount), 0)).scalar()

    paid = _scope(db.query(models.Case), user).filter(models.Case.paid_status == "PAID").count()
    unpaid = _scope(db.query(models.Case), user).filter(models.Case.paid_status == "UNPAID").count()
    partial = _scope(db.query(models.Case), user).filter(models.Case.paid_status == "PARTIAL").count()

    target_f, received_f = _d(target), _d(received)
    recovery_rate = round((received_f / target_f * 100), 2) if target_f else 0.0

    # by bank
    bank_rows = (
        _scope(db.query(models.Case.bank,
                        func.count(models.Case.id),
                        func.coalesce(func.sum(models.Case.received_amount), 0),
                        func.coalesce(func.sum(models.Case.pending_amount), 0)), user)
        .group_by(models.Case.bank).all()
    )
    by_bank = [
        {"bank": b or "—", "cases": c, "received": _d(r), "pending": _d(p)}
        for b, c, r, p in bank_rows
    ]

    # by status
    status_rows = (
        _scope(db.query(models.Case.status, func.count(models.Case.id)), user)
        .group_by(models.Case.status).all()
    )
    by_status = [{"status": s or "—", "count": c} for s, c in status_rows]

    # by disposition
    disp_rows = (
        _scope(db.query(models.Case.disposition, func.count(models.Case.id)), user)
        .filter(models.Case.disposition.isnot(None))
        .group_by(models.Case.disposition).order_by(func.count(models.Case.id).desc()).limit(8).all()
    )
    by_disposition = [{"disposition": d, "count": c} for d, c in disp_rows]

    # collections trend (last 14 days from visits)
    since = datetime.now(timezone.utc) - timedelta(days=14)
    vq = db.query(
        func.date(models.Visit.created_at).label("d"),
        func.coalesce(func.sum(models.Visit.amount_collected), 0),
        func.count(models.Visit.id),
    ).filter(models.Visit.created_at >= since)
    if user.role == "fos":
        vq = vq.filter(models.Visit.officer_id == user.id)
    vq = vq.group_by("d").order_by("d")
    trend = [{"date": str(d), "collected": _d(a), "visits": v} for d, a, v in vq.all()]

    # FO leaderboard (admin only useful)
    fo_rows = (
        db.query(models.User.name,
                 func.count(models.Visit.id),
                 func.coalesce(func.sum(models.Visit.amount_collected), 0))
        .join(models.Visit, models.Visit.officer_id == models.User.id)
        .filter(models.User.role == "fos")
        .group_by(models.User.name)
        .order_by(func.coalesce(func.sum(models.Visit.amount_collected), 0).desc())
        .limit(10).all()
    )
    fo_leaderboard = [{"name": n, "visits": v, "collected": _d(a)} for n, v, a in fo_rows]

    return {
        "kpis": {
            "total_cases": total_cases,
            "target": target_f,
            "received": received_f,
            "pending": _d(pending),
            "recovery_rate": recovery_rate,
            "paid": paid, "unpaid": unpaid, "partial": partial,
        },
        "by_bank": by_bank,
        "by_status": by_status,
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
        "cases": db.query(models.Case).count(),
        "visits": db.query(models.Visit).count(),
        "calls": db.query(models.CallLog).count(),
        "payments": db.query(models.CallLog).filter(models.CallLog.disposition == "PAYMENT").count(),
        "location_pings": db.query(models.LocationPing).count(),
        "import_batches": db.query(models.ImportBatch).count(),
    }


@router.get("/activity")
def activity(kind: str = "all", limit: int = 100, db: Session = Depends(get_db),
             admin: models.User = Depends(require_roles("admin"))):
    """Recent records being stored/updated across the system — visits, calls and payments,
    each joined to its case and the staff member who created it."""
    users = {u.id: u.name for u in db.query(models.User).all()}
    items = []

    if kind in ("all", "visits"):
        rows = (db.query(models.Visit, models.Case.customer_name, models.Case.bank)
                .join(models.Case, models.Case.id == models.Visit.case_id)
                .order_by(models.Visit.created_at.desc()).limit(limit).all())
        gm = get_settings().geofence_metres
        for v, name, bank in rows:
            off = v.distance_from_case_m is not None and v.distance_from_case_m > gm
            items.append({
                "type": "visit", "at": v.created_at, "case_id": v.case_id, "customer": name, "bank": bank,
                "by": users.get(v.officer_id, ""), "amount": _d(v.amount_collected),
                "detail": (v.disposition or "") + (f" · paid ₹{_d(v.amount_collected):.0f}" if v.paid else "")
                          + (" · moved" if v.person_moved else "")
                          + (f" · ⚠ {int(v.distance_from_case_m)}m off-location" if off else ""),
                "lat": v.latitude, "lng": v.longitude, "photo": resolve_photo(v.photo_path), "note": v.note,
                "distance_m": v.distance_from_case_m, "off_location": off,
            })

    if kind in ("all", "calls", "payments"):
        q = db.query(models.CallLog, models.Case.customer_name, models.Case.bank).join(
            models.Case, models.Case.id == models.CallLog.case_id)
        if kind == "payments":
            q = q.filter(models.CallLog.disposition == "PAYMENT")
        rows = q.order_by(models.CallLog.created_at.desc()).limit(limit).all()
        for cl, name, bank in rows:
            items.append({
                "type": "payment" if cl.disposition == "PAYMENT" else "call",
                "at": cl.created_at, "case_id": cl.case_id, "customer": name, "bank": bank,
                "by": users.get(cl.caller_id, ""), "amount": _d(cl.ptp_amount),
                "detail": cl.disposition or "", "note": cl.note,
            })

    items.sort(key=lambda x: x["at"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return items[:limit]
