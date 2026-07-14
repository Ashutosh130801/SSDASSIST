from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_roles

router = APIRouter(prefix="/api/devices", tags=["devices"])


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
    q = (db.query(models.Device, models.User.name, models.User.branch)
         .join(models.User, models.User.id == models.Device.user_id))
    if actor.role == "manager":
        q = q.filter(models.User.branch == actor.branch)
    if pending is not None:
        q = q.filter(models.Device.approved == (not pending))
    rows = q.order_by(models.Device.approved.asc(), models.Device.created_at.desc()).all()
    out = []
    for dev, name, branch in rows:
        d = schemas.DeviceOut.model_validate(dev)
        d.user_name = name
        d.user_branch = branch
        out.append(d)
    return out


@router.post("/{dev_id}/approve")
def approve_device(dev_id: int, db: Session = Depends(get_db),
                   actor: models.User = Depends(require_roles("admin", "manager"))):
    dev = _get_device(db, actor, dev_id)
    dev.approved = True
    db.commit()
    return {"ok": True}


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
