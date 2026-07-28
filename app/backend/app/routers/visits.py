import os
import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user, require_roles
from ..storage import save_photo, resolve as resolve_photo
from .. import audit

router = APIRouter(prefix="/api/visits", tags=["visits"])
IST = timezone(timedelta(hours=5, minutes=30))


@router.post("", response_model=schemas.VisitOut)
async def create_visit(
    case_id: int = Form(...),
    latitude: float | None = Form(None),
    longitude: float | None = Form(None),
    gps_accuracy: float | None = Form(None),
    location_correct: bool | None = Form(None),
    person_moved: bool = Form(False),
    paid: bool = Form(False),
    amount_collected: str = Form("0"),
    norm_stab: str | None = Form(None),
    disposition: str | None = Form(None),
    ptp_date: str | None = Form(None),
    note: str | None = Form(None),
    photo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("fos", "admin")),
):
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if user.role == "fos" and case.assigned_fos_id != user.id:
        raise HTTPException(status_code=403, detail="This case is not assigned to you")
    from .cases import _ensure_open
    _ensure_open(case, user)

    photo_path = None
    if photo is not None:
        content = await photo.read()
        photo_path = save_photo(content, photo.filename or "", photo.content_type or "image/jpeg")

    # Geo-fence: distance between where the visit was logged and the case's known location.
    dist_m = None
    if latitude is not None and longitude is not None and case.latitude is not None and case.longitude is not None:
        import math
        r = 6371000.0
        p1, p2 = math.radians(latitude), math.radians(case.latitude)
        dphi = math.radians(case.latitude - latitude); dl = math.radians(case.longitude - longitude)
        a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        dist_m = round(2 * r * math.asin(math.sqrt(a)), 1)

    amt = Decimal(str(amount_collected or "0"))
    visit = models.Visit(
        case_id=case_id, officer_id=user.id, latitude=latitude, longitude=longitude,
        gps_accuracy=gps_accuracy, distance_from_case_m=dist_m, photo_path=photo_path,
        location_correct=location_correct, person_moved=person_moved, paid=paid,
        amount_collected=amt, disposition=disposition, note=note,
    )
    db.add(visit)

    # roll the visit up into the case
    case.status = "in_progress"
    case.visited = True                       # FOS logged a visit → MIS "VISITED"
    if disposition:
        case.disposition = disposition
    if person_moved:
        case.disposition = "MOVED"
    if paid and amt > 0:
        case.received_amount = (Decimal(case.received_amount or 0) + amt)
        case.pending_amount = (Decimal(case.funding_amount or 0) - Decimal(case.received_amount or 0))
        if case.pending_amount <= 0:
            case.paid_status = "PAID"
            case.status = "paid"
        else:
            case.paid_status = "PARTIAL"
        if norm_stab:                         # credit-card: NORM or STAB paid
            ns = norm_stab.upper()
            case.norm_stab = "STAB" if "STAB" in ns else ("NORM" if "NORM" in ns else case.norm_stab)
    if latitude and longitude and location_correct:
        case.latitude = latitude
        case.longitude = longitude

    # Roll the case forward so it re-surfaces on the right day and sinks in today's view.
    try:
        pd = datetime.strptime(ptp_date, "%Y-%m-%d").date() if ptp_date else None
    except ValueError:
        pd = None
    if case.paid_status == "PAID" and Decimal(case.pending_amount or 0) <= 0:
        case.follow_up_date = None                              # settled → out of the queue
    else:
        # unpaid / partial after a visit → carry to the promised date, else next working day
        case.follow_up_date = pd or (datetime.now(IST).date() + timedelta(days=1))
        if pd or (disposition or "").upper() in ("PTP", "RTP"):
            case.status = "ptp"
    audit.record(db, user, "visit", case, new=disposition,
                 detail=f"Field visit — {disposition or 'logged'}"
                        + (f", paid ₹{amt}" if (paid and amt > 0) else "")
                        + (f", {int(dist_m)}m from case" if dist_m else ""))
    audit.stamp_case(case, user)
    db.commit()
    db.refresh(visit)
    from .realtime import notify_data_changed
    notify_data_changed(case.bank, case.product)
    visit.photo_path = resolve_photo(visit.photo_path)
    return visit


@router.get("/officer/{officer_id}/day")
def officer_day(officer_id: int, date: str | None = None, db: Session = Depends(get_db),
                actor: models.User = Depends(get_current_user)):
    """A field officer's visits for a given day (IST), each joined to its case with the
    payment collected and the full log — for the live-map tags and the day Excel view."""
    u = db.query(models.User).filter(models.User.id == officer_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Officer not found")
    if actor.role == "manager" and u.branch != actor.branch:
        raise HTTPException(status_code=403, detail="Not in your branch")
    if actor.role in ("fos", "telecaller", "backend") and actor.id != u.id:
        raise HTTPException(status_code=403, detail="Not allowed")

    try:
        d = date and datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        d = None
    if not d:
        d = datetime.now(IST).date()
    start = datetime.combine(d, time.min, tzinfo=IST).astimezone(timezone.utc)
    end = start + timedelta(days=1)

    visits = (db.query(models.Visit)
              .filter(models.Visit.officer_id == officer_id,
                      models.Visit.created_at >= start, models.Visit.created_at < end)
              .order_by(models.Visit.created_at.asc()).all())
    cids = [v.case_id for v in visits]
    cases = {c.id: c for c in db.query(models.Case).filter(models.Case.id.in_(cids)).all()} if cids else {}

    def as_ist(dt):
        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(IST).strftime("%H:%M") if dt else ""

    out = []
    for v in visits:
        c = cases.get(v.case_id)
        out.append({
            "id": v.id, "case_id": v.case_id, "time": as_ist(v.created_at),
            "lat": v.latitude, "lng": v.longitude,
            "customer": c.customer_name if c else None, "account": c.account_no if c else None,
            "bank": c.bank if c else None, "product": c.product if c else None,
            "phone": c.phone if c else None, "address": c.address if c else None,
            "disposition": v.disposition, "paid": bool(v.paid),
            "amount": float(v.amount_collected or 0), "norm_stab": (c.norm_stab if c else None),
            "person_moved": bool(v.person_moved),
            "location_correct": v.location_correct,
            "off_location": (v.distance_from_case_m is not None and v.distance_from_case_m > 300),
            "distance_m": v.distance_from_case_m, "note": v.note,
            "photo": resolve_photo(v.photo_path),
        })
    return {"officer": {"id": u.id, "name": u.name, "branch": u.branch}, "date": d.isoformat(),
            "count": len(out), "collected": round(sum(x["amount"] for x in out), 2), "visits": out}


@router.get("/case/{case_id}", response_model=list[schemas.VisitOut])
def visits_for_case(case_id: int, db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)):
    q = db.query(models.Visit).filter(models.Visit.case_id == case_id)
    if user.role == "fos":
        q = q.filter(models.Visit.officer_id == user.id)
    rows = q.order_by(models.Visit.created_at.desc()).all()
    for v in rows:
        v.photo_path = resolve_photo(v.photo_path)
    return rows
