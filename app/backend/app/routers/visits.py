import os
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user, require_roles
from ..storage import save_photo, resolve as resolve_photo

router = APIRouter(prefix="/api/visits", tags=["visits"])


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
    disposition: str | None = Form(None),
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
    if latitude and longitude and location_correct:
        case.latitude = latitude
        case.longitude = longitude
    db.commit()
    db.refresh(visit)
    visit.photo_path = resolve_photo(visit.photo_path)
    return visit


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
