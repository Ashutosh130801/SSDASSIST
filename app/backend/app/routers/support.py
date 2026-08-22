"""Help / Support tickets.

Any user can raise a query or issue from the Help section and track its status. Tickets are
handled by the hidden 'techsupport' role, who can reply and mark them resolved with remarks.
Both sides get in-app notifications on every update.
"""
from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/api/support", tags=["support"])
SUPPORT_ROLES = ("techsupport", "admin")
CATEGORIES = ["login", "data", "bug", "feature", "performance", "other"]


def _is_support(user) -> bool:
    return user.role in SUPPORT_ROLES


def _msg(user, text, kind="message"):
    return {"by_id": user.id, "name": user.name, "role": user.role,
            "text": (text or "").strip(), "at": datetime.utcnow().isoformat(), "kind": kind}


def _notify(db, user_id, title, body, by_name):
    db.add(models.Notification(user_id=user_id, type="support", title=title[:160],
                               body=body, created_by=by_name))


def _out(t: models.SupportTicket) -> dict:
    return {
        "id": t.id, "user_id": t.user_id, "user_name": t.user_name, "user_role": t.user_role,
        "branch": t.branch, "category": t.category, "subject": t.subject, "status": t.status,
        "messages": t.messages or [], "resolved_by": t.resolved_by,
        "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


@router.get("/meta")
def meta():
    return {"categories": CATEGORIES}


@router.get("/tickets")
def list_tickets(status: str | None = None, db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)):
    """Support/admin see every ticket; everyone else sees only their own."""
    q = db.query(models.SupportTicket)
    if not _is_support(user):
        q = q.filter(models.SupportTicket.user_id == user.id)
    if status:
        q = q.filter(models.SupportTicket.status == status)
    rows = q.order_by(models.SupportTicket.updated_at.desc()).all()
    counts = {"open": 0, "in_progress": 0, "resolved": 0}
    for t in db.query(models.SupportTicket.status).all() if _is_support(user) else \
            db.query(models.SupportTicket.status).filter(models.SupportTicket.user_id == user.id).all():
        counts[t[0]] = counts.get(t[0], 0) + 1
    return {"tickets": [_out(t) for t in rows], "counts": counts, "is_support": _is_support(user)}


@router.post("/tickets")
def create_ticket(body: dict = Body(...), db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    subject = (body.get("subject") or "").strip()
    message = (body.get("message") or "").strip()
    if not subject or not message:
        raise HTTPException(status_code=400, detail="Subject and message are required.")
    cat = (body.get("category") or "other").strip().lower()
    t = models.SupportTicket(
        user_id=user.id, user_name=user.name, user_role=user.role, branch=user.branch,
        category=cat if cat in CATEGORIES else "other", subject=subject[:200],
        status="open", messages=[_msg(user, message, kind="opened")],
    )
    db.add(t)
    db.flush()
    # Alert every tech-support account so it shows on their bell + inbox.
    for su in db.query(models.User).filter(models.User.role == "techsupport",
                                           models.User.is_active.is_(True)).all():
        _notify(db, su.id, f"New support ticket #{t.id}", f"{user.name}: {subject}", user.name)
    db.commit(); db.refresh(t)
    return _out(t)


def _get(db, tid, user):
    t = db.query(models.SupportTicket).filter(models.SupportTicket.id == tid).first()
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if not _is_support(user) and t.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your ticket")
    return t


@router.get("/tickets/{tid}")
def get_ticket(tid: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return _out(_get(db, tid, user))


@router.post("/tickets/{tid}/reply")
def reply(tid: int, body: dict = Body(...), db: Session = Depends(get_db),
          user: models.User = Depends(get_current_user)):
    t = _get(db, tid, user)
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Reply text is required.")
    t.messages = (t.messages or []) + [_msg(user, text)]
    t.updated_at = datetime.utcnow()
    if _is_support(user):
        if t.status == "open":
            t.status = "in_progress"
        _notify(db, t.user_id, f"Support replied — #{t.id}", text, user.name)
    else:
        # user replied → nudge every tech-support account
        for su in db.query(models.User).filter(models.User.role == "techsupport",
                                               models.User.is_active.is_(True)).all():
            _notify(db, su.id, f"Reply on ticket #{t.id}", f"{user.name}: {text}", user.name)
    db.commit(); db.refresh(t)
    return _out(t)


@router.post("/tickets/{tid}/status")
def set_status(tid: int, body: dict = Body(...), db: Session = Depends(get_db),
               user: models.User = Depends(get_current_user)):
    if not _is_support(user):
        raise HTTPException(status_code=403, detail="Only tech support can change status.")
    t = db.query(models.SupportTicket).filter(models.SupportTicket.id == tid).first()
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")
    new = (body.get("status") or "").strip().lower()
    if new not in ("open", "in_progress", "resolved"):
        raise HTTPException(status_code=400, detail="Invalid status.")
    remark = (body.get("remark") or "").strip()
    t.status = new
    if remark:
        t.messages = (t.messages or []) + [_msg(user, remark, kind="status:" + new)]
    if new == "resolved":
        t.resolved_by = user.id
        t.resolved_at = datetime.utcnow()
    t.updated_at = datetime.utcnow()
    label = {"open": "reopened", "in_progress": "in progress", "resolved": "resolved"}[new]
    _notify(db, t.user_id, f"Ticket #{t.id} {label}",
            (remark or f"Your ticket was marked {label}."), user.name)
    db.commit(); db.refresh(t)
    return _out(t)
