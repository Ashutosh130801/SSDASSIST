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
