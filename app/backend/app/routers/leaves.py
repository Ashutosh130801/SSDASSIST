from datetime import datetime, timezone, timedelta, date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user, require_roles
from ..leave_policy import effective_days
from .. import audit

router = APIRouter(prefix="/api/leaves", tags=["leaves"])

IST = timezone(timedelta(hours=5, minutes=30))
LEAVE_TYPES = ["Casual", "Sick", "Earned", "Unpaid"]
DEFAULT_ALLOWANCE = {"Casual": 12, "Sick": 12, "Earned": 15, "Unpaid": 0}


def _today():
    return datetime.now(IST).date()


def _names(db):
    return {u.id: (u.name, u.branch, u.role) for u in db.query(models.User).all()}


def _eff_days(lv):
    """Effective leave days: a half-day counts 0.5, otherwise the calendar-day count."""
    return effective_days(lv)


def _overlap(db, uid, start, end, exclude=None):
    q = db.query(models.Leave).filter(models.Leave.user_id == uid,
        models.Leave.status.in_(("pending", "approved")),
        models.Leave.start_date <= end, models.Leave.end_date >= start)
    if exclude is not None:
        q = q.filter(models.Leave.id != exclude)
    return q.first()


def _changed():
    from .realtime import notify_data_changed
    notify_data_changed()


def _year_totals(db, uids, year):
    start, end = date(year, 1, 1), date(year, 12, 31)
    totals = {}
    for lv in db.query(models.Leave).filter(models.Leave.user_id.in_(uids),
            models.Leave.status.in_(("approved", "pending")),
            models.Leave.start_date <= end, models.Leave.end_date >= start).all():
        entry = totals.setdefault(lv.user_id, {}).setdefault(lv.leave_type, {"approved": 0.0, "pending": 0.0})
        entry[lv.status] += effective_days(lv, start, end)
    return totals


def _out(lv, names):
    d = schemas.LeaveOut.model_validate(lv)
    d.half_day = bool(lv.half_day)
    d.days_effective = _eff_days(lv)
    nm = names.get(lv.user_id, (None, None, None))
    d.user_name, d.user_branch, d.user_role = nm[0], nm[1], nm[2]
    if lv.approver_id:
        d.approver_name = names.get(lv.approver_id, (None, None, None))[0]
    return d


def _can_manage(actor, target_user):
    if not target_user:
        return False
    if actor.id == target_user.id:
        return False                      # nobody approves their own leave
    # HEAD OFFICE's leave can be approved by HR (or an Administrator).
    if target_user.role == "headoffice":
        return actor.role in ("admin", "hr")
    # An HR's own leave is still approved by an Administrator only.
    if target_user.role == "hr":
        return actor.role == "admin"
    # HR and head office approve everyone else's leave (any staff, any branch). Admin too.
    if actor.role in ("admin", "hr", "headoffice"):
        return True
    if actor.role == "manager":
        return target_user.branch == actor.branch and target_user.role not in ("admin", "manager")
    return False


@router.post("", response_model=schemas.LeaveOut)
def apply_leave(body: schemas.LeaveCreate, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)):
    if body.leave_type not in LEAVE_TYPES:
        raise HTTPException(status_code=400, detail=f"leave_type must be one of {LEAVE_TYPES}")
    if body.end_date < body.start_date:
        raise HTTPException(status_code=400, detail="end date must be on or after start date")
    half = bool(getattr(body, "half_day", False))
    if half and body.start_date != body.end_date:
        raise HTTPException(status_code=400, detail="A half-day leave must be for a single date (From = To).")
    db.query(models.User).filter_by(id=user.id).with_for_update().first()
    if _overlap(db, user.id, body.start_date, body.end_date):
        raise HTTPException(409, "A pending or approved leave already covers this date range.")
    days = (body.end_date - body.start_date).days + 1
    lv = models.Leave(user_id=user.id, leave_type=body.leave_type, start_date=body.start_date,
                      end_date=body.end_date, days=days, half_day=half, reason=body.reason, status="pending")
    db.add(lv)
    audit.record(db, user, "leave_requested", entity_type="leave", target_user_id=user.id,
                 detail=f"{body.leave_type}: {body.start_date} to {body.end_date}, {0.5 if half else days} day(s)")
    db.commit()
    db.refresh(lv)
    _changed()
    return _out(lv, _names(db))


@router.get("", response_model=list[schemas.LeaveOut])
def list_leaves(status: str | None = None, scope: str = "auto",
                leave_type: str | None = None, from_date: date | None = None,
                to_date: date | None = None, q: str | None = None,
                role: str | None = None,
                db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)):
    """scope=mine -> only my leaves; scope=team -> branch/all (admin/manager);
    scope=auto -> mine for staff, team for admin/manager.
    Optional history filters: status, leave_type, from_date/to_date (overlap), q (name/branch/type/reason)."""
    query = db.query(models.Leave)
    want_team = scope == "team" or (scope == "auto" and user.role in ("admin", "manager", "hr", "headoffice"))
    if not want_team or user.role not in ("admin", "manager", "hr", "headoffice"):
        query = query.filter(models.Leave.user_id == user.id)
    elif user.role == "manager":
        from sqlalchemy import select
        ids = select(models.User.id).where(models.User.branch == user.branch)
        query = query.filter(models.Leave.user_id.in_(ids))
    # admin/hr/headoffice team -> all
    if status and status != "all":
        query = query.filter(models.Leave.status == status)
    if leave_type and leave_type != "all":
        query = query.filter(models.Leave.leave_type == leave_type)
    if from_date:                       # overlaps the window [from_date, to_date]
        query = query.filter(models.Leave.end_date >= from_date)
    if to_date:
        query = query.filter(models.Leave.start_date <= to_date)
    if role and role != "all":                       # filter by the applicant's role
        from sqlalchemy import select as _select
        query = query.filter(models.Leave.user_id.in_(
            _select(models.User.id).where(models.User.role == role)))
    rows = query.order_by(models.Leave.start_date.desc(), models.Leave.created_at.desc()).all()
    names = _names(db)
    out = [_out(lv, names) for lv in rows]
    if q:
        s = q.lower().strip()
        def _hit(d):
            return any(s in (str(getattr(d, k, "") or "")).lower()
                       for k in ("user_name", "user_branch", "leave_type", "reason", "status"))
        out = [d for d in out if _hit(d)]
    return out


@router.get("/balance")
def balance(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    year = _today().year
    totals = _year_totals(db, [user.id], year).get(user.id, {})
    used = {t: v["approved"] for t, v in totals.items()}
    pending = {t: v["pending"] for t, v in totals.items()}
    out = []
    for t in LEAVE_TYPES:
        allow = DEFAULT_ALLOWANCE.get(t, 0)
        u = used.get(t, 0)
        out.append({"type": t, "allowance": allow, "used": u, "pending": pending.get(t, 0),
                    "remaining": (allow - u) if t != "Unpaid" else None})
    return out


@router.get("/balances")
def balances(role: str | None = None, q: str | None = None, year: int | None = None,
             db: Session = Depends(get_db),
             actor: models.User = Depends(require_roles("admin", "manager", "hr", "headoffice"))):
    """Per-EMPLOYEE leave summary for HR/HO/admin (manager = own branch): days taken (approved),
    pending, and remaining per type + overall. Filter by role / name search / year."""
    yr = year or _today().year
    jan1, dec31 = date(yr, 1, 1), date(yr, 12, 31)
    users = db.query(models.User).filter(models.User.is_active == True)
    if actor.role == "manager":
        users = users.filter(models.User.branch == actor.branch)
    if role and role != "all":
        users = users.filter(models.User.role == role)
    users = users.order_by(models.User.name).all()
    uids = [u.id for u in users]
    # Sum approved/pending days per (user, type) within the year.
    agg = _year_totals(db, uids, yr) if uids else {}
    out = []
    for u in users:
        per = agg.get(u.id, {})
        types = []
        tot_taken = tot_remaining = tot_pending = 0
        for t in LEAVE_TYPES:
            allow = DEFAULT_ALLOWANCE.get(t, 0)
            taken = per.get(t, {}).get("approved", 0)
            pend = per.get(t, {}).get("pending", 0)
            rem = (allow - taken) if t != "Unpaid" else None
            types.append({"type": t, "allowance": allow, "taken": taken, "pending": pend, "remaining": rem})
            tot_taken += taken; tot_pending += pend
            if rem is not None:
                tot_remaining += rem
        out.append({"user_id": u.id, "name": u.name, "role": u.role, "branch": u.branch,
                    "emp_code": u.emp_code, "types": types,
                    "total_allowance": sum(DEFAULT_ALLOWANCE[t] for t in LEAVE_TYPES if t != "Unpaid"),
                    "total_taken": tot_taken, "total_pending": tot_pending, "total_remaining": tot_remaining})
    if q:
        s = q.lower().strip()
        out = [r for r in out if s in (r["name"] or "").lower() or s in (r["emp_code"] or "").lower()]
    return {"year": yr, "rows": out}


@router.post("/{leave_id}/{decision}", response_model=schemas.LeaveOut)
def decide(leave_id: int, decision: str, db: Session = Depends(get_db),
           actor: models.User = Depends(require_roles("admin", "manager", "hr", "headoffice"))):
    if decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="decision must be approve or reject")
    lv = db.query(models.Leave).filter(models.Leave.id == leave_id).first()
    if not lv:
        raise HTTPException(status_code=404, detail="Leave not found")
    target = db.query(models.User).filter(models.User.id == lv.user_id).first()
    if target and actor.id == target.id:
        raise HTTPException(status_code=403, detail="You can't approve your own leave — it goes to an Administrator.")
    if not _can_manage(actor, target):
        raise HTTPException(status_code=403, detail="Not allowed to decide this request")
    db.query(models.User).filter_by(id=lv.user_id).with_for_update().first()
    db.refresh(lv)
    desired = "approved" if decision == "approve" else "rejected"
    if lv.status == desired:
        return _out(lv, _names(db))
    if lv.status != "pending":
        raise HTTPException(409, "This request has already been decided.")
    if decision == "approve" and lv.half_day and lv.start_date != lv.end_date:
        raise HTTPException(400, "Half-day leave must cover a single date. Reject this request and ask the employee to reapply.")
    if decision == "approve" and _overlap(db, lv.user_id, lv.start_date, lv.end_date, lv.id):
        raise HTTPException(409, "Another pending or approved request overlaps these dates. Resolve it first.")
    lv.status = "approved" if decision == "approve" else "rejected"
    lv.approver_id = actor.id
    lv.decided_at = datetime.now(timezone.utc)
    audit.record(db, actor, "leave_" + lv.status, entity_type="leave", target_user_id=lv.user_id,
                 detail=f"Leave #{lv.id}: {_eff_days(lv)} day(s), {lv.start_date} to {lv.end_date}")
    db.commit()
    db.refresh(lv)
    _changed()
    return _out(lv, _names(db))


@router.get("/insights")
def insights(db: Session = Depends(get_db),
             actor: models.User = Depends(require_roles("admin", "manager", "hr", "headoffice"))):
    today = _today()
    q_pending = db.query(models.Leave).filter(models.Leave.status == "pending")
    q_today = db.query(models.Leave).filter(models.Leave.status == "approved",
                                            models.Leave.start_date <= today, models.Leave.end_date >= today)
    q_upcoming = db.query(models.Leave).filter(models.Leave.status == "approved",
                                               models.Leave.start_date > today, models.Leave.start_date <= today + timedelta(days=7))
    if actor.role == "manager":
        from sqlalchemy import select
        ids = select(models.User.id).where(models.User.branch == actor.branch)
        q_pending = q_pending.filter(models.Leave.user_id.in_(ids))
        q_today = q_today.filter(models.Leave.user_id.in_(ids))
        q_upcoming = q_upcoming.filter(models.Leave.user_id.in_(ids))
    names = _names(db)
    return {
        "pending": q_pending.count(),
        "on_leave_today": [{"name": names.get(l.user_id, ("", ""))[0], "type": l.leave_type,
                            "half_day": bool(l.half_day), "days_effective": _eff_days(l),
                            "until": l.end_date.isoformat()} for l in q_today.all()],
        "upcoming_week": q_upcoming.count(),
    }
