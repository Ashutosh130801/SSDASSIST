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
from .. import audit

router = APIRouter(prefix="/api/sheet", tags=["sheet"])

# Fields a telecaller may edit inline. Everything else is read-only in the grid.
EDITABLE = {
    "status", "disposition", "remarks", "follow_up_date",
    "received_amount", "pending_amount", "phone", "alt_phone", "paid_status",
    "min_amount_due", "norm_stab", "cat", "team", "team_lead", "caller_name", "fos_name",
    # PL/BL: TOS and the daily-updated OD STAB / OD NORM targets are caller-editable.
    "total_outstanding", "principal_outstanding", "stab_amount", "norm_amount",
    # Customer's latest address / phone found mid-cycle — surfaced to the assigned FOS.
    "new_address", "new_phone",
}
NUMERIC = {"received_amount", "pending_amount", "min_amount_due", "enr", "norm_amount", "stab_amount",
           "total_outstanding", "principal_outstanding"}
# Editing any of these counts as "contacted today" for performance stats.
CONTACT_FIELDS = {"status", "disposition", "remarks", "received_amount", "paid_status", "norm_stab"}


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
    if field in NUMERIC:
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
    is_extra = body.field.startswith("x_")     # free-form caller-added column
    if body.field not in EDITABLE and not is_extra:
        raise HTTPException(status_code=400, detail=f"'{body.field}' is not editable")

    case = _scope(db.query(models.Case), user).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    # A telecaller may only edit cases in their own queue.
    if user.role == "telecaller" and case.assigned_caller_id != user.id:
        raise HTTPException(status_code=403, detail="This case is not in your queue")
    from .cases import _ensure_open
    _ensure_open(case, user)

    if is_extra:
        extra = dict(case.extra or {})
        old_val = extra.get(body.field)
        if body.value in (None, ""):
            extra.pop(body.field, None)
        else:
            extra[body.field] = body.value
        case.extra = extra
        new_val = body.value
    else:
        old_val = getattr(case, body.field, None)
        setattr(case, body.field, _coerce(body.field, body.value))
        new_val = getattr(case, body.field, None)

    if str(old_val) != str(new_val):
        audit.record(db, user, "cell_edit", case, field=body.field, old=old_val, new=new_val,
                     detail=f"{body.field} edited in live sheet")
        audit.stamp_case(case, user)

    # Money edits flow through the single source of truth (paymath) so pending and
    # PAID / PARTIAL / UNPAID stay correct for EVERY product — funding, TOS, ENR, POS and
    # NORM/STAB settlement — not just funding-based ones. A change to the collected amount also
    # drops a dated PAYMENT event so the money shows in the trend / FTD-MTD windows exactly like a
    # DPR update or a field collection (this closes the "reflected today, gone tomorrow" gap).
    _MONEY_FIELDS = {"received_amount", "funding_amount", "total_outstanding", "enr",
                     "principal_outstanding", "norm_amount", "stab_amount", "auto_debit", "norm_stab"}
    if body.field in _MONEY_FIELDS:
        from .. import paymath
        if body.field == "received_amount":
            _delta = Decimal(case.received_amount or 0) - Decimal(str(old_val or 0))
            if abs(_delta) >= Decimal("0.5"):     # positive = collection, negative = correction/reversal
                _credit = case.assigned_caller_id or case.assigned_fos_id or user.id
                db.add(models.CallLog(case_id=case.id, caller_id=_credit, disposition="PAYMENT",
                                      ptp_amount=_delta, note=f"Live-sheet collection edit (by {user.name})"))
        paymath.recompute(case)

    # PL/BL MIS base is TOS — keep ENR mirrored to it so the MIS updates live on a TOS edit.
    if body.field == "total_outstanding" and (case.segment or "") == "PL/BL":
        case.enr = case.total_outstanding

    if body.field in CONTACT_FIELDS:
        case.last_contacted_at = datetime.now(timezone.utc)

    # New address / phone: stamp who+when and alert the assigned field officer.
    if body.field in ("new_address", "new_phone") and str(old_val) != str(new_val):
        case.new_contact_by = user.name
        case.new_contact_at = datetime.now(timezone.utc)
        if case.assigned_fos_id:
            label = "phone" if body.field == "new_phone" else "address"
            icon = "📞" if body.field == "new_phone" else "📍"
            who = case.customer_name or case.account_no or f"case #{case.id}"
            from .notifications import push
            push(db, case.assigned_fos_id,
                 title=f"Updated contact — {who}",
                 body=f"{icon} New {label}: {new_val}   (by {user.name})",
                 case_id=case.id, ntype="contact_update", by_name=user.name)

    db.commit()
    db.refresh(case)

    payload = schemas.CaseOut.model_validate(case).model_dump(mode="json")
    await manager.broadcast({"type": "case_update", "case": payload})
    await manager.broadcast({"type": "data_changed", "bank": case.bank, "product": case.product})
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
