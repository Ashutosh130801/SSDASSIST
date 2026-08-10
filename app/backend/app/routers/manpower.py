"""Manpower / HR directory.

- Admin, Head Office and HR can browse the full employee directory (role + location
  filters) and download it as Excel.
- Every employee can view their own E-ID profile and complete a ONE-TIME self edit
  (add photo + personal details) right after first login; after that it locks and only
  admin/HR can change it.
"""
import io
import os
import zipfile

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import models, audit
from ..database import get_db
from ..deps import get_current_user, require_roles
from ..storage import save_photo, resolve as resolve_photo, read_bytes

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
        "also_team_lead": bool(u.also_team_lead), "tl_emp_code": u.tl_emp_code,
        "all_roles": _all_roles(u), "all_ids": _all_ids(u),
    }


_ROLE_LABELS = {"telecaller": "Tele-calling Agent", "fos": "Field Agent", "teamlead": "Team Lead",
                "manager": "Collections Manager", "admin": "Administrator", "headoffice": "Head Office",
                "backend": "Back-office Official", "hr": "HR", "it": "IT", "staff": "Staff"}


def _all_roles(u) -> str:
    """Both roles for a dual-role user, e.g. 'Field Agent + Team Lead'."""
    label = _ROLE_LABELS.get(u.role, (u.role or "").title())
    if getattr(u, "also_team_lead", False) and u.role != "teamlead":
        return f"{label} + Team Lead"
    return label


def _all_ids(u) -> str:
    """Both IDs for a dual-role user, e.g. 'FO012 / TL014'."""
    ids = [u.emp_code] if u.emp_code else []
    if getattr(u, "also_team_lead", False) and getattr(u, "tl_emp_code", None):
        ids.append(u.tl_emp_code)
    return " / ".join(ids)


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
    cols = [("emp_code", "Emp Code"), ("tl_emp_code", "Team Lead ID"), ("all_roles", "Roles"),
            ("hr_ref", "HR Ref"), ("name", "Name"),
            ("role", "Primary Role"), ("designation", "Designation"), ("location", "Location"),
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
    if role == "admin" and user.role != "admin":
        raise HTTPException(status_code=403,
                            detail="Only an administrator can create another Administrator.")
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
    old_role = u.role
    new_role = (body.get("role") or "").strip()
    if new_role:
        # Only an admin may grant the admin role, or change an existing admin's role.
        if (new_role == "admin" or old_role == "admin") and user.role != "admin":
            raise HTTPException(status_code=403,
                                detail="Only an administrator can assign or change the Administrator role.")
        u.role = new_role
    # Optional: when the role changes, regenerate the emp code so its prefix matches the new
    # role (e.g. FO001 → TL003). Off by default — existing sheet references keep the old code.
    if body.get("regen_code") and u.role != old_role:
        from .users import generate_emp_code
        u.emp_code = generate_emp_code(db, u.role)
    # Dual role: grant/revoke the team-lead hat on a caller/FOS. Granting keeps their primary
    # role + emp_code and issues a second team-lead ID (tl_emp_code) if they don't have one.
    if "also_team_lead" in body:
        grant = bool(body["also_team_lead"])
        u.also_team_lead = grant
        if grant and u.role != "teamlead" and not u.tl_emp_code:
            from .users import generate_emp_code
            u.tl_emp_code = generate_emp_code(db, "teamlead")
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


# ---------------------------------------------------------------------------
# HR document vault — upload / list / download / zip per employee.
# ---------------------------------------------------------------------------
DOC_TYPES = [
    ("pan", "PAN card"),
    ("aadhaar", "Aadhaar card"),
    ("photo", "Photo"),
    ("signature", "Signature (white paper)"),
    ("pvc", "PVC"),
    ("dra", "DRA certificate"),
    ("cibil", "CIBIL report (Paisabazaar)"),
    ("bank_details", "Bank account details"),
    ("reference", "Reference contact details"),
    ("whatsapp", "WhatsApp no. (not PhonePe-linked)"),
    ("email", "Email ID proof"),
]
_DOC_KEYS = {k for k, _ in DOC_TYPES}


@router.get("/doc-types")
def doc_types(user: models.User = Depends(require_roles(*HR_ROLES))):
    return [{"key": k, "label": lbl} for k, lbl in DOC_TYPES]


@router.get("/{emp_id}/documents")
def list_documents(emp_id: int, db: Session = Depends(get_db),
                   user: models.User = Depends(require_roles(*HR_ROLES))):
    rows = (db.query(models.EmployeeDocument)
            .filter(models.EmployeeDocument.user_id == emp_id)
            .order_by(models.EmployeeDocument.uploaded_at.desc()).all())
    latest = {}
    for d in rows:                       # keep the most-recent per type
        latest.setdefault(d.doc_type, d)
    return [{"id": d.id, "doc_type": d.doc_type, "filename": d.filename,
             "url": resolve_photo(d.ref),
             "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None}
            for d in latest.values()]


@router.post("/{emp_id}/documents")
async def upload_document(emp_id: int, doc_type: str = Form(...), file: UploadFile = File(...),
                          db: Session = Depends(get_db),
                          user: models.User = Depends(require_roles(*HR_ROLES))):
    emp = db.query(models.User).filter(models.User.id == emp_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    if doc_type not in _DOC_KEYS:
        raise HTTPException(status_code=400, detail="Unknown document type")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    ref = save_photo(content, filename=file.filename or doc_type,
                     content_type=file.content_type or "application/octet-stream", folder="documents")
    # Replace any prior file of this type (keep one current per type).
    db.query(models.EmployeeDocument).filter(
        models.EmployeeDocument.user_id == emp_id,
        models.EmployeeDocument.doc_type == doc_type).delete()
    d = models.EmployeeDocument(user_id=emp_id, doc_type=doc_type, filename=file.filename,
                                ref=ref, content_type=file.content_type, uploaded_by=user.id)
    db.add(d)
    audit.record(db, user, "staff_update", None, entity_type="staff", target_user_id=emp_id,
                 detail=f"Uploaded document '{doc_type}' for {emp.name}")
    db.commit()
    db.refresh(d)
    return {"id": d.id, "doc_type": d.doc_type, "filename": d.filename, "url": resolve_photo(d.ref)}


@router.get("/{emp_id}/documents.zip")
def documents_zip(emp_id: int, db: Session = Depends(get_db),
                  user: models.User = Depends(require_roles(*HR_ROLES))):
    emp = db.query(models.User).filter(models.User.id == emp_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    rows = db.query(models.EmployeeDocument).filter(models.EmployeeDocument.user_id == emp_id).all()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for d in rows:
            data = read_bytes(d.ref)
            if data is None:
                continue
            ext = os.path.splitext(d.filename or "")[1] or ""
            z.writestr(f"{d.doc_type}{ext}", data)
    buf.seek(0)
    safe = "".join(ch for ch in (emp.name or f"emp{emp_id}")
                   if ch.isalnum() or ch in " _-").strip().replace(" ", "_") or f"emp{emp_id}"
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{safe}.zip"'})


@router.get("/{emp_id}/documents/{doc_id}/download")
def download_document(emp_id: int, doc_id: int, db: Session = Depends(get_db),
                      user: models.User = Depends(require_roles(*HR_ROLES))):
    d = (db.query(models.EmployeeDocument)
         .filter(models.EmployeeDocument.id == doc_id, models.EmployeeDocument.user_id == emp_id).first())
    if not d:
        raise HTTPException(status_code=404, detail="Document not found")
    data = read_bytes(d.ref)
    if data is None:
        raise HTTPException(status_code=404, detail="File missing from storage")
    return StreamingResponse(io.BytesIO(data), media_type=d.content_type or "application/octet-stream",
                             headers={"Content-Disposition": f'attachment; filename="{d.filename or d.doc_type}"'})


@router.delete("/{emp_id}/documents/{doc_id}")
def delete_document(emp_id: int, doc_id: int, db: Session = Depends(get_db),
                    user: models.User = Depends(require_roles(*HR_ROLES))):
    n = (db.query(models.EmployeeDocument)
         .filter(models.EmployeeDocument.id == doc_id, models.EmployeeDocument.user_id == emp_id)
         .delete())
    db.commit()
    return {"deleted": n}


# ---------------------------------------------------------------------------
# Offer-letter generator — preview (editable HTML) + email to the candidate.
# ---------------------------------------------------------------------------
def _esc(x) -> str:
    return str("" if x is None else x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _offer_letter_html(emp, d: dict) -> str:
    from datetime import date as _date
    from ..config import get_settings
    s = get_settings()
    company = d.get("company") or s.company_name
    today = d.get("date") or _date.today().strftime("%d %B %Y")
    name = d.get("name") or emp.name or "[Employee Name]"
    designation = d.get("designation") or emp.designation or "[Designation]"
    department = d.get("department") or "[Department]"
    location = d.get("location") or emp.location or emp.branch or "[Location]"
    joining = d.get("joining_date") or "[Date of Joining]"
    ctc = d.get("ctc") or emp.ctc or "[Annual CTC]"
    # Salary breakup: list of {component, monthly, annual}. HR edits these placeholders.
    salary = d.get("salary") or [
        {"component": "Basic", "monthly": "[____]", "annual": "[____]"},
        {"component": "HRA", "monthly": "[____]", "annual": "[____]"},
        {"component": "Special Allowance", "monthly": "[____]", "annual": "[____]"},
        {"component": "Gross Salary", "monthly": "[____]", "annual": "[____]"},
        {"component": "Deductions (PF/ESI/PT)", "monthly": "[____]", "annual": "[____]"},
        {"component": "Net Take-home", "monthly": "[____]", "annual": "[____]"},
    ]
    sal_rows = "".join(
        f"<tr><td>{_esc(r.get('component'))}</td>"
        f"<td style='text-align:right'>{_esc(r.get('monthly'))}</td>"
        f"<td style='text-align:right'>{_esc(r.get('annual'))}</td></tr>" for r in salary)
    terms = d.get("terms") or [
        "This offer is contingent on successful verification of the documents submitted.",
        "You will be on probation for the first 6 months from the date of joining.",
        "Your employment is governed by the company's policies, which may be amended from time to time.",
        "Either party may terminate this employment by serving 30 days' written notice.",
    ]
    terms_html = "".join(f"<li>{_esc(t)}</li>" for t in terms)
    return f"""<div style="font-family:Georgia,serif;color:#111;max-width:720px;line-height:1.6">
  <div style="text-align:center;border-bottom:2px solid #1D4ED8;padding-bottom:10px;margin-bottom:18px">
    <div style="font-size:22px;font-weight:700;color:#1D4ED8">{_esc(company)}</div>
    <div style="font-size:12px;color:#555">Offer of Employment</div>
  </div>
  <div style="text-align:right;font-size:13px">Date: {_esc(today)}</div>
  <p>Dear <b>{_esc(name)}</b>,</p>
  <p>We are pleased to offer you the position of <b>{_esc(designation)}</b> in the
     <b>{_esc(department)}</b> department at <b>{_esc(location)}</b>, with a date of joining of
     <b>{_esc(joining)}</b>. Your annual cost to company (CTC) will be <b>{_esc(ctc)}</b>.</p>
  <h3 style="color:#1D4ED8;margin:18px 0 6px">Salary Break-up</h3>
  <table style="border-collapse:collapse;width:100%;font-family:Arial,sans-serif;font-size:13px">
    <thead><tr style="background:#EEF3FB">
      <th style="border:1px solid #cbd5e1;padding:6px 8px;text-align:left">Component</th>
      <th style="border:1px solid #cbd5e1;padding:6px 8px;text-align:right">Monthly (₹)</th>
      <th style="border:1px solid #cbd5e1;padding:6px 8px;text-align:right">Annual (₹)</th>
    </tr></thead>
    <tbody>{sal_rows}</tbody>
  </table>
  <h3 style="color:#1D4ED8;margin:18px 0 6px">Terms &amp; Conditions</h3>
  <ol style="font-family:Arial,sans-serif;font-size:13px">{terms_html}</ol>
  <p>We look forward to welcoming you to the {_esc(company)} team. Please sign and return a copy
     of this letter as a token of your acceptance.</p>
  <div style="margin-top:34px;display:flex;justify-content:space-between;font-size:13px">
    <div>_____________________<br/>For {_esc(company)}<br/>(HR / Authorised Signatory)</div>
    <div>_____________________<br/>{_esc(name)}<br/>(Candidate's acceptance)</div>
  </div>
</div>"""


def _send_email(to: str, subject: str, html: str, attachments=None):
    from ..config import get_settings
    s = get_settings()
    if not s.smtp_host or not s.smtp_user:
        raise HTTPException(status_code=400,
                            detail="Email is not configured. Set SMTP_HOST, SMTP_USER and SMTP_PASSWORD.")
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.application import MIMEApplication
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = s.smtp_from or s.smtp_user
    msg["To"] = to
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText("Please open this email in an HTML-capable client.", "plain"))
    alt.attach(MIMEText(html, "html"))
    msg.attach(alt)
    for fn, data, _ctype in (attachments or []):
        part = MIMEApplication(data)
        part.add_header("Content-Disposition", "attachment", filename=fn)
        msg.attach(part)
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as server:
        server.starttls()
        server.login(s.smtp_user, s.smtp_password)
        server.sendmail(msg["From"], [to], msg.as_string())


@router.post("/offer-letter")
def offer_letter_preview(body: dict = Body(...), db: Session = Depends(get_db),
                         user: models.User = Depends(require_roles(*HR_ROLES))):
    emp = db.query(models.User).filter(models.User.id == body.get("emp_id")).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return {"html": _offer_letter_html(emp, body), "email": emp.email}


@router.post("/offer-letter/email")
def offer_letter_email(body: dict = Body(...), db: Session = Depends(get_db),
                       user: models.User = Depends(require_roles(*HR_ROLES))):
    emp = db.query(models.User).filter(models.User.id == body.get("emp_id")).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    to = (body.get("to") or emp.email or "").strip()
    if not to:
        raise HTTPException(status_code=400, detail="No recipient email — add the employee's email first")
    html = body.get("html") or _offer_letter_html(emp, body)
    subject = body.get("subject") or f"Offer of Employment — {emp.name}"
    safe = "".join(ch for ch in (emp.name or "candidate") if ch.isalnum() or ch in " _-").strip().replace(" ", "_")
    full = f"<html><body>{html}</body></html>"
    _send_email(to, subject, full, attachments=[(f"OfferLetter_{safe}.html", full.encode("utf-8"), "text/html")])
    audit.record(db, user, "staff_update", None, entity_type="staff", target_user_id=emp.id,
                 detail=f"Emailed offer letter to {to}")
    db.commit()
    return {"sent": True, "to": to}
