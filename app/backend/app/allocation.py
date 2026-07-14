"""Automatic case allocation.

Strategy (per user's choice): match FO's assigned pincodes to the case pincode
first; if no pincode match, fall back to nearest FO by GPS distance to the case
location. Telecaller allocation is round-robin balanced by current open load.
"""
import math
from typing import List, Optional

from sqlalchemy.orm import Session

from . import models


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _bank_ok(user: models.User, bank: Optional[str]) -> bool:
    if not bank or not user.banks:
        return True
    return bank.upper() in [b.upper() for b in user.banks]


def choose_fos(db: Session, case: models.Case, fos_users: List[models.User]) -> Optional[models.User]:
    candidates = [u for u in fos_users if _bank_ok(u, case.bank)]
    if not candidates:
        candidates = fos_users
    if not candidates:
        return None

    # 1) pincode match
    if case.pincode:
        pin_matches = [u for u in candidates if u.assigned_pincodes and case.pincode in u.assigned_pincodes]
        if pin_matches:
            pin_matches.sort(key=lambda u: _open_load(db, u.id))
            case.allocation_reason = f"pincode {case.pincode}"
            return pin_matches[0]

    # 2) nearest by GPS
    if case.latitude is not None and case.longitude is not None:
        geo = [u for u in candidates if u.home_lat is not None and u.home_lng is not None]
        if geo:
            geo.sort(key=lambda u: haversine_km(case.latitude, case.longitude, u.home_lat, u.home_lng))
            nearest = geo[0]
            d = haversine_km(case.latitude, case.longitude, nearest.home_lat, nearest.home_lng)
            case.allocation_reason = f"nearest FO ~{d:.1f}km"
            return nearest

    # 3) fallback: least loaded
    candidates.sort(key=lambda u: _open_load(db, u.id))
    case.allocation_reason = "load-balanced"
    return candidates[0]


def _open_load(db: Session, fos_id: int) -> int:
    return (
        db.query(models.Case)
        .filter(models.Case.assigned_fos_id == fos_id)
        .filter(models.Case.status.notin_(["paid", "closed"]))
        .count()
    )


def _caller_load(db: Session, caller_id: int) -> int:
    return (
        db.query(models.Case)
        .filter(models.Case.assigned_caller_id == caller_id)
        .filter(models.Case.status.notin_(["paid", "closed"]))
        .count()
    )


def choose_caller(db: Session, case: models.Case, callers: List[models.User]) -> Optional[models.User]:
    candidates = [u for u in callers if _bank_ok(u, case.bank)] or callers
    if not candidates:
        return None
    candidates.sort(key=lambda u: _caller_load(db, u.id))
    return candidates[0]


def run_allocation(db: Session, only_unallocated: bool = True, bank: Optional[str] = None) -> dict:
    fos_users = db.query(models.User).filter(models.User.role == "fos", models.User.is_active == True).all()
    callers = db.query(models.User).filter(models.User.role == "telecaller", models.User.is_active == True).all()

    q = db.query(models.Case)
    if bank:
        q = q.filter(models.Case.bank == bank)
    if only_unallocated:
        q = q.filter((models.Case.assigned_fos_id.is_(None)) | (models.Case.assigned_caller_id.is_(None)))
    q = q.filter(models.Case.status.notin_(["paid", "closed"]))

    allocated_fos = 0
    allocated_caller = 0
    for case in q.all():
        if case.assigned_fos_id is None and fos_users:
            fos = choose_fos(db, case, fos_users)
            if fos:
                case.assigned_fos_id = fos.id
                if case.status == "new":
                    case.status = "allocated"
                allocated_fos += 1
        if case.assigned_caller_id is None and callers:
            caller = choose_caller(db, case, callers)
            if caller:
                case.assigned_caller_id = caller.id
                allocated_caller += 1
    db.commit()
    return {"fos_allocated": allocated_fos, "caller_allocated": allocated_caller}
