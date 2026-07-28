"""Read-only Activity / Audit Log for managers & admins.

Every mutating action in the system is recorded to models.AuditLog (see app/audit.py).
This exposes it with branch / role / employee / action / bank / product / date filters.
Managers see only their own branch; admin & head office see everything."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..deps import require_roles

router = APIRouter(prefix="/api/audit", tags=["audit"])

VIEW_ROLES = ("admin", "manager", "headoffice")


def _scope(q, viewer: models.User):
    """Managers are limited to their own branch's activity."""
    if viewer.role == "manager" and viewer.branch:
        q = q.filter(models.AuditLog.branch == viewer.branch)
    return q


@router.get("/filters")
def audit_filters(db: Session = Depends(get_db),
                  viewer: models.User = Depends(require_roles(*VIEW_ROLES))):
    """Distinct values to populate the log's filter dropdowns (branch-scoped for managers)."""
    q = _scope(db.query(models.AuditLog), viewer)
    branches = sorted({b for (b,) in q.with_entities(models.AuditLog.branch).distinct() if b})
    banks = sorted({b for (b,) in q.with_entities(models.AuditLog.bank).distinct() if b})
    products = sorted({p for (p,) in q.with_entities(models.AuditLog.product).distinct() if p})
    actions = sorted({a for (a,) in q.with_entities(models.AuditLog.action).distinct() if a})
    roles = sorted({r for (r,) in q.with_entities(models.AuditLog.actor_role).distinct() if r})
    # Employees who appear as actors (so the filter only lists people who did something)
    actor_rows = q.with_entities(models.AuditLog.actor_id, models.AuditLog.actor_name,
                                 models.AuditLog.actor_role).distinct().all()
    seen, employees = set(), []
    for aid, name, role in actor_rows:
        if aid and aid not in seen:
            seen.add(aid)
            employees.append({"id": aid, "name": name, "role": role})
    employees.sort(key=lambda e: (e["name"] or "").lower())
    return {"branches": branches, "banks": banks, "products": products,
            "actions": actions, "roles": roles, "employees": employees}


@router.get("")
def audit_list(
    db: Session = Depends(get_db),
    viewer: models.User = Depends(require_roles(*VIEW_ROLES)),
    branch: str | None = None,
    role: str | None = None,           # actor role
    emp: int | None = None,            # actor id
    action: str | None = None,
    bank: str | None = None,
    product: str | None = None,
    case_id: int | None = None,
    q: str | None = None,              # free text over detail / names / field
    period: str | None = None,        # "YYYY-MM" — changes made during that month
    days: int | None = None,          # last N days
    limit: int = Query(200, le=1000),
    offset: int = 0,
):
    """Filtered, paginated activity feed — newest first."""
    query = _scope(db.query(models.AuditLog), viewer)
    if branch:
        query = query.filter(models.AuditLog.branch == branch)
    if role:
        query = query.filter(models.AuditLog.actor_role == role)
    if emp:
        query = query.filter(models.AuditLog.actor_id == emp)
    if action:
        query = query.filter(models.AuditLog.action == action)
    if bank:
        query = query.filter(models.AuditLog.bank == bank)
    if product:
        query = query.filter(models.AuditLog.product == product)
    if case_id:
        query = query.filter(models.AuditLog.case_id == case_id)
    if period:
        try:
            y, m = int(period[:4]), int(period[5:7])
            start = datetime(y, m, 1, tzinfo=timezone.utc)
            end = datetime(y + (m // 12), (m % 12) + 1, 1, tzinfo=timezone.utc)
            query = query.filter(models.AuditLog.at >= start, models.AuditLog.at < end)
        except (ValueError, TypeError):
            pass
    if days:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        query = query.filter(models.AuditLog.at >= since)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            models.AuditLog.detail.ilike(like),
            models.AuditLog.actor_name.ilike(like),
            models.AuditLog.field.ilike(like),
            models.AuditLog.new_value.ilike(like),
            models.AuditLog.old_value.ilike(like),
        ))

    total = query.count()
    rows = query.order_by(models.AuditLog.at.desc()).offset(offset).limit(limit).all()

    # Resolve customer names for case rows in one query.
    cids = {r.case_id for r in rows if r.case_id}
    cnames = {}
    if cids:
        cnames = {cid: name for cid, name in db.query(
            models.Case.id, models.Case.customer_name).filter(models.Case.id.in_(cids)).all()}

    items = [{
        "id": r.id, "at": r.at, "actor_id": r.actor_id, "actor": r.actor_name,
        "role": r.actor_role, "action": r.action, "case_id": r.case_id,
        "customer": cnames.get(r.case_id), "branch": r.branch, "bank": r.bank,
        "product": r.product, "field": r.field, "old": r.old_value, "new": r.new_value,
        "detail": r.detail, "meta": r.meta,
    } for r in rows]
    return {"total": total, "count": len(items), "offset": offset, "items": items}
