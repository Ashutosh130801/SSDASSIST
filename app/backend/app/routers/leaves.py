from datetime import datetime, timezone, timedelta, date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user, require_roles

router = APIRouter(prefix="/api/leaves", tags=["leaves"])

IST = timezone(timedelta(hours=5, minutes=30))
LEAVE_TYPES = ["Casual", "Sick", "Earned", "Unpaid"]
DEFAULT_ALLOWANCE = {"Casual": 12, "Sick": 12, "Earned": 15, "Unpaid": 0}


def _today():
    return datetime.now(IST).date()


def _names(db):
    return {u.id: (u.name, u.branch) for u in db.query(models.User).all()}


def _out(lv, names):
    d = schemas.LeaveOut.model_validate(lv)
    nm = names.get(lv.user_id, (None, None))
    d.user_name, d.user_branch = nm[0], nm[1]
    if lv.approver_id:
        d.approver_name = names.get(lv.approver_id, (None, None))[0]
    return d


def _can_manage(actor, target_user):
    if actor.role == "admin":
        return True
    if actor.role == "manager":
        return target_user and target_user.branch == actor.branch and target_user.role not in ("admin", "manager")
    return False


@router.post("", response_model=schemas.LeaveOut)
def apply_leave(body: schemas.LeaveCreate, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)):
    if body.leave_type not in LEAVE_TYPES:
        raise HTTPException(status_code=400, detail=f"leave_type must be one of {LEAVE_TYPES}")
    if body.end_date < body.start_date:
        raise HTTPException(status_code=400, detail="end date must be on or after start date")
    days = (body.end_date - body.start_date).days + 1
    lv = models.Leave(user_id=user.id, leave_type=body.leave_type, start_date=body.start_date,
                      end_date=body.end_date, days=days, reason=body.reason, status="pending")
    db.add(lv)
    db.commit()
    db.refresh(lv)
    return _out(lv, _names(db))


@router.get("", response_model=list[schemas.LeaveOut])
def list_leaves(status: str | None = None, scope: str = "auto", db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)):
    """scope=mine -> only my leaves; scope=team -> branch/all (admin/manager);
    scope=auto -> mine for staff, team for admin/manager."""
    q = db.query(models.Leave)
    want_team = scope == "team" or (scope == "auto" and user.role in ("admin", "manager"))
    if not want_team or user.role in ("fos", "telecaller"):
        q = q.filter(models.Leave.user_id == user.id)
    elif user.role == "manager":
        from sqlalchemy import select
        ids = select(models.User.id).where(models.User.branch == user.branch)
        q = q.filter(models.Leave.user_id.in_(ids))
    # admin team -> all
    if status:
        q = q.filter(models.Leave.status == status)
    rows = q.order_by(models.Leave.created_at.desc()).all()
    names = _names(db)
    return [_out(lv, names) for lv in rows]


@router.get("/balance")
def balance(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    year = _today().year
    jan1 = date(year, 1, 1)
    rows = (db.query(models.Leave.leave_type, models.Leave.status, func.coalesce(func.sum(models.Leave.days), 0))
            .filter(models.Leave.user_id == user.id, models.Leave.start_date >= jan1)
            .group_by(models.Leave.leave_type, models.Leave.status).all())
    used, pending = {}, {}
    for lt, st, d in rows:
        if st == "approved":
            used[lt] = used.get(lt, 0) + int(d)
        elif st == "pending":
            pending[lt] = pending.get(lt, 0) + int(d)
    out = []
    for t in LEAVE_TYPES:
        allow = DEFAULT_ALLOWANCE.get(t, 0)
        u = used.get(t, 0)
        out.append({"type": t, "allowance": allow, "used": u, "pending": pending.get(t, 0),
                    "remaining": (allow - u) if t != "Unpaid" else None})
    return out


@router.post("/{leave_id}/{decision}", response_model=schemas.LeaveOut)
def decide(leave_id: int, decision: str, db: Session = Depends(get_db),
           actor: models.User = Depends(require_roles("admin", "manager"))):
    if decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="decision must be approve or reject")
    lv = db.query(models.Leave).filter(models.Leave.id == leave_id).first()
    if not lv:
        raise HTTPException(status_code=404, detail="Leave not found")
    target = db.query(models.User).filter(models.User.id == lv.user_id).first()
    if not _can_manage(actor, target):
        raise HTTPException(status_code=403, detail="Not allowed to decide this request")
    lv.status = "approved" if decision == "approve" else "rejected"
    lv.approver_id = actor.id
    lv.decided_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(lv)
    return _out(lv, _names(db))


@router.get("/insights")
def insights(db: Session = Depends(get_db),
             actor: models.User = Depends(require_roles("admin", "manager"))):
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
                            "until": l.end_date.isoformat()} for l in q_today.all()],
        "upcoming_week": q_upcoming.count(),
    }
