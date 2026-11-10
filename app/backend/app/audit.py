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


class Batch:
    """One Audit-Log line for a bulk action (re-allocate, transfer, remove, joint-allocate…).

    Each case still gets its own row (so the case's History shows it), but those rows are marked
    entity_type='batch_item' and hidden from the main Audit Log; the log shows ONE summary row
    (action 'bulk_<kind>') whose meta holds every case — opened like a DPR upload.
    With a single case no summary is written and the case row stays a normal entry."""

    def __init__(self, db: Session, actor, kind: str, label: str):
        self.db, self.actor, self.kind, self.label = db, actor, kind, label
        self.rows, self.items = [], []

    def record(self, action: str, case, **kw):
        row = record(self.db, self.actor, action, case, entity_type="batch_item", **{k: v for k, v in kw.items() if k != "entity_type"})
        self.rows.append(row)
        self.items.append({"case_id": getattr(case, "id", None), "account": getattr(case, "account_no", None),
                           "customer": getattr(case, "customer_name", None), "bank": getattr(case, "bank", None),
                           "product": getattr(case, "product", None), "action": action, "field": kw.get("field"),
                           "old": _s(kw.get("old")), "new": _s(kw.get("new")), "detail": _s(kw.get("detail"))})
        return row

    def close(self, summary: str, meta: dict | None = None):
        case_ids = {i["case_id"] for i in self.items if i["case_id"]}
        if len(case_ids) <= 1:
            for r in self.rows:
                r.entity_type = "case"
            return None
        ports = {(i["bank"], i["product"]) for i in self.items}
        branches = {r.branch for r in self.rows}
        row = record(self.db, self.actor, f"bulk_{self.kind}", None, entity_type="batch",
                     detail=f"{self.label}: {len(case_ids)} cases — {summary}",
                     meta={"bulk": True, "kind": self.kind, "label": self.label, "cases": len(case_ids),
                           "changes": len(self.items), **(meta or {}), "items": self.items[:20000]})
        if len(ports) == 1:
            row.bank, row.product = next(iter(ports))
        if len(branches) == 1:
            row.branch = next(iter(branches))
        return row
