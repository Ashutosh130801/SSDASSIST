from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_roles

router = APIRouter(prefix="/api/devices", tags=["devices"])

MAX_APPROVED_DEVICES = 2


EXEMPT_ROLES = ("admin", "techsupport")   # no device cap — unlimited approved devices


def prune_approved_devices(db: Session, user_id: int, keep: int = MAX_APPROVED_DEVICES):
    """Keep only the most-recently-approved `keep` devices for a user; DELETE the older
    approved ones. A removed device is treated as brand-new next time it signs in, so it
    must be approved again. Admins and tech-support are exempt (no cap). Caller commits."""
    owner = db.query(models.User).filter(models.User.id == user_id).first()
    if owner and owner.role in EXEMPT_ROLES:
        return 0
    approved = (db.query(models.Device)
                .filter(models.Device.user_id == user_id, models.Device.approved.is_(True))
                .all())
    if len(approved) <= keep:
        return 0
    # Newest approval first; fall back to last_seen / created_at for rows approved before
    # the approved_at column existed.
    def _rank(d):
        return d.approved_at or d.last_seen or d.created_at or datetime.min.replace(tzinfo=timezone.utc)
    approved.sort(key=_rank, reverse=True)
    removed = 0
    for d in approved[keep:]:
        db.delete(d)
        removed += 1
    return removed


def _get_device(db: Session, actor: models.User, dev_id: int) -> models.Device:
    dev = db.query(models.Device).filter(models.Device.id == dev_id).first()
    if not dev:
        raise HTTPException(status_code=404, detail="Device not found")
    if actor.role == "manager":
        owner = db.query(models.User).filter(models.User.id == dev.user_id).first()
        if not owner or owner.branch != actor.branch:
            raise HTTPException(status_code=403, detail="Not in your branch")
    return dev


@router.get("", response_model=list[schemas.DeviceOut])
def list_devices(pending: bool | None = None, db: Session = Depends(get_db),
                 actor: models.User = Depends(require_roles("admin", "manager"))):
    q = (db.query(models.Device, models.User.name, models.User.branch, models.User.role)
         .join(models.User, models.User.id == models.Device.user_id))
    if actor.role == "manager":
        q = q.filter(models.User.branch == actor.branch)
    if pending is not None:
        q = q.filter(models.Device.approved == (not pending))
    rows = q.order_by(models.Device.approved.asc(), models.Device.created_at.desc()).all()
    # How many APPROVED devices each of these users currently has (so an admin reviewing a
    # new-device request can see the user's active devices at a glance).
    counts = dict(db.query(models.Device.user_id, func.count(models.Device.id))
                  .filter(models.Device.approved.is_(True))
                  .group_by(models.Device.user_id).all())
    out = []
    for dev, name, branch, role in rows:
        d = schemas.DeviceOut.model_validate(dev)
        d.user_name = name
        d.user_branch = branch
        d.user_role = role
        d.approved_count = int(counts.get(dev.user_id, 0))
        out.append(d)
    return out


@router.post("/{dev_id}/approve")
def approve_device(dev_id: int, db: Session = Depends(get_db),
                   actor: models.User = Depends(require_roles("admin", "manager"))):
    dev = _get_device(db, actor, dev_id)
    dev.approved = True
    dev.approved_at = datetime.now(timezone.utc)
    # Keep at most MAX_APPROVED_DEVICES per user; older approved devices are removed and
    # will have to be re-approved if used again.
    removed = prune_approved_devices(db, dev.user_id)
    db.commit()
    return {"ok": True, "removed_old": removed}


@router.post("/{dev_id}/revoke")
def revoke_device(dev_id: int, db: Session = Depends(get_db),
                  actor: models.User = Depends(require_roles("admin", "manager"))):
    dev = _get_device(db, actor, dev_id)
    dev.approved = False
    db.commit()
    return {"ok": True}


@router.delete("/{dev_id}")
def delete_device(dev_id: int, db: Session = Depends(get_db),
                  actor: models.User = Depends(require_roles("admin", "manager"))):
    dev = _get_device(db, actor, dev_id)
    db.delete(dev)
    db.commit()
    return {"ok": True}
