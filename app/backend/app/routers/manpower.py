"""Manpower / HR directory.

- Admin, Head Office and HR can browse the full employee directory (role + location
  filters) and download it as Excel.
- Every employee can view their own E-ID profile and complete a ONE-TIME self edit
  (add photo + personal details) right after first login; after that it locks and only
  admin/HR can change it.
"""
import io

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import models, audit
from ..database import get_db
from ..deps import get_current_user, require_roles

router = APIRouter(prefix="/api/manpower", tags=["manpower"])

HR_ROLES = ("admin", "headoffice", "hr")

# Fields an employee may set during their one-time self edit.
SELF_EDITABLE = {
    "phone", "gender", "dob", "blood_group", "marital_status", "emergency_contact",
    "emergency_name", "emergency_relation", "current_address", "aadhar_number",
    "pan_number", "bank_holder", "bank_account", "ifsc_code", "bank_name",
    "aadhar_address", "photo_url", "address",
}


def _emp(u: models.User) -> dict:
    return {
        "id": u.id, "emp_code": u.emp_code, "hr_ref": u.hr_ref, "name": u.name,
        "email": u.email, "phone": u.phone, "role": u.role, "designation": u.designation,
        "location": u.location, "branch": u.branch, "gender": u.gender,
        "dob": u.dob.isoformat() if u.dob else None,
        "joining_date": u.joining_date.isoformat() if u.joining_date else None,
        "blood_group": u.blood_group, "marital_status": u.marital_status,
        "emergency_contact": u.emergency_contact, "emergency_name": u.emergency_name,
        "emergency_relation": u.emergency_relation, "dra_status": u.dra_status,
        "pvc_status": u.pvc_status, "aadhar_number": u.aadhar_number, "pan_number": u.pan_number,
        "bank_holder": u.bank_holder, "bank_account": u.bank_account, "ifsc_code": u.ifsc_code,
        "bank_name": u.bank_name, "current_address": u.current_address,
        "aadhar_address": u.aadhar_address, "rent_own": u.rent_own, "ctc": u.ctc,
        "photo_url": u.photo_url, "is_active": u.is_active,
        "profile_completed": bool(u.profile_completed),
    }


@router.get("/filters")
def filters(db: Session = Depends(get_db), user: models.User = Depends(require_roles(*HR_ROLES))):
    us = db.query(models.User.role, models.User.location).all()
    roles = sorted({r for r, _ in us if r})
    locations = sorted({(loc or "").strip() for _, loc in us if loc and loc.strip()})
    return {"roles": roles, "locations": locations}


@router.get("")
def list_manpower(role: str | None = None, location: str | None = None, q: str | None = None,
                  db: Session = Depends(get_db), user: models.User = Depends(require_roles(*HR_ROLES))):
    """The full employee directory with role / location / text filters."""
    query = db.query(models.User)
    if role:
        query = query.filter(models.User.role == role)
    if location:
        query = query.filter(func_lower(models.User.location) == location.strip().lower())
    rows = query.order_by(models.User.name).all()
    out = [_emp(u) for u in rows]
    if q:
        s = q.lower()
        out = [e for e in out if s in (e["name"] or "").lower() or s in (e["emp_code"] or "").lower()
               or s in (e["email"] or "").lower() or s in (e["phone"] or "")]
    return out


@router.get("/download")
def download(role: str | None = None, location: str | None = None,
             db: Session = Depends(get_db), user: models.User = Depends(require_roles(*HR_ROLES))):
    import openpyxl
    from openpyxl.styles import Font, PatternFill
    query = db.query(models.User)
    if role:
        query = query.filter(models.User.role == role)
    if location:
        query = query.filter(func_lower(models.User.location) == location.strip().lower())
    rows = query.order_by(models.User.role, models.User.name).all()

    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Manpower"
    cols = [("emp_code", "Emp Code"), ("hr_ref", "HR Ref"), ("name", "Name"),
            ("role", "Role"), ("designation", "Designation"), ("location", "Location"),
            ("branch", "Branch"), ("phone", "Phone"), ("email", "Email"), ("gender", "Gender"),
            ("dob", "DOB"), ("joining_date", "DOJ"), ("blood_group", "Blood"),
            ("marital_status", "Marital"), ("emergency_contact", "Emergency No"),
            ("emergency_name", "Emergency Name"), ("emergency_relation", "Relation"),
            ("aadhar_number", "Aadhaar"), ("pan_number", "PAN"), ("bank_holder", "Bank Holder"),
            ("bank_account", "Account"), ("ifsc_code", "IFSC"), ("bank_name", "Bank"),
            ("current_address", "Current Address"), ("rent_own", "Rent/Own")]
    ws.append([c[1] for c in cols])
    for i in range(1, len(cols) + 1):
        cell = ws.cell(row=1, column=i); cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="2563EB")
    for u in rows:
        e = _emp(u)
        ws.append([e.get(c[0]) for c in cols])
    ws.freeze_panes = "A2"
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return StreamingResponse(buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=SSDE_manpower.xlsx"})


@router.get("/me")
def my_profile(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """The signed-in employee's own profile / E-ID data."""
    return _emp(user)


@router.patch("/me")
def update_my_profile(body: dict = Body(...), db: Session = Depends(get_db),
                      user: models.User = Depends(get_current_user)):
    """One-time self edit right after first login. Locks once completed (admin/HR can
    still edit via user management). Admin/HR are not limited by the one-time lock."""
    is_hr = user.role in HR_ROLES
    if user.profile_completed and not is_hr:
        raise HTTPException(status_code=403,
                            detail="Your profile has already been completed. Ask HR/admin for further changes.")
    changed = 0
    for k, v in body.items():
        if k not in SELF_EDITABLE:
            continue
        if k in ("dob",) and v:
            from datetime import datetime as _dt
            try:
                v = _dt.strptime(str(v)[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
        setattr(user, k, v)
        changed += 1
    if not is_hr:
        user.profile_completed = True    # lock after the one-time completion
    audit.record(db, user, "profile_update", None, entity_type="staff",
                 detail=f"{'HR' if is_hr else 'Self'} profile update ({changed} fields)")
    db.commit()
    return {"ok": True, "profile_completed": bool(user.profile_completed)}


# tiny local helper to avoid importing func at module top for one use
def func_lower(col):
    from sqlalchemy import func
    return func.lower(col)
