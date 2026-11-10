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

VIEW_ROLES = ("admin", "manager", "headoffice", "teamlead")


def _scope(q, viewer: models.User, db: Session = None):
    """Managers see only their branch. Team leads see only their team's activity —
    actions done BY their team members or ON cases that carry the lead's name."""
    if viewer.role == "manager" and viewer.branch:
        q = q.filter(models.AuditLog.branch == viewer.branch)
    elif viewer.role == "teamlead" and db is not None:
        from .cases import _scope_user_ids, teamlead_case_filter
        member_ids = set(_scope_user_ids(db, viewer)) | {viewer.id}
        case_ids = [cid for (cid,) in db.query(models.Case.id).filter(teamlead_case_filter(viewer)).all()]
        conds = []
        if member_ids:
            conds.append(models.AuditLog.actor_id.in_(member_ids))
        if case_ids:
            conds.append(models.AuditLog.case_id.in_(case_ids))
        q = q.filter(or_(*conds)) if conds else q.filter(models.AuditLog.id == -1)
    return q


@router.get("/filters")
def audit_filters(db: Session = Depends(get_db),
                  viewer: models.User = Depends(require_roles(*VIEW_ROLES))):
    """Distinct values to populate the log's filter dropdowns (branch-scoped for managers)."""
    q = _scope(db.query(models.AuditLog), viewer, db)
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
    query = _scope(db.query(models.AuditLog), viewer, db)
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
    else:
        # Bulk actions: ONE summary line each; their per-case rows live in each case's History.
        query = query.filter(or_(models.AuditLog.entity_type.is_(None), models.AuditLog.entity_type != "batch_item"))
    if not case_id and action != "dpr_update":
        # One DPR upload = ONE line (action 'dpr_upload'); its per-case rows stay in each case's
        # History and are shown here only when you filter by that case or by 'dpr_update'.
        query = query.filter(models.AuditLog.action != "dpr_update")
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
        "detail": r.detail, "meta": _light_meta(r.meta),
    } for r in rows]
    return {"total": total, "count": len(items), "offset": offset, "items": items}


def _light_meta(meta):
    """The list sends counts only — the full DPR change list (can be thousands of rows) loads when opened."""
    if isinstance(meta, dict) and isinstance(meta.get("items"), list):
        m = {k: v for k, v in meta.items() if k != "items"}
        m["items_count"] = len(meta["items"])
        return m
    if isinstance(meta, dict) and isinstance(meta.get("changes"), list):
        m = {k: v for k, v in meta.items() if k not in ("changes", "not_paid")}
        m["changes_count"] = len(meta["changes"])
        m["not_paid_count"] = len(meta.get("not_paid") or [])
        return m
    return meta


def _one(db, viewer, entry_id):
    from fastapi import HTTPException
    r = _scope(db.query(models.AuditLog), viewer, db).filter(models.AuditLog.id == entry_id).first()
    if not r:
        raise HTTPException(404, "Log entry not found")
    return r


@router.get("/{entry_id}")
def audit_entry(entry_id: int, db: Session = Depends(get_db),
                viewer: models.User = Depends(require_roles(*VIEW_ROLES))):
    """One log entry with its full detail (e.g. every case a DPR upload changed)."""
    r = _one(db, viewer, entry_id)
    return {"id": r.id, "at": r.at, "actor_id": r.actor_id, "actor": r.actor_name, "role": r.actor_role,
            "action": r.action, "case_id": r.case_id, "branch": r.branch, "bank": r.bank, "product": r.product,
            "field": r.field, "old": r.old_value, "new": r.new_value, "detail": r.detail, "meta": r.meta}


@router.get("/{entry_id}/dpr.xlsx")
def audit_dpr_xlsx(entry_id: int, db: Session = Depends(get_db),
                   viewer: models.User = Depends(require_roles(*VIEW_ROLES))):
    """Excel of a DPR upload's full change list (same as the preview)."""
    import io
    from fastapi import HTTPException
    from fastapi.responses import StreamingResponse
    from .. import audit
    from .archive import _sheet_xlsx
    r = _one(db, viewer, entry_id)
    m = r.meta or {}
    if not m.get("dpr"):
        raise HTTPException(400, "Not a DPR upload entry")
    ch = m.get("changes") or []
    rows = [[c.get("case_id"), c.get("key"), c.get("customer"), c.get("action"), c.get("old_status"), c.get("new_status"),
             c.get("delta"), c.get("new_received"), c.get("norm_stab"),
             "; ".join(f"{k}={v}" for k, v in (c.get("fields") or {}).items())] for c in ch]
    np_rows = [[x.get("account"), x.get("customer"), x.get("amount"), x.get("status"), x.get("reason")] for x in (m.get("not_paid") or [])]
    summary = [["Uploaded by", r.actor_name], ["When", r.at], ["Bank", m.get("bank")], ["Product", m.get("product")],
               ["File", m.get("file")], ["Month", m.get("month")]] + \
              [[k.replace("_", " ").title(), m.get(k)] for k in ("rows_in_file", "paid", "extra", "reduce", "unpaid", "plbl",
                                                                  "no_change", "unmatched", "field_updates", "collected")]
    data = _sheet_xlsx([("Summary", ["Item", "Value"], summary),
                        ("Changes", ["Case id", "Account / card", "Customer", "Action", "Before", "After", "Δ amount ₹",
                                     "Collected now ₹", "NORM/STAB", "Fields updated"], rows),
                        ("Not paid - unmatched", ["Account / card", "Customer", "Amount ₹", "Status", "Reason"], np_rows)])
    audit.record(db, viewer, "download", None, entity_type="download", detail=f"DPR change list #{r.id} ({len(rows)} rows)")
    db.commit()
    name = f"DPR_{m.get('bank') or ''}_{m.get('product') or ''}_{r.at:%Y%m%d_%H%M}.xlsx".replace(" ", "_").replace("/", "-")
    return StreamingResponse(io.BytesIO(data), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/{entry_id}/items.xlsx")
def audit_items_xlsx(entry_id: int, db: Session = Depends(get_db),
                     viewer: models.User = Depends(require_roles(*VIEW_ROLES))):
    """Excel of a bulk action's full case list (re-allocation, transfer, remove, joint allocation…)."""
    import io
    from fastapi import HTTPException
    from fastapi.responses import StreamingResponse
    from .. import audit
    from .archive import _sheet_xlsx
    r = _one(db, viewer, entry_id)
    m = r.meta or {}
    if not m.get("bulk"):
        raise HTTPException(400, "Not a bulk action entry")
    rows = [[i.get("case_id"), i.get("account"), i.get("customer"), i.get("bank"), i.get("product"), i.get("action"),
             i.get("field"), i.get("old"), i.get("new"), i.get("detail")] for i in (m.get("items") or [])]
    data = _sheet_xlsx([("Summary", ["Item", "Value"], [["Action", m.get("label")], ["Done by", r.actor_name], ["When", r.at],
                                                        ["Cases", m.get("cases")], ["Detail", r.detail]]),
                        ("Cases", ["Case id", "Account / card", "Customer", "Bank", "Product", "Action", "Field", "Before", "After", "Detail"], rows)])
    audit.record(db, viewer, "download", None, entity_type="download", detail=f"Bulk action list #{r.id} ({len(rows)} rows)")
    db.commit()
    name = f"{(m.get('kind') or 'bulk')}_{r.at:%Y%m%d_%H%M}.xlsx"
    return StreamingResponse(io.BytesIO(data), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})
