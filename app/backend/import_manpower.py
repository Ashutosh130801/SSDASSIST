"""Create staff logins from the SSDE manpower sheet + the generated credentials sheet.

Run ONCE on the server (after deploying the manpower fields + new roles):

    python import_manpower.py "SSDE Man power.xlsx" "SSDE_login_credentials.xlsx"

- The manpower sheet supplies every HR detail (designation, DOB, PAN, bank, address...).
- The credentials sheet supplies the login email + password + role-wise Emp Code that
  were handed to the team, so the live accounts match that sheet exactly.
Matching between the two sheets is by the official employee id (SSD ID / HR Ref).
Existing accounts (same email) are updated, not duplicated.
"""
import sys
from datetime import datetime

import openpyxl

from app.database import SessionLocal
from app import models
from app.security import hash_password


def _s(v):
    return str(v).strip() if v not in (None, "") else None


# Location -> branch. Everyone EXCEPT field officers is placed in a city/region branch;
# FOS are location-based (no branch), so branch managers see them via the cases they work.
_LOC_BRANCH = {
    "visakhapatnam": "Visakhapatnam", "vizag": "Visakhapatnam", "vishakapatnam": "Visakhapatnam",
    "vijayawada": "Vijayawada", "vijaywada": "Vijayawada",
    "hyderabad": "Hyderabad",
    "telangana": "Telangana",
    "kadapa": "Kadapa", "cuddapah": "Kadapa",
    "guntur": "Guntur", "tirupati": "Tirupati", "nellore": "Nellore",
    "warangal": "Warangal", "karimnagar": "Karimnagar", "east-west": "East-West",
}


def _branch_for(location):
    d = (location or "").strip().lower()
    if not d:
        return None
    return _LOC_BRANCH.get(d, (location or "").strip().title())


def _date(v):
    if not v:
        return None
    if isinstance(v, datetime):
        return v.date()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(v)[:10], fmt).date()
        except ValueError:
            continue
    return None


def _rows(path, sheet=None):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[sheet] if sheet else wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    hdr = [str(c).strip() if c else "" for c in rows[0]]
    return hdr, rows[1:]


def main(manpower_path, creds_path):
    # 1) credentials sheet -> by HR Ref: {emp_code, email, password, role, ...}
    ch, crows = _rows(creds_path)
    ci = {n: ch.index(n) for n in ch}
    creds = {}
    for r in crows:
        if not r:
            continue
        ref = _s(r[ci["HR Ref (SSD ID)"]])
        if not ref:
            continue
        pw_col = "Start Password" if "Start Password" in ci else "Password"
        creds[ref] = {
            "emp_code": _s(r[ci["Emp Code (login ID)"]]),
            "email": _s(r[ci["Login (email)"]]),
            "password": _s(r[ci[pw_col]]),
            "role": _s(r[ci["Role"]]),
        }

    # 2) manpower sheet -> full HR record per employee, matched to creds by EMP_ID
    mh, mrows = _rows(manpower_path, "EMPL")
    idx = {n: mh.index(n) for n in mh}

    def g(r, col):
        return _s(r[idx[col]]) if col in idx else None

    db = SessionLocal()
    created = updated = skipped = 0
    for r in mrows:
        if not r:
            continue
        ref = g(r, "EMP_ID")
        c = creds.get(ref)
        if not c or not c["email"]:
            skipped += 1
            continue
        u = db.query(models.User).filter(models.User.email == c["email"]).first()
        is_new = u is None
        if is_new:
            u = models.User(email=c["email"], role=c["role"])
            db.add(u)
        u.name = g(r, "Employee Name") or u.name
        u.role = c["role"]
        u.emp_code = c["emp_code"]
        u.hr_ref = ref
        if is_new or not u.hashed_password:
            u.hashed_password = hash_password(c["password"])
            u.must_change_password = True     # force a new password on first login
        u.phone = g(r, "Contact Number")
        u.designation = g(r, "Designation")
        loc = g(r, "Location")
        u.location = (loc or "").title() or None
        # FOS are location-based (no branch); everyone else joins their city/region branch.
        u.branch = None if c["role"] == "fos" else _branch_for(loc)
        u.gender = g(r, "Gender")
        u.blood_group = g(r, "BLOOD GROUP")
        u.marital_status = g(r, "Status")
        u.ctc = g(r, "CTC")
        u.joining_date = _date(r[idx["DOJ"]]) if "DOJ" in idx else None
        u.dob = _date(r[idx["DOB"]]) if "DOB" in idx else None
        u.emergency_contact = g(r, "Emergency Contact Number")
        u.emergency_name = g(r, "ER Contact Name")
        u.emergency_relation = g(r, "Relation")
        u.dra_status = g(r, "DRA Status")
        u.pvc_status = g(r, "PVC Status")
        u.aadhar_number = g(r, "AadharNumber")
        u.pan_number = g(r, "PAN Number")
        u.bank_holder = g(r, "Bank Accountant Holder Name")
        u.bank_account = g(r, "Bank Account Number")
        u.ifsc_code = g(r, "IFSC code")
        u.bank_name = g(r, "BANK NAME")
        u.aadhar_address = g(r, "Aadhar address")
        u.current_address = g(r, "Current address")
        u.rent_own = g(r, "Rent-Own")
        u.is_active = True
        if is_new:
            u.employment_type = "Full-time"
            u.profile_completed = False
        created += int(is_new)
        updated += int(not is_new)
    db.commit()
    print(f"Done. Created {created}, updated {updated}, skipped {skipped} (no email match).")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print('Usage: python import_manpower.py "SSDE Man power.xlsx" "SSDE_login_credentials.xlsx"')
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
