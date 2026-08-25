"""Per-user notifications (bell). Currently raised when a caller / head-office updates a
customer's new address or phone on a case, so the assigned FOS is alerted."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _out(n: models.Notification) -> dict:
    return {
        "id": n.id, "case_id": n.case_id, "type": n.type, "title": n.title,
        "body": n.body, "read": bool(n.read), "created_by": n.created_by,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


def push(db: Session, user_id: int, title: str, body: str,
         case_id: int | None = None, ntype: str = "contact_update",
         by_name: str | None = None) -> models.Notification | None:
    """Create a notification row and fire a live push to the recipient. Caller commits."""
    if not user_id:
        return None
    n = models.Notification(user_id=user_id, case_id=case_id, type=ntype,
                            title=title, body=body, created_by=by_name)
    db.add(n)
    db.flush()
    try:
        from .realtime import notify_user
        notify_user(user_id, {"type": "notification", "notification": _out(n)})
    except Exception:
        pass
    return n


def _case_associates(db: Session, case, include_supervisors: bool = True) -> set[int]:
    """User ids associated with a case: assigned FOS & caller (or their pre-escalation owners),
    the escalation owner, the case's team lead, and — optionally — the branch manager(s) and
    head office. Blocked/inactive users are dropped by the caller."""
    ids: set[int] = set()
    for v in (getattr(case, "assigned_fos_id", None), getattr(case, "assigned_caller_id", None),
              getattr(case, "esc_prev_fos_id", None), getattr(case, "esc_prev_caller_id", None),
              getattr(case, "escalated_to", None)):
        if v:
            ids.add(v)
    # Team lead named on the case (matched to a user by name / emp code).
    tl = (getattr(case, "team_lead", None) or "").strip().lower()
    if tl:
        from sqlalchemy import func, or_ as _or
        row = (db.query(models.User.id)
               .filter(models.User.role == "teamlead",
                       _or(func.lower(func.trim(models.User.name)) == tl,
                           func.lower(func.trim(models.User.emp_code)) == tl))
               .first())
        if row:
            ids.add(row[0])
    if include_supervisors:
        # Branch manager(s) for the case's branch + all head-office users.
        q = db.query(models.User.id).filter(models.User.is_active.is_(True))
        from sqlalchemy import or_ as _or2
        conds = [models.User.role == "headoffice"]
        if getattr(case, "branch", None):
            conds.append((models.User.role == "manager") & (models.User.branch == case.branch))
        for (uid,) in q.filter(_or2(*conds)).all():
            ids.add(uid)
    return ids


def notify_case_change(db: Session, case, actor, summary: str,
                       ntype: str = "case_update", include_supervisors: bool = True) -> int:
    """Notify everyone associated with a case that it changed — with what changed and who did it.
    Excludes the actor. Caller commits. Returns how many notifications were created."""
    actor_id = getattr(actor, "id", None)
    actor_name = getattr(actor, "name", None) or "Someone"
    ids = _case_associates(db, case, include_supervisors=include_supervisors)
    ids.discard(actor_id)
    if not ids:
        return 0
    # Skip blocked/inactive recipients.
    active = {u.id for u in db.query(models.User.id).filter(
        models.User.id.in_(ids), models.User.is_active.is_(True)).all()} if ids else set()
    cust = getattr(case, "customer_name", None) or getattr(case, "account_no", None) or f"Case #{getattr(case, 'id', '')}"
    title = f"{cust} — updated by {actor_name}"
    body = f"{summary}\n— by {actor_name}"
    n = 0
    for uid in active:
        push(db, uid, title, body, case_id=getattr(case, "id", None), ntype=ntype, by_name=actor_name)
        n += 1
    return n


@router.get("")
def my_notifications(unread_only: bool = False, limit: int = 50,
                     db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)):
    q = db.query(models.Notification).filter(models.Notification.user_id == user.id)
    if unread_only:
        q = q.filter(models.Notification.read.is_(False))
    rows = q.order_by(models.Notification.created_at.desc()).limit(min(limit, 200)).all()
    unread = db.query(models.Notification).filter(
        models.Notification.user_id == user.id,
        models.Notification.read.is_(False)).count()
    return {"unread": unread, "items": [_out(n) for n in rows]}


@router.get("/unread-count")
def unread_count(db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)):
    n = db.query(models.Notification).filter(
        models.Notification.user_id == user.id,
        models.Notification.read.is_(False)).count()
    return {"unread": n}


@router.post("/{nid}/read")
def mark_read(nid: int, db: Session = Depends(get_db),
              user: models.User = Depends(get_current_user)):
    n = db.query(models.Notification).filter(
        models.Notification.id == nid, models.Notification.user_id == user.id).first()
    if not n:
        raise HTTPException(status_code=404, detail="Not found")
    n.read = True
    db.commit()
    return {"ok": True}


@router.post("/read-all")
def mark_all_read(db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    db.query(models.Notification).filter(
        models.Notification.user_id == user.id,
        models.Notification.read.is_(False)).update({models.Notification.read: True})
    db.commit()
    return {"ok": True}
