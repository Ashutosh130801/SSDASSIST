from decimal import Decimal
from datetime import datetime, time, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user, require_roles
from ..allocation import run_allocation
from ..config import get_settings
from ..storage import resolve as resolve_photo

router = APIRouter(prefix="/api/cases", tags=["cases"])


def _needs_geocode(q):
    return q.filter(models.Case.latitude.is_(None)).filter(
        or_(models.Case.address.isnot(None), models.Case.pincode.isnot(None)))


@router.post("/geocode")
def geocode(limit: int = 40, db: Session = Depends(get_db),
            admin: models.User = Depends(require_roles("admin"))):
    """Fill in latitude/longitude for cases that only have an address/pincode,
    so they show up as pins on the field map. Processes up to `limit` per call
    (call again while `remaining` > 0). Uses the free OpenStreetMap (Nominatim)
    geocoder — no API key needed. Nominatim asks for max ~1 request/second, so
    this paces itself and is intentionally gentle."""
    import time
    cases = _needs_geocode(db.query(models.Case)).limit(limit).all()
    geocoded, failed = 0, 0
    headers = {"User-Agent": "RecoverIQ/1.0 (collections app; contact admin)"}
    with httpx.Client(timeout=15, headers=headers) as client:
        for c in cases:
            parts = [p for p in [c.address, c.pincode] if p]
            query = (" ".join(parts) + " India").strip()
            try:
                r = client.get("https://nominatim.openstreetmap.org/search",
                               params={"q": query, "format": "json", "limit": 1, "countrycodes": "in"})
                data = r.json()
                if isinstance(data, list) and data:
                    c.latitude, c.longitude = float(data[0]["lat"]), float(data[0]["lon"])
                    geocoded += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
            time.sleep(1)  # respect Nominatim's ~1 req/sec usage policy
    db.commit()
    remaining = _needs_geocode(db.query(models.Case)).count()
    return {"geocoded": geocoded, "failed": failed, "remaining": remaining}


@router.delete("/all")
def delete_all_cases(confirm: str = Query(""), db: Session = Depends(get_db),
                     admin: models.User = Depends(require_roles("admin"))):
    """DANGER: permanently remove every case and its visits/calls, so a fresh loading
    file can be uploaded from scratch. Requires ?confirm=DELETE-ALL. Staff and settings
    are untouched — only case data is wiped."""
    if confirm != "DELETE-ALL":
        raise HTTPException(status_code=400, detail="Pass confirm=DELETE-ALL to wipe all cases.")
    # break foreign-key links first so the delete is safe on Postgres too
    db.query(models.LocationPing).update({models.LocationPing.active_case_id: None}, synchronize_session=False)
    db.query(models.LegalCase).update({models.LegalCase.case_id: None}, synchronize_session=False)
    v = db.query(models.Visit).delete(synchronize_session=False)
    cl = db.query(models.CallLog).delete(synchronize_session=False)
    n = db.query(models.Case).delete(synchronize_session=False)
    db.query(models.ImportBatch).delete(synchronize_session=False)
    db.commit()
    return {"deleted_cases": n, "deleted_visits": v, "deleted_calls": cl}


def _branch_user_ids(user: models.User):
    return select(models.User.id).where(models.User.branch == user.branch)


def _scope(q, user: models.User):
    """Restrict rows by role — FO sees own field cases, telecaller sees own queue,
    branch manager sees cases handled by staff in their branch."""
    if user.role == "fos":
        return q.filter(models.Case.assigned_fos_id == user.id)
    if user.role == "telecaller":
        return q.filter(models.Case.assigned_caller_id == user.id)
    if user.role == "manager":
        ids = _branch_user_ids(user)
        # A case belongs to a branch if it's tagged with that branch OR handled by its staff.
        return q.filter(or_(models.Case.branch == user.branch,
                            models.Case.assigned_fos_id.in_(ids),
                            models.Case.assigned_caller_id.in_(ids)))
    return q  # admin: everything


def propensity(c) -> int:
    """Heuristic 0-100 'likelihood to recover' score to help prioritise cases.
    Pure function of the case's current signals (no extra queries)."""
    s = 50
    disp = (c.disposition or "").upper()
    if "PTP" in disp or "RTP" in disp:
        s += 22
    if (c.paid_status or "") == "PARTIAL":
        s += 15
    if float(c.received_amount or 0) > 0:
        s += 8
    if any(x in disp for x in ("RNR", "SWITCH", "WRONG", "NOT REACHABLE", "REFUSED", "DISPUTE")):
        s -= 22
    if "X" in (c.bucket or "").upper():
        s -= 8
    if c.last_contacted_at:
        s += 5
    if float(c.pending_amount or 0) > 100000:
        s -= 10
    return max(1, min(99, s))


def _with_score(cases):
    for c in cases:
        c.propensity = propensity(c)
    return cases


_IST = timezone(timedelta(hours=5, minutes=30))


def _mark_today(db, cases):
    """Tag each case with contacted_today / visited_today so the FOS & caller views can
    sink touched cases and keep untouched work on top."""
    today = datetime.now(_IST).date()
    start = datetime.combine(today, time.min, tzinfo=_IST).astimezone(timezone.utc)
    ids = [c.id for c in cases]
    visited = set()
    if ids:
        visited = {vid for (vid,) in db.query(models.Visit.case_id).filter(
            models.Visit.case_id.in_(ids), models.Visit.created_at >= start).distinct().all()}
    for c in cases:
        c.visited_today = c.id in visited
        lc = c.last_contacted_at
        if lc and lc.tzinfo is None:
            lc = lc.replace(tzinfo=timezone.utc)
        c.contacted_today = bool(lc and lc.astimezone(_IST).date() == today)
    return cases


@router.get("", response_model=list[schemas.CaseOut])
def list_cases(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
    bank: str | None = None,
    product: str | None = None,
    segment: str | None = None,
    status: str | None = None,
    paid_status: str | None = None,
    search: str | None = None,
    limit: int = Query(500, le=5000),
    offset: int = 0,
):
    q = _scope(db.query(models.Case), user)
    if bank:
        q = q.filter(models.Case.bank == bank)
    if product:
        q = q.filter(models.Case.product == product)
    if segment:
        q = q.filter(models.Case.segment == segment)
    if status:
        q = q.filter(models.Case.status == status)
    if paid_status:
        q = q.filter(models.Case.paid_status == paid_status)
    if search:
        like = f"%{search}%"
        q = q.filter(or_(
            models.Case.customer_name.ilike(like),
            models.Case.account_no.ilike(like),
            models.Case.phone.ilike(like),
            models.Case.pincode.ilike(like),
        ))
    return _mark_today(db, _with_score(q.order_by(models.Case.updated_at.desc()).offset(offset).limit(limit).all()))


class EscalateIn(BaseModel):
    to_user_id: int | None = None       # default: escalate to the actor themselves
    note: str | None = None


def _manager_owns(db, actor, case):
    if actor.role == "manager" and case.branch != actor.branch:
        raise HTTPException(status_code=403, detail="Not in your branch")


@router.get("/escalated", response_model=list[schemas.CaseOut])
def escalated_cases(mine: bool = False, db: Session = Depends(get_db),
                    actor: models.User = Depends(require_roles("admin", "manager", "backend", "headoffice"))):
    """Cases pulled off the field/calling staff. `mine=true` limits to ones escalated to me."""
    q = db.query(models.Case).filter(models.Case.escalated.is_(True))
    if actor.role == "manager":
        q = q.filter(models.Case.branch == actor.branch)
    if mine:
        q = q.filter(models.Case.escalated_to == actor.id)
    return _mark_today(db, _with_score(q.order_by(models.Case.updated_at.desc()).all()))


@router.post("/{case_id}/escalate")
def escalate_case(case_id: int, body: EscalateIn = EscalateIn(), db: Session = Depends(get_db),
                  actor: models.User = Depends(require_roles("admin", "manager", "backend"))):
    """Take a hard/high-value case away from its FOS & caller and own it personally.
    It leaves their queues and individual performance, but stays in MIS & feedback
    (which key off the case's own fos_name/caller/product, not the live assignment)."""
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    _manager_owns(db, actor, case)
    owner_id = body.to_user_id or actor.id
    owner = db.query(models.User).filter(models.User.id == owner_id).first()
    if not owner or owner.role not in ("admin", "manager", "backend", "headoffice"):
        raise HTTPException(status_code=400, detail="Escalation owner must be admin, manager, back-office or head office")
    case.escalated = True
    case.escalated_to = owner_id
    case.escalated_by = actor.id
    case.escalated_at = datetime.now(timezone.utc)
    case.assigned_fos_id = None            # drop from the FOS queue / performance
    case.assigned_caller_id = None         # drop from the caller queue / performance
    if body.note:
        case.allocation_reason = f"Escalated: {body.note}"
    db.commit()
    from .realtime import notify_data_changed
    notify_data_changed(case.bank, case.product)
    return {"ok": True, "escalated_to": owner_id}


@router.post("/{case_id}/deescalate")
def deescalate_case(case_id: int, db: Session = Depends(get_db),
                    actor: models.User = Depends(require_roles("admin", "manager", "backend", "headoffice"))):
    """Release an escalated case back to the pool (admin can re-run allocation to reassign)."""
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    _manager_owns(db, actor, case)
    case.escalated = False
    case.escalated_to = None
    db.commit()
    from .realtime import notify_data_changed
    notify_data_changed(case.bank, case.product)
    return {"ok": True}


@router.get("/product-summary")
def product_summary(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Product cards: one row per bank + product + segment with case counts and money,
    scoped to what the user may see (admin all, manager their branch)."""
    rows = (
        _scope(db.query(
            models.Case.bank, models.Case.product, models.Case.segment,
            func.count(models.Case.id),
            func.coalesce(func.sum(models.Case.pending_amount), 0),
            func.coalesce(func.sum(models.Case.received_amount), 0),
        ), user)
        .group_by(models.Case.bank, models.Case.product, models.Case.segment)
        .all()
    )
    out = [
        {"bank": b or "—", "product": p or "—", "segment": s,
         "count": c, "pending": float(pd or 0), "received": float(rc or 0)}
        for b, p, s, c, pd, rc in rows
    ]
    out.sort(key=lambda x: (x["bank"], x["product"]))
    return out


@router.get("/{case_id}", response_model=schemas.CaseOut)
def get_case(case_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    case = _scope(db.query(models.Case), user).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    case.propensity = propensity(case)
    return case


@router.post("", response_model=schemas.CaseOut)
def create_case(body: schemas.CaseCreate, db: Session = Depends(get_db),
                admin: models.User = Depends(require_roles("admin"))):
    case = models.Case(**body.model_dump())
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


@router.patch("/{case_id}", response_model=schemas.CaseOut)
def update_case(case_id: int, body: schemas.CaseUpdate, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)):
    case = _scope(db.query(models.Case), user).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    data = body.model_dump(exclude_unset=True)
    # only admin may reassign
    if user.role != "admin":
        data.pop("assigned_fos_id", None)
        data.pop("assigned_caller_id", None)
    for k, v in data.items():
        setattr(case, k, v)
    # keep pending consistent when received changes
    if "received_amount" in data:
        case.pending_amount = (Decimal(case.funding_amount or 0) - Decimal(case.received_amount or 0))
        if case.pending_amount <= 0 and Decimal(case.received_amount or 0) > 0:
            case.paid_status = "PAID"
            case.status = "paid"
    db.commit()
    db.refresh(case)
    return case


@router.post("/allocate")
def allocate(body: schemas.AllocateRequest, db: Session = Depends(get_db),
             admin: models.User = Depends(require_roles("admin"))):
    return run_allocation(db, only_unallocated=body.only_unallocated, bank=body.bank)


class PaymentIn(BaseModel):
    amount: Decimal
    mode: str = "UPI"
    note: str | None = None
    norm_stab: str | None = None      # NORM / STAB paid (credit-card cases)


@router.post("/{case_id}/payment", response_model=schemas.CaseOut)
def record_payment(case_id: int, body: PaymentIn, db: Session = Depends(get_db),
                   user: models.User = Depends(require_roles("telecaller", "admin", "fos"))):
    """Record a collection against a case: adds to received, recomputes pending
    with Decimal precision, and writes an entry to the case's activity history."""
    case = _scope(db.query(models.Case), user).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    amt = Decimal(str(body.amount or 0))
    if amt <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero")

    case.received_amount = (Decimal(case.received_amount or 0) + amt)
    case.pending_amount = (Decimal(case.funding_amount or 0) - Decimal(case.received_amount or 0))
    if case.pending_amount <= 0:
        case.paid_status = "PAID"
        case.status = "paid"
        case.follow_up_date = None
    else:
        case.paid_status = "PARTIAL"
    if body.norm_stab:
        ns = body.norm_stab.upper()
        case.norm_stab = "STAB" if "STAB" in ns else ("NORM" if "NORM" in ns else case.norm_stab)

    note = f"₹{amt} via {body.mode}" + (f" — {body.note}" if body.note else "")
    db.add(models.CallLog(case_id=case.id, caller_id=user.id,
                          disposition="PAYMENT", ptp_amount=amt, note=note))
    db.commit()
    db.refresh(case)
    from .realtime import notify_data_changed
    notify_data_changed(case.bank, case.product)
    return case


@router.get("/{case_id}/timeline")
def timeline(case_id: int, db: Session = Depends(get_db),
             user: models.User = Depends(get_current_user)):
    """Full audit trail for a case: creation, field visits (photo/GPS/paid/location-correct/
    moved), calls, and payments — one merged, time-ordered list."""
    case = _scope(db.query(models.Case), user).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    users = {u.id: u.name for u in db.query(models.User).all()}
    ev = []

    ev.append({"type": "created", "at": case.created_at, "by": None, "title": "Case created",
               "detail": " · ".join([x for x in [case.bank, case.bucket, f"target ₹{float(case.funding_amount or 0):.0f}"] if x])})
    if case.assigned_fos_id or case.assigned_caller_id:
        who = " / ".join([x for x in [users.get(case.assigned_fos_id), users.get(case.assigned_caller_id)] if x])
        ev.append({"type": "allocated", "at": case.created_at, "by": None, "title": "Allocated",
                   "detail": f"{who}" + (f" ({case.allocation_reason})" if case.allocation_reason else "")})

    for v in db.query(models.Visit).filter(models.Visit.case_id == case_id).all():
        bits = [v.disposition or "visit"]
        if v.paid:
            bits.append(f"paid ₹{float(v.amount_collected or 0):.0f}")
        if v.location_correct is not None:
            bits.append("location OK" if v.location_correct else "wrong location")
        if v.person_moved:
            bits.append("person moved")
        ev.append({"type": "visit", "at": v.created_at, "by": users.get(v.officer_id), "title": "Field visit",
                   "detail": " · ".join(bits), "lat": v.latitude, "lng": v.longitude,
                   "photo": resolve_photo(v.photo_path), "note": v.note, "amount": float(v.amount_collected or 0)})

    for cl in db.query(models.CallLog).filter(models.CallLog.case_id == case_id).all():
        is_pay = cl.disposition == "PAYMENT"
        ev.append({"type": "payment" if is_pay else "call", "at": cl.created_at, "by": users.get(cl.caller_id),
                   "title": "Payment" if is_pay else f"Call — {cl.disposition or ''}",
                   "detail": cl.note or cl.disposition or "", "amount": float(cl.ptp_amount or 0),
                   "ptp_date": cl.ptp_date.isoformat() if cl.ptp_date else None})

    from datetime import datetime, timezone
    ev.sort(key=lambda e: e["at"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return ev
