from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_roles

router = APIRouter(prefix="/api/legal", tags=["legal"])

MATTER_TYPES = ["Sec 138", "SARFAESI", "Arbitration", "IBC", "Civil", "Criminal", "Consumer"]


def _scope(q, actor):
    if actor.role == "manager":
        return q.filter(models.LegalCase.branch == actor.branch)
    return q


@router.get("", response_model=list[schemas.LegalOut])
def list_legal(status: str | None = None, matter_type: str | None = None,
               db: Session = Depends(get_db),
               actor: models.User = Depends(require_roles("admin", "manager"))):
    q = _scope(db.query(models.LegalCase), actor)
    if status:
        q = q.filter(models.LegalCase.status == status)
    if matter_type:
        q = q.filter(models.LegalCase.matter_type == matter_type)
    # nulls last, then soonest hearing first (portable across SQLite/Postgres)
    return q.order_by(models.LegalCase.next_hearing_date.is_(None),
                      models.LegalCase.next_hearing_date.asc()).all()


@router.post("", response_model=schemas.LegalOut)
def create_legal(body: schemas.LegalCreate, db: Session = Depends(get_db),
                 actor: models.User = Depends(require_roles("admin", "manager"))):
    if body.matter_type not in MATTER_TYPES:
        raise HTTPException(status_code=400, detail=f"matter_type must be one of {MATTER_TYPES}")
    data = body.model_dump()
    if actor.role == "manager":
        data["branch"] = actor.branch
    lc = models.LegalCase(created_by=actor.id, **data)
    db.add(lc)
    db.commit()
    db.refresh(lc)
    return lc


@router.patch("/{lid}", response_model=schemas.LegalOut)
def update_legal(lid: int, body: schemas.LegalUpdate, db: Session = Depends(get_db),
                 actor: models.User = Depends(require_roles("admin", "manager"))):
    lc = db.query(models.LegalCase).filter(models.LegalCase.id == lid).first()
    if not lc:
        raise HTTPException(status_code=404, detail="Legal case not found")
    if actor.role == "manager" and lc.branch != actor.branch:
        raise HTTPException(status_code=403, detail="Not in your branch")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(lc, k, v)
    db.commit()
    db.refresh(lc)
    return lc


@router.delete("/{lid}")
def delete_legal(lid: int, db: Session = Depends(get_db),
                 actor: models.User = Depends(require_roles("admin", "manager"))):
    lc = db.query(models.LegalCase).filter(models.LegalCase.id == lid).first()
    if not lc:
        raise HTTPException(status_code=404, detail="Legal case not found")
    if actor.role == "manager" and lc.branch != actor.branch:
        raise HTTPException(status_code=403, detail="Not in your branch")
    db.delete(lc)
    db.commit()
    return {"ok": True}


@router.get("/insights")
def legal_insights(db: Session = Depends(get_db),
                   actor: models.User = Depends(require_roles("admin", "manager"))):
    today = date.today()
    q = _scope(db.query(models.LegalCase), actor).filter(models.LegalCase.status == "open")
    return {
        "open": q.count(),
        "hearing_overdue": q.filter(models.LegalCase.next_hearing_date < today).count(),
        "hearing_today": q.filter(models.LegalCase.next_hearing_date == today).count(),
        "hearing_week": q.filter(models.LegalCase.next_hearing_date > today,
                                 models.LegalCase.next_hearing_date <= today + timedelta(days=7)).count(),
    }
