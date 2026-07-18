"""Live spreadsheet endpoints for telecallers: column preferences, single-cell edits
(with contact tracking + live broadcast), and web→phone case handoff."""
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user
from .cases import _scope
from .realtime import manager

router = APIRouter(prefix="/api/sheet", tags=["sheet"])

# Fields a telecaller may edit inline. Everything else is read-only in the grid.
EDITABLE = {
    "status", "disposition", "remarks", "follow_up_date",
    "received_amount", "phone", "alt_phone", "paid_status", "min_amount_due",
}
# Editing any of these counts as "contacted today" for performance stats.
CONTACT_FIELDS = {"status", "disposition", "remarks", "received_amount", "paid_status"}


class CellUpdate(BaseModel):
    field: str
    value: Optional[Any] = None


@router.get("/prefs")
def get_prefs(user: models.User = Depends(get_current_user)):
    """The telecaller's saved sheet layout (visible columns, order, widths, custom formulas)."""
    return user.sheet_prefs or {}


@router.put("/prefs")
def put_prefs(body: dict = Body(...), db: Session = Depends(get_db),
              user: models.User = Depends(get_current_user)):
    user.sheet_prefs = body or {}
    db.commit()
    return {"ok": True}


def _coerce(field: str, value: Any):
    if field in ("received_amount", "min_amount_due"):
        try:
            return Decimal(str(value or 0))
        except (InvalidOperation, ValueError):
            raise HTTPException(status_code=400, detail="Amount must be a number")
    if field == "follow_up_date":
        if not value:
            return None
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            raise HTTPException(status_code=400, detail="Date must be YYYY-MM-DD")
    return value if value not in ("", None) else None


@router.patch("/cell/{case_id}")
async def update_cell(case_id: int, body: CellUpdate, db: Session = Depends(get_db),
                      user: models.User = Depends(get_current_user)):
    if body.field not in EDITABLE:
        raise HTTPException(status_code=400, detail=f"'{body.field}' is not editable")

    case = _scope(db.query(models.Case), user).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    # A telecaller may only edit cases in their own queue.
    if user.role == "telecaller" and case.assigned_caller_id != user.id:
        raise HTTPException(status_code=403, detail="This case is not in your queue")

    setattr(case, body.field, _coerce(body.field, body.value))

    if body.field == "received_amount":
        case.pending_amount = (Decimal(case.funding_amount or 0) - Decimal(case.received_amount or 0))
        if Decimal(case.received_amount or 0) >= Decimal(case.funding_amount or 0) > 0:
            case.paid_status = "PAID"

    if body.field in CONTACT_FIELDS:
        case.last_contacted_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(case)

    payload = schemas.CaseOut.model_validate(case).model_dump(mode="json")
    await manager.broadcast({"type": "case_update", "case": payload})
    return payload


@router.post("/open/{case_id}")
async def open_on_phone(case_id: int, db: Session = Depends(get_db),
                        user: models.User = Depends(get_current_user)):
    """Signal the telecaller's phone (same account) to open this case so they can
    call / WhatsApp from mobile while working the sheet on the web."""
    case = _scope(db.query(models.Case), user).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    await manager.send_to_user(user.id, {"type": "open_case", "case_id": case_id})
    return {"ok": True}
