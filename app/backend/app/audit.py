"""Central audit trail. Call `record()` from any endpoint that mutates data so the
admin/manager Activity Log captures who did what, when, and the before/after value.

Kept deliberately tiny and dependency-free: it only appends an AuditLog row to the
session already in play (the caller commits as part of its own transaction)."""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from . import models


def _s(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v)
    return s[:2000]


def record(db: Session, actor: Optional[models.User], action: str,
           case: Optional[models.Case] = None, *,
           field: str | None = None, old: Any = None, new: Any = None,
           detail: str | None = None, target_user_id: int | None = None,
           entity_type: str = "case", meta: dict | None = None) -> models.AuditLog:
    """Append one audit entry. Does NOT commit — the caller's transaction owns that."""
    row = models.AuditLog(
        actor_id=getattr(actor, "id", None),
        actor_name=getattr(actor, "name", None),
        actor_role=getattr(actor, "role", None),
        action=action,
        entity_type=entity_type,
        case_id=getattr(case, "id", None),
        target_user_id=target_user_id,
        branch=getattr(case, "branch", None),
        bank=getattr(case, "bank", None),
        product=getattr(case, "product", None),
        field=field,
        old_value=_s(old),
        new_value=_s(new),
        detail=_s(detail),
        meta=meta or {},
    )
    db.add(row)
    return row


def stamp_case(case: models.Case, actor: Optional[models.User]) -> None:
    """Mark who last touched a case (shown as 'last changed by' in the sheet/detail)."""
    if case is not None and actor is not None:
        case.updated_by = actor.id
        case.updated_by_name = actor.name
