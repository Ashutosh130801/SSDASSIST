from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user, require_roles

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("", response_model=list[schemas.TemplateOut])
def list_templates(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return db.query(models.MessageTemplate).order_by(models.MessageTemplate.name).all()


@router.post("", response_model=schemas.TemplateOut)
def create_template(body: schemas.TemplateCreate, db: Session = Depends(get_db),
                    actor: models.User = Depends(require_roles("admin", "manager"))):
    t = models.MessageTemplate(name=body.name, channel=body.channel, body=body.body, created_by=actor.id)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@router.patch("/{tid}", response_model=schemas.TemplateOut)
def update_template(tid: int, body: schemas.TemplateCreate, db: Session = Depends(get_db),
                    actor: models.User = Depends(require_roles("admin", "manager"))):
    t = db.query(models.MessageTemplate).filter(models.MessageTemplate.id == tid).first()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    t.name, t.channel, t.body = body.name, body.channel, body.body
    db.commit()
    db.refresh(t)
    return t


@router.delete("/{tid}")
def delete_template(tid: int, db: Session = Depends(get_db),
                    actor: models.User = Depends(require_roles("admin", "manager"))):
    t = db.query(models.MessageTemplate).filter(models.MessageTemplate.id == tid).first()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    db.delete(t)
    db.commit()
    return {"ok": True}


class CommLog(BaseModel):
    case_id: int
    channel: str = "whatsapp"
    text: str | None = None


@router.post("/log")
def log_comm(body: CommLog, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Record a sent message into the case's activity timeline."""
    case = db.query(models.Case).filter(models.Case.id == body.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    db.add(models.CallLog(case_id=case.id, caller_id=user.id, disposition="MESSAGE",
                          note=f"{body.channel}: {(body.text or '')[:200]}"))
    db.commit()
    return {"ok": True}
