"""Manpower / HR directory.

- Admin, Head Office and HR can browse the full employee directory (role + location
  filters) and download it as Excel.
- Every employee can view their own E-ID profile and complete a ONE-TIME self edit
  (add photo + personal details) right after first login; after that it locks and only
  admin/HR can change it.
"""
import io

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import models, audit
from ..database import get_db
from ..deps import get_current_user, require_roles
from ..storage import save_photo, resolve as resolve_photo

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
        "photo_url": resolve_photo(u.photo_url), "is_active": u.is_active,
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
        s = q.lower().strip()
        def _hit(e):
            return any(s in (str(e.get(k) or "")).lower() for k in
                       ("name", "emp_code", "email", "phone", "designation",
                        "location", "branch", "hr_ref", "role"))
        out = [e for e in out if _hit(e)]
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


# Fields an HR user can set when adding an employee (mirrors the manpower sheet).
_ADD_FIELDS = (
    "phone", "designation", "location", "branch", "hr_ref", "gender", "blood_group",
    "marital_status", "emergency_contact", "emergency_name", "emergency_relation",
    "aadhar_number", "pan_number", "bank_holder", "bank_account", "ifsc_code", "bank_name",
    "current_address", "aadhar_address", "employment_type", "photo_url", "ctc",
)
_STARTER_PASSWORD = "Ssd@2026"


@router.post("")
def add_employee(body: dict = Body(...), db: Session = Depends(get_db),
                 user: models.User = Depends(require_roles("admin", "headoffice", "hr"))):
    """Add a new employee to the directory with full HR details. Creates a login with a
    starter password (they set their own on first sign-in) and a role-wise emp code."""
    from ..security import hash_password
    from .users import generate_emp_code
    from datetime import datetime as _dt

    name = (body.get("name") or "").strip()
    email = (body.get("email") or "").strip().lower()
    role = (body.get("role") or "").strip()
    if not name or not email or not role:
        raise HTTPException(status_code=400, detail="Name, login email and role are required")
    if db.query(models.User).filter(models.User.email == email).first():
        raise HTTPException(status_code=400, detail="That login email is already registered")

    u = models.User(
        name=name, email=email, role=role,
        emp_code=generate_emp_code(db, role),
        hashed_password=hash_password(body.get("password") or _STARTER_PASSWORD),
        must_change_password=True, profile_completed=True, is_active=True,
    )
    for k in _ADD_FIELDS:
        v = body.get(k)
        if v not in (None, ""):
            setattr(u, k, v)
    for dk in ("dob", "joining_date"):
        dv = body.get(dk)
        if dv:
            try:
                setattr(u, dk, _dt.strptime(str(dv)[:10], "%Y-%m-%d").date())
            except ValueError:
                pass
    db.add(u)
    db.flush()
    audit.record(db, user, "staff_create", None, entity_type="staff", target_user_id=u.id,
                 detail=f"Added employee {name} ({role}) — {u.emp_code}")
    db.commit()
    db.refresh(u)
    return _emp(u)


@router.get("/me")
def my_profile(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """The signed-in employee's own profile / E-ID data."""
    return _emp(user)


@router.post("/me/photo")
async def upload_my_photo(file: UploadFile = File(...), db: Session = Depends(get_db),
                         user: models.User = Depends(get_current_user)):
    """Upload / replace the signed-in employee's profile photo. Allowed ANY time (not
    subject to the one-time profile lock), so staff can update their picture whenever."""
    ct = (file.content_type or "").lower()
    if not ct.startswith("image/"):
        raise HTTPException(status_code=400, detail="Please upload an image file")
    content = await file.read()
    if len(content) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image too large (max 8 MB)")
    ref = save_photo(content, file.filename or "photo.jpg", ct, folder="profiles")
    user.photo_url = ref
    audit.record(db, user, "profile_update", None, entity_type="staff", detail="Updated profile photo")
    db.commit()
    return {"ok": True, "photo_url": resolve_photo(ref)}


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


# Registered AFTER the /me routes so "/me" is never captured as an emp_id.
@router.patch("/{emp_id}")
def edit_employee(emp_id: int, body: dict = Body(...), db: Session = Depends(get_db),
                  user: models.User = Depends(require_roles("admin", "headoffice", "hr"))):
    """HR / admin / head office edits any employee's directory details. Only the fields sent
    are changed. Can also reset the person's password (forces a change on next login)."""
    from datetime import datetime as _dt
    u = db.query(models.User).filter(models.User.id == emp_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Employee not found")

    new_email = (body.get("email") or "").strip().lower()
    if new_email and new_email != (u.email or "").lower():
        if db.query(models.User).filter(models.User.email == new_email,
                                        models.User.id != u.id).first():
            raise HTTPException(status_code=400, detail="That login email is already registered")
        u.email = new_email
    if (body.get("name") or "").strip():
        u.name = body["name"].strip()
    if (body.get("role") or "").strip():
        u.role = body["role"].strip()
    if "is_active" in body:
        u.is_active = bool(body["is_active"])
    for k in _ADD_FIELDS:
        if k in body:
            v = body.get(k)
            setattr(u, k, v if v not in ("",) else None)
    for dk in ("dob", "joining_date"):
        if dk in body:
            dv = body.get(dk)
            if dv:
                try:
                    setattr(u, dk, _dt.strptime(str(dv)[:10], "%Y-%m-%d").date())
                except ValueError:
                    pass
            else:
                setattr(u, dk, None)
    if body.get("password"):
        from ..security import hash_password
        u.hashed_password = hash_password(body["password"])
        u.must_change_password = True
    audit.record(db, user, "staff_update", None, entity_type="staff", target_user_id=u.id,
                 detail=f"Edited employee {u.name} ({u.emp_code})")
    db.commit()
    db.refresh(u)
    return _emp(u)


# tiny local helper to avoid importing func at module top for one use
def func_lower(col):
    from sqlalchemy import func
    return func.lower(col)
