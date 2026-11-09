"""Salary & Payslips (payroll) API.

Who can do what:
  • Admin + HR   — set salary structures, advances, prepare / recalculate runs, adjustments, downloads.
  • Admin only   — payroll rules, bank file formats, approve (password + 2FA + typed total), reopen,
                    mark paid, release payslips, send to payout gateway.
  • Every user   — their own released payslips.

Safety: an approved run is frozen (amounts + bank-account fingerprints hashed). Bank details that
change after approval block the bank file. Every action is in the Audit Log. The whole section
honours the salary lock (routers/payouts.SECTION_LOCKED).
"""
from __future__ import annotations

import hashlib
import io
import json
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import audit, models
from .. import payroll_docs as docs
from .. import payroll_engine as eng
from .. import razorpayx as rx
from .. import tax_engine as tx
from ..database import get_db
from ..deps import get_current_user
from ..security import verify_password

router = APIRouter(prefix="/api/payroll", tags=["payroll"])

IST = timezone(timedelta(hours=5, minutes=30))
SKIP_ROLES = ("techsupport", "it_support_view")
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
ACCT_RE = re.compile(r"^[0-9]{9,18}$")


# ───────────────────────────────────────────────────────────── access
def _locked():
    from . import payouts
    if payouts.SECTION_LOCKED:
        raise HTTPException(423, payouts.LOCKED_MSG)


def _staff(user: models.User = Depends(get_current_user)) -> models.User:
    _locked()
    if user.role not in ("admin", "hr") or not user.is_active:
        raise HTTPException(403, "Payroll is for Admin and HR.")
    return user


def _admin(user: models.User = Depends(get_current_user)) -> models.User:
    _locked()
    if user.role != "admin" or not user.is_active:
        raise HTTPException(403, "Only Admin can do this.")
    return user


def _me(user: models.User = Depends(get_current_user)) -> models.User:
    _locked()
    return user


def _check_secret(user, password, otp):
    if not password or not verify_password(password, user.hashed_password or ""):
        raise HTTPException(401, "Password is incorrect.")
    if user.twofa_enabled:
        import pyotp
        if not otp or not user.totp_secret or not pyotp.TOTP(user.totp_secret).verify(str(otp).strip(), valid_window=1):
            raise HTTPException(401, "2FA code is incorrect.")


def _today():
    return datetime.now(IST).date()


def _f(x) -> float:
    return float(x or 0)


# ───────────────────────────────────────────────────────────── config
def _config_row(db) -> models.PayrollConfig:
    row = db.get(models.PayrollConfig, 1)
    if not row:
        row = models.PayrollConfig(id=1, data={})
        db.add(row); db.flush()
    return row


def get_cfg(db) -> dict:
    cfg = eng.merged_config(_config_row(db).data)
    co = cfg["company"]
    if not co.get("name"):                      # first run: start from the letterhead details already in use
        try:
            from .manpower import _company
            c = _company({})
            co["name"], co["address"] = c.get("name", ""), c.get("address", "")
        except Exception:
            pass
    return cfg


@router.get("/config")
def read_config(db: Session = Depends(get_db), user=Depends(_staff)):
    return {"config": get_cfg(db), "bank_fields": docs.BANK_FIELDS,
            "calc_options": {"percent_gross": "% of monthly gross", "percent_basic": "% of Basic",
                             "fixed": "Fixed amount", "balance": "Balance (gross − others)"},
            "pay_basis_options": {"calendar": "Calendar days in the cycle", "fixed_30": "Fixed 30 days",
                                  "fixed_26": "Fixed 26 days", "working": "Working days (excl. Sundays)"}}


@router.put("/config")
def save_config(body: dict = Body(...), db: Session = Depends(get_db), user=Depends(_admin)):
    cfg = eng.merged_config(body.get("config") or body)
    errs = eng.validate_config(cfg)
    if errs:
        raise HTTPException(400, {"message": "Fix these settings", "errors": errs})
    row = _config_row(db)
    old = row.data or {}
    row.data, row.updated_by = cfg, user.id
    audit.record(db, user, "payroll.config", entity_type="payroll", detail="Payroll rules updated",
                 meta={"changed": sorted(k for k in cfg if cfg.get(k) != old.get(k))})
    db.commit()
    return {"ok": True, "config": cfg}


# ───────────────────────────────────────────────────────────── employees & salary structures
def _salary_for(db, user_id, on: date):
    return (db.query(models.EmployeeSalary).filter(models.EmployeeSalary.user_id == user_id,
                                                   models.EmployeeSalary.effective_from <= on)
            .order_by(models.EmployeeSalary.effective_from.desc(), models.EmployeeSalary.id.desc()).first())


def _bank(u):
    acct = re.sub(r"\s", "", u.bank_account or "")
    ifsc = (u.ifsc_code or "").strip().upper()
    return acct, ifsc


def _bank_issues(u) -> list[str]:
    acct, ifsc = _bank(u)
    out = []
    if not acct:
        out.append("No bank account")
    elif not ACCT_RE.match(acct):
        out.append("Account number must be 9–18 digits")
    if not ifsc:
        out.append("No IFSC")
    elif not IFSC_RE.match(ifsc):
        out.append("IFSC format invalid")
    return out


def _sal_out(s: models.EmployeeSalary | None) -> dict | None:
    if not s:
        return None
    return {"id": s.id, "effective_from": s.effective_from.isoformat(), "monthly_gross": _f(s.monthly_gross),
            "overrides": s.overrides or {}, "on_payroll": bool(s.on_payroll), "exempt_reason": s.exempt_reason,
            "pf_applicable": bool(s.pf_applicable), "esi_applicable": bool(s.esi_applicable),
            "pt_applicable": bool(s.pt_applicable), "lwf_applicable": bool(s.lwf_applicable),
            "attendance_exempt": bool(s.attendance_exempt), "tds_monthly": _f(s.tds_monthly),
            "payment_mode": s.payment_mode or "bank", "uan": s.uan, "pf_number": s.pf_number,
            "esic_number": s.esic_number, "note": s.note, "created_at": s.created_at.isoformat() if s.created_at else None}


def _staff_users(db):
    return (db.query(models.User).filter(~models.User.role.in_(SKIP_ROLES))
            .order_by(models.User.is_active.desc(), models.User.name).all())


@router.get("/employees")
def employees(db: Session = Depends(get_db), user=Depends(_staff)):
    cfg = get_cfg(db)
    today = _today()
    out = []
    for u in _staff_users(db):
        s = _salary_for(db, u.id, today) or _salary_for(db, u.id, date(2999, 1, 1))
        acct, ifsc = _bank(u)
        parts = eng.split_gross(s.monthly_gross, cfg["components"], s.overrides) if s else []
        out.append({"id": u.id, "name": u.name, "emp_code": u.emp_code or u.hr_ref, "role": u.role,
                    "designation": u.designation, "location": u.location or u.branch, "active": bool(u.is_active),
                    "joining_date": u.joining_date.isoformat() if u.joining_date else None, "ctc": u.ctc,
                    "bank_name": u.bank_name, "account": docs.mask(acct), "ifsc": ifsc, "bank_issues": _bank_issues(u),
                    "pan": u.pan_number, "salary": _sal_out(s),
                    "breakup": [{"code": p["code"], "name": p["name"], "amount": _f(p["full"])} for p in parts]})
    return out


@router.get("/employees/{uid}")
def employee_history(uid: int, db: Session = Depends(get_db), user=Depends(_staff)):
    rows = (db.query(models.EmployeeSalary).filter(models.EmployeeSalary.user_id == uid)
            .order_by(models.EmployeeSalary.effective_from.desc(), models.EmployeeSalary.id.desc()).all())
    return [_sal_out(r) for r in rows]


def _num(v, field, allow_blank=False):
    if v in (None, "") and allow_blank:
        return None
    try:
        d = Decimal(str(v).replace(",", "").strip())
    except Exception:
        raise HTTPException(400, f"{field}: '{v}' is not a number")
    if d < 0:
        raise HTTPException(400, f"{field} cannot be negative")
    return d.quantize(Decimal("0.01"))


def _yn(v, default=True):
    if v in (None, ""):
        return default
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("y", "yes", "true", "1")


def _save_structure(db, actor, uid, body, cfg) -> models.EmployeeSalary:
    u = db.get(models.User, uid)
    if not u:
        raise HTTPException(404, "Employee not found")
    try:
        eff = date.fromisoformat(str(body.get("effective_from") or _today().isoformat())[:10])
    except ValueError:
        raise HTTPException(400, "Effective from must be a date (YYYY-MM-DD)")
    gross = _num(body.get("monthly_gross"), "Monthly gross")
    codes = {c["code"] for c in cfg["components"]}
    ov = {}
    for k, v in (body.get("overrides") or {}).items():
        if k in codes and v not in (None, ""):
            ov[k] = float(_num(v, k))
    s = models.EmployeeSalary(
        user_id=uid, effective_from=eff, monthly_gross=gross, overrides=ov,
        on_payroll=_yn(body.get("on_payroll"), True), exempt_reason=(body.get("exempt_reason") or "")[:160] or None,
        pf_applicable=_yn(body.get("pf_applicable"), True), esi_applicable=_yn(body.get("esi_applicable"), True),
        pt_applicable=_yn(body.get("pt_applicable"), True), lwf_applicable=_yn(body.get("lwf_applicable"), False),
        attendance_exempt=_yn(body.get("attendance_exempt"), False),
        tds_monthly=_num(body.get("tds_monthly") or 0, "TDS"), payment_mode=(body.get("payment_mode") or "bank")[:10],
        uan=(str(body.get("uan") or "").strip() or None), pf_number=(str(body.get("pf_number") or "").strip() or None),
        esic_number=(str(body.get("esic_number") or "").strip() or None), note=(body.get("note") or "")[:300] or None,
        created_by=actor.id)
    if s.payment_mode not in ("bank", "cash", "cheque"):
        raise HTTPException(400, "Payment mode must be bank, cash or cheque")
    db.add(s)
    audit.record(db, actor, "payroll.salary_set", entity_type="payroll", target_user_id=uid,
                 detail=f"{u.name}: gross ₹{gross} from {eff}" + ("" if s.on_payroll else " (exempt)"))
    return s


@router.post("/employees/{uid}/salary")
def set_salary(uid: int, body: dict = Body(...), db: Session = Depends(get_db), user=Depends(_staff)):
    s = _save_structure(db, user, uid, body, get_cfg(db))
    db.commit()
    return _sal_out(s)


SAL_HEAD = ["Emp ID", "Name", "Monthly Gross", "Effective From", "On Payroll (Y/N)", "Exempt Reason", "PF (Y/N)",
            "ESI (Y/N)", "PT (Y/N)", "LWF (Y/N)", "Attendance Exempt (Y/N)", "TDS per month", "Payment Mode",
            "UAN", "PF Number", "ESIC Number"]


@router.get("/employees-template.xlsx")
def salary_template(db: Session = Depends(get_db), user=Depends(_staff)):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    cfg = get_cfg(db)
    comps = [c["code"] for c in cfg["components"] if c["calc"] != "balance"]
    wb = Workbook(); ws = wb.active; ws.title = "Salary"
    head = SAL_HEAD + [f"{c} (fixed, optional)" for c in comps]
    ws.append(head)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="1E3A8A")
    today = _today()
    for u in _staff_users(db):
        if not u.is_active:
            continue
        s = _salary_for(db, u.id, today)
        ws.append([u.emp_code or u.hr_ref or "", u.name, _f(s.monthly_gross) if s else "", (s.effective_from if s else today).isoformat(),
                   "Y" if (not s or s.on_payroll) else "N", (s.exempt_reason if s else "") or "",
                   "Y" if (not s or s.pf_applicable) else "N", "Y" if (not s or s.esi_applicable) else "N",
                   "Y" if (not s or s.pt_applicable) else "N", "Y" if (s and s.lwf_applicable) else "N",
                   "Y" if (s and s.attendance_exempt) else "N", _f(s.tds_monthly) if s else 0, (s.payment_mode if s else "bank"),
                   (s.uan if s else "") or "", (s.pf_number if s else "") or "", (s.esic_number if s else "") or ""]
                  + [((s.overrides or {}).get(c, "") if s else "") for c in comps])
    for i, w in enumerate([10, 26, 14, 14, 10, 22, 8, 8, 8, 8, 12, 12, 12, 14, 16, 14], 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = w
    out = io.BytesIO(); wb.save(out)
    return Response(out.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="salary_structures.xlsx"'})


def _read_sheet(content: bytes, filename: str) -> list[dict]:
    rows = []
    if filename.lower().endswith(".csv"):
        import csv
        rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig", errors="replace"))))
    else:
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        rows = [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    if not rows:
        return []
    head = [str(h or "").strip() for h in rows[0]]
    out = []
    for r in rows[1:]:
        if not any(v not in (None, "") for v in r):
            continue
        out.append({head[i]: (r[i] if i < len(r) else None) for i in range(len(head)) if head[i]})
    return out


def _user_by_code(db):
    m = {}
    for u in db.query(models.User).all():
        for c in (u.emp_code, u.hr_ref, getattr(u, "tl_emp_code", None), getattr(u, "fos_emp_code", None), getattr(u, "tc_emp_code", None)):
            if c:
                m[str(c).strip().upper()] = u
    return m


def _col(row, *names):
    for k, v in row.items():
        kk = re.sub(r"[^a-z]", "", k.lower())
        for n in names:
            if kk.startswith(n):
                return v
    return None


@router.post("/employees/upload")
async def upload_salaries(file: UploadFile = File(...), commit: bool = Form(False),
                          db: Session = Depends(get_db), user=Depends(_staff)):
    cfg = get_cfg(db)
    rows = _read_sheet(await file.read(), file.filename or "x.xlsx")
    codes = _user_by_code(db)
    comps = [c["code"] for c in cfg["components"] if c["calc"] != "balance"]
    ok, errors = [], []
    for i, r in enumerate(rows, 2):
        code = str(_col(r, "empid", "employeeid", "empcode", "code") or "").strip().upper()
        u = codes.get(code)
        if not u:
            errors.append(f"Row {i}: unknown Emp ID '{code}'"); continue
        gross = _col(r, "monthlygross", "gross")
        if gross in (None, ""):
            errors.append(f"Row {i} ({u.name}): Monthly Gross is empty"); continue
        eff = _col(r, "effectivefrom", "effective")
        eff = eff.date().isoformat() if isinstance(eff, datetime) else (eff.isoformat() if isinstance(eff, date) else str(eff or _today().isoformat())[:10])
        body = {"monthly_gross": gross, "effective_from": eff, "on_payroll": _col(r, "onpayroll"),
                "exempt_reason": _col(r, "exemptreason"), "pf_applicable": _col(r, "pfyn", "pf"),
                "esi_applicable": _col(r, "esiyn", "esi"), "pt_applicable": _col(r, "ptyn", "pt"),
                "lwf_applicable": _col(r, "lwf"), "attendance_exempt": _col(r, "attendanceexempt"),
                "tds_monthly": _col(r, "tds") or 0, "payment_mode": str(_col(r, "paymentmode") or "bank").lower(),
                "uan": _col(r, "uan"), "pf_number": _col(r, "pfnumber"), "esic_number": _col(r, "esicnumber", "esic"),
                "overrides": {c: _col(r, re.sub(r'[^a-z]', '', c.lower())) for c in comps}}
        try:
            if commit:
                _save_structure(db, user, u.id, body, cfg)
            else:
                Decimal(str(gross).replace(",", ""))
                date.fromisoformat(eff)
            ok.append({"emp_code": code, "name": u.name, "monthly_gross": float(Decimal(str(gross).replace(",", ""))), "effective_from": eff})
        except HTTPException as e:
            errors.append(f"Row {i} ({u.name}): {e.detail}")
        except Exception as e:
            errors.append(f"Row {i} ({u.name}): {e}")
    if commit:
        if errors:
            db.rollback()
            raise HTTPException(400, {"message": "Nothing saved — fix these rows first", "errors": errors})
        db.commit()
    return {"rows": len(rows), "valid": ok, "errors": errors, "committed": bool(commit)}


# ───────────────────────────────────────────────────────────── advances / loans
def _adv_out(a, names):
    return {"id": a.id, "user_id": a.user_id, "name": names.get(a.user_id), "kind": a.kind, "principal": _f(a.principal),
            "emi": _f(a.emi), "balance": _f(a.balance), "start_period": a.start_period, "status": a.status, "note": a.note,
            "created_at": a.created_at.isoformat() if a.created_at else None}


@router.get("/advances")
def advances(db: Session = Depends(get_db), user=Depends(_staff)):
    rows = db.query(models.SalaryAdvance).order_by(models.SalaryAdvance.status, models.SalaryAdvance.id.desc()).all()
    names = {u.id: u.name for u in db.query(models.User).filter(models.User.id.in_({r.user_id for r in rows} or {0}))}
    return [_adv_out(a, names) for a in rows]


@router.post("/advances")
def add_advance(body: dict = Body(...), db: Session = Depends(get_db), user=Depends(_staff)):
    u = db.get(models.User, int(body.get("user_id") or 0))
    if not u:
        raise HTTPException(404, "Employee not found")
    principal = _num(body.get("principal"), "Amount")
    emi = _num(body.get("emi"), "Monthly recovery")
    if principal <= 0 or emi <= 0:
        raise HTTPException(400, "Amount and monthly recovery must be more than 0")
    sp = str(body.get("start_period") or _today().strftime("%Y-%m"))[:7]
    if not re.match(r"^\d{4}-\d{2}$", sp):
        raise HTTPException(400, "Start month must be YYYY-MM")
    a = models.SalaryAdvance(user_id=u.id, kind=(body.get("kind") or "advance")[:12], principal=principal, emi=min(emi, principal),
                             balance=principal, start_period=sp, note=(body.get("note") or "")[:300] or None, created_by=user.id)
    db.add(a)
    audit.record(db, user, "payroll.advance", entity_type="payroll", target_user_id=u.id,
                 detail=f"{u.name}: {a.kind} ₹{principal}, recover ₹{a.emi}/month from {sp}")
    db.commit()
    return _adv_out(a, {u.id: u.name})


@router.post("/advances/{aid}/close")
def close_advance(aid: int, db: Session = Depends(get_db), user=Depends(_staff)):
    a = db.get(models.SalaryAdvance, aid)
    if not a:
        raise HTTPException(404, "Not found")
    a.status = "closed"
    audit.record(db, user, "payroll.advance_close", entity_type="payroll", target_user_id=a.user_id,
                 detail=f"Advance #{a.id} closed with balance ₹{a.balance}")
    db.commit()
    return {"ok": True}


# ───────────────────────────────────────────────────────────── run computation
def _days(db, u, start: date, end: date, cfg) -> list[dict]:
    from ..leave_policy import day_credit
    today = _today()
    atts = {a.date: a for a in db.query(models.Attendance).filter(models.Attendance.user_id == u.id,
                                                                   models.Attendance.date >= start,
                                                                   models.Attendance.date <= end)}
    leaves = (db.query(models.Leave).filter(models.Leave.user_id == u.id, models.Leave.status == "approved",
                                            models.Leave.start_date <= end, models.Leave.end_date >= start).all())
    kw = [k.lower() for k in (cfg.get("attendance") or {}).get("unpaid_leave_keywords") or []]
    out = []
    d = start
    while d <= end:
        lv = next((l for l in leaves if l.start_date <= d <= l.end_date), None)
        c = day_credit(atts.get(d), lv, d, today)
        c["date"] = d
        c["unpaid_leave"] = c.get("leave", 0) if (lv and any(k in (lv.leave_type or "").lower() for k in kw)) else 0
        out.append(c)
        d += timedelta(days=1)
    return out


def _snapshot(u, s, cfg):
    acct, ifsc = _bank(u)
    role_label = {"fos": "Field Executive", "telecaller": "Tele Caller", "teamlead": "Team Leader", "manager": "Manager",
                  "headoffice": "Head Office", "hr": "HR", "admin": "Administrator", "backend": "Back Office"}
    return {"name": u.name, "emp_code": u.emp_code or u.hr_ref, "designation": u.designation or role_label.get(u.role, u.role),
            "location": u.location or u.branch, "role": u.role,
            "joining_date": u.joining_date.strftime("%d-%b-%Y") if u.joining_date else None,
            "pan": u.pan_number, "bank_name": u.bank_name, "holder": (u.bank_holder or u.name),
            "account_masked": docs.mask(acct), "account_fp": rx.fingerprint(acct, ifsc) if acct else None,
            "ifsc": ifsc, "uan": s.uan, "pf_number": s.pf_number, "esic_number": s.esic_number,
            "payment_mode": s.payment_mode or "bank", "email": u.email, "phone": u.phone,
            "monthly_gross": _f(s.monthly_gross)}


def _prev_lines(db, run) -> dict:
    prev = (db.query(models.PayrollRun).filter(models.PayrollRun.id != run.id, models.PayrollRun.period < run.period,
                                               models.PayrollRun.status.in_(("approved", "paid")))
            .order_by(models.PayrollRun.period.desc()).first())
    if not prev:
        return {}
    return {l.user_id: l for l in db.query(models.PayrollLine).filter(models.PayrollLine.run_id == prev.id)}


def _decl(db, uid, fy, cfg):
    d = db.query(models.TaxDeclaration).filter_by(user_id=uid, fy=fy).first()
    return d, (d.regime if d else None) or (cfg.get("income_tax") or {}).get("default_regime", "new")


def _taxable_parts(line_like, adj_types):
    """From a payroll line's earnings/deductions → taxable gross, basic, HRA, employee PF, PT, TDS."""
    g = b = h = 0.0
    for e in line_like.get("earnings") or []:
        if e.get("adjustment") and adj_types.get(e["code"], {}).get("taxable") is False:
            continue
        g += float(e.get("amount") or 0)
        if e["code"] == "BASIC":
            b += float(e.get("amount") or 0)
        if e["code"] == "HRA":
            h += float(e.get("amount") or 0)
    dm = {}
    for d in line_like.get("deductions") or []:
        dm[d["code"]] = dm.get(d["code"], 0.0) + float(d.get("amount") or 0)
    return {"gross": g, "basic": b, "hra": h, "pf": dm.get("PF", 0.0), "pt": dm.get("PT", 0.0), "tds": dm.get("TDS", 0.0)}


def project_tax(db, u, s, cfg, period, current: dict | None, exclude_run_id=None, leaving=False) -> dict:
    """Projected tax for the FY of `period`: actual approved months + this month + remaining months at the
    current structure. Returns both regimes and the monthly TDS for the employee's chosen regime."""
    tc = cfg.get("income_tax") or tx.DEFAULT_TAX
    fy = tx.fy_of(period)
    periods = tx.fy_periods(fy)
    adj_types = {a["code"]: a for a in cfg.get("adjustment_types") or []}
    past = {"gross": 0.0, "basic": 0.0, "hra": 0.0, "pf": 0.0, "pt": 0.0, "tds": 0.0}
    runs = {r.id: r.period for r in db.query(models.PayrollRun).filter(models.PayrollRun.period.in_(periods),
                                                                       models.PayrollRun.period < period,
                                                                       models.PayrollRun.status.in_(("approved", "paid")))
            if r.id != exclude_run_id}
    paid_periods = set()
    for l in db.query(models.PayrollLine).filter(models.PayrollLine.run_id.in_(list(runs) or [0]), models.PayrollLine.user_id == u.id,
                                                 models.PayrollLine.included == True):  # noqa: E712
        p = _taxable_parts({"earnings": l.earnings, "deductions": l.deductions}, adj_types)
        for k in past:
            past[k] += p[k]
        paid_periods.add(runs[l.run_id])
    parts = eng.split_gross(s.monthly_gross, cfg["components"], s.overrides)
    full = {"gross": float(s.monthly_gross), "basic": sum(float(x["full"]) for x in parts if x["code"] == "BASIC"),
            "hra": sum(float(x["full"]) for x in parts if x["code"] == "HRA")}
    st = cfg.get("statutory") or {}
    pfc = st.get("pf") or {}
    full["pf"] = (round(min(full["basic"], float(pfc.get("wage_ceiling") or 15000)) * float(pfc.get("employee_rate") or 12) / 100)
                  if pfc.get("enabled") and s.pf_applicable else 0.0)
    full["pt"] = float(eng.pt_for(full["gross"], (st.get("pt") or {}).get("slabs"))) if (st.get("pt") or {}).get("enabled") and s.pt_applicable else 0.0
    cur = current or {k: full[k] for k in ("gross", "basic", "hra", "pf", "pt")}
    idx = periods.index(period)
    # Months of this FY before RecoverIQ payroll started (or not run here): assume the current salary was
    # paid if the employee had joined by then. TDS deducted outside RecoverIQ is entered in the declaration.
    sd = int((cfg.get("cycle") or {}).get("start_day") or 1)
    outside = 0
    for p_ in periods[:idx]:
        if p_ in paid_periods:
            continue
        if u.joining_date and u.joining_date > eng.cycle_for(p_, sd)[1]:
            continue
        outside += 1
    for k in ("gross", "basic", "hra", "pf", "pt"):
        past[k] += full[k] * outside
    left_after = 0 if leaving else len(periods) - idx - 1
    tot = {k: past[k] + cur.get(k, 0.0) + full.get(k, 0.0) * left_after for k in ("gross", "basic", "hra", "pf", "pt")}
    d, regime = _decl(db, u.id, fy, cfg)
    data = (d.data if d else {}) or {}
    metro = bool(d.metro) if d else False
    res = {r_: tx.compute_annual(regime=r_, cfg=tc, gross=tot["gross"], basic=tot["basic"], hra=tot["hra"], pf=tot["pf"],
                                 pt=tot["pt"], decl=data, metro=metro) for r_ in ("new", "old")}
    so_far = past["tds"] + float(data.get("prev_employer_tds") or 0) + float(data.get("tds_outside") or 0)
    monthly = tx.monthly_tds(res[regime]["total"], so_far, left_after + 1)
    return {"fy": fy, "regime": regime, "annual": res[regime], "other": res["old" if regime == "new" else "new"],
            "projected": tot, "tds_so_far": round(so_far, 2), "months_left": left_after + 1, "monthly_tds": monthly,
            "months_outside": outside,
            "declared": bool(d)}


def _fnf_done(db, uid, before: date):
    return (db.query(models.FnfSettlement).filter(models.FnfSettlement.user_id == uid,
                                                  models.FnfSettlement.status.in_(("approved", "paid")),
                                                  models.FnfSettlement.last_working_day <= before).first())


def _compute(db, run: models.PayrollRun, cfg: dict):
    """(Re)build every line of a DRAFT run. Manual choices (exclude, hold, paid-days override) survive."""
    if run.status != "draft":
        raise HTTPException(400, "Only a draft run can be recalculated.")
    existing = {l.user_id: l for l in db.query(models.PayrollLine).filter(models.PayrollLine.run_id == run.id)}
    adj_types = {a["code"]: a for a in cfg.get("adjustment_types") or []}
    adjs = {}
    for a in db.query(models.PayrollAdjustment).filter(models.PayrollAdjustment.run_id == run.id):
        adjs.setdefault(a.user_id, []).append({"kind": a.kind, "code": a.code, "amount": a.amount, "note": a.note})
    prev = _prev_lines(db, run)
    pct = float((cfg.get("checks") or {}).get("net_change_pct") or 0)
    seen = set()
    missing = []
    for u in _staff_users(db):
        exit_day = None
        if not u.is_active:
            if not u.blocked_at:
                continue
            exit_day = (u.blocked_at.date() if isinstance(u.blocked_at, datetime) else u.blocked_at)
            if exit_day < run.cycle_start:
                continue
        if _fnf_done(db, u.id, run.cycle_end):        # paid through full & final — never paid twice
            continue
        s = _salary_for(db, u.id, run.cycle_end)
        if not s:
            if u.is_active:
                missing.append({"id": u.id, "name": u.name, "emp_code": u.emp_code or u.hr_ref, "role": u.role})
            continue
        seen.add(u.id)
        line = existing.get(u.id) or models.PayrollLine(run_id=run.id, user_id=u.id, included=True)
        if line.id is None:
            db.add(line)
        line.salary_id = s.id
        line.snapshot = _snapshot(u, s, cfg)
        if not s.on_payroll:
            line.included = False
            line.exclude_reason = s.exempt_reason or "Exempt from payroll"
        joining = u.joining_date if (u.joining_date and run.cycle_start <= u.joining_date <= run.cycle_end) else None
        days = _days(db, u, run.cycle_start, run.cycle_end, cfg)
        att = eng.attendance_lop(days, cfg, run.cycle_start, run.cycle_end, joining, exit_day, bool(s.attendance_exempt))
        advs = [{"id": a.id, "emi": a.emi, "balance": a.balance} for a in db.query(models.SalaryAdvance)
                .filter(models.SalaryAdvance.user_id == u.id, models.SalaryAdvance.status == "active",
                        models.SalaryAdvance.start_period <= run.period, models.SalaryAdvance.balance > 0)]
        auto_tds = (cfg.get("income_tax") or {}).get("mode", "auto") == "auto" and not float(s.tds_monthly or 0)
        fl = {"pf": s.pf_applicable, "esi": s.esi_applicable, "pt": s.pt_applicable, "lwf": s.lwf_applicable,
              "tds": 0 if auto_tds else s.tds_monthly}

        def _run_line(f):
            return eng.compute_line(gross_monthly=s.monthly_gross, components=cfg["components"], overrides=s.overrides,
                                    att=att, paid_days_override=line.paid_days_override, adjustments=adjs.get(u.id, []),
                                    adj_types=adj_types, advances=advs, flags_in=f, cfg=cfg, period=run.period)
        res = _run_line(fl)
        tax_info = None
        if auto_tds:
            try:
                tax_info = project_tax(db, u, s, cfg, run.period, _taxable_parts(res, adj_types),
                                       exclude_run_id=run.id, leaving=bool(exit_day))
                if tax_info["monthly_tds"] > 0:
                    res = _run_line({**fl, "tds": tax_info["monthly_tds"]})
            except Exception as e:                   # tax must never block payroll; flag it instead
                tax_info = {"error": str(e)[:120]}
        att["paid_days_final"] = res["paid_days"]
        att["tax"] = tax_info or {"mode": "manual", "monthly_tds": float(s.tds_monthly or 0)}
        att["statutory_wages"] = res["statutory_wages"]
        line.attendance = att
        line.earnings, line.deductions, line.employer = res["earnings"], res["deductions"], res["employer"]
        line.gross, line.total_deductions, line.net = res["gross"], res["total_deductions"], res["net"]
        flags = list(res["flags"])
        if (s.payment_mode or "bank") == "bank":
            for iss in _bank_issues(u):
                flags.append({"level": "error", "text": iss})
        if res["net"] <= 0:
            flags.append({"level": "error", "text": "Net pay is zero or negative"})
        p = prev.get(u.id)
        if p and p.included:
            if pct and float(p.net or 0) > 0 and abs(res["net"] - float(p.net)) / float(p.net) * 100 > pct:
                flags.append({"level": "warn", "text": f"Net changed {round((res['net'] - float(p.net)) / float(p.net) * 100)}% vs last month (₹{float(p.net):,.0f})"})
            if (p.snapshot or {}).get("account_fp") and p.snapshot.get("account_fp") != line.snapshot.get("account_fp"):
                flags.append({"level": "warn", "text": "Bank details changed since last salary — verify before paying"})
        if joining:
            flags.append({"level": "info", "text": f"New joiner ({u.joining_date.strftime('%d %b')})"})
        if exit_day:
            flags.append({"level": "info", "text": f"Left on {exit_day.strftime('%d %b')} — pro-rated"})
        if att["lop"] > 0:
            flags.append({"level": "info", "text": f"LOP {att['lop']:g} day(s)"})
        if tax_info and tax_info.get("error"):
            flags.append({"level": "warn", "text": f"TDS not calculated: {tax_info['error']}"})
        elif tax_info and tax_info.get("monthly_tds"):
            flags.append({"level": "info", "text": f"TDS ₹{tax_info['monthly_tds']:,.0f} ({tax_info['regime']} regime, "
                                                   f"annual tax ₹{tax_info['annual']['total']:,.0f})"})
        line.flags = flags
    for uid, l in existing.items():                 # people no longer eligible drop out of the draft
        if uid not in seen:
            db.delete(l)
    run.computed_at = datetime.now(timezone.utc)
    db.flush()
    run.totals = _totals(db, run, missing)


def _totals(db, run, missing=None):
    lines = db.query(models.PayrollLine).filter(models.PayrollLine.run_id == run.id).all()
    inc = [l for l in lines if l.included]
    pay = [l for l in inc if not l.hold]
    er = sum(sum(e["amount"] for e in (l.employer or [])) for l in inc)
    t = {"count": len(pay), "excluded": len(lines) - len(inc), "on_hold": len(inc) - len(pay),
         "gross": round(sum(_f(l.gross) for l in inc), 2), "deductions": round(sum(_f(l.total_deductions) for l in inc), 2),
         "net": round(sum(_f(l.net) for l in pay), 2), "net_on_hold": round(sum(_f(l.net) for l in inc if l.hold), 2),
         "employer": round(er, 2), "ctc": round(sum(_f(l.gross) for l in inc) + er, 2),
         "errors": sum(1 for l in inc for f in (l.flags or []) if f.get("level") == "error"),
         "warnings": sum(1 for l in inc for f in (l.flags or []) if f.get("level") == "warn"),
         "by_mode": {}}
    for l in pay:
        m = (l.snapshot or {}).get("payment_mode") or "bank"
        t["by_mode"][m] = round(t["by_mode"].get(m, 0) + _f(l.net), 2)
    if missing is not None:
        t["missing"] = missing
    else:
        t["missing"] = (run.totals or {}).get("missing", [])
    return t


def _run_out(run, names=None):
    return {"id": run.id, "period": run.period, "label": docs.period_label(run.period),
            "cycle_start": run.cycle_start.isoformat(), "cycle_end": run.cycle_end.isoformat(),
            "pay_date": run.pay_date.isoformat() if run.pay_date else None, "status": run.status,
            "totals": run.totals or {}, "released": bool(run.released), "payout_batch_id": run.payout_batch_id,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "computed_at": run.computed_at.isoformat() if run.computed_at else None,
            "approved_at": run.approved_at.isoformat() if run.approved_at else None,
            "approved_by": (names or {}).get(run.approved_by), "created_by": (names or {}).get(run.created_by),
            "paid_at": run.paid_at.isoformat() if run.paid_at else None, "note": run.note}


def _line_out(l):
    return {"id": l.id, "user_id": l.user_id, "snapshot": {k: v for k, v in (l.snapshot or {}).items() if k != "account_fp"},
            "included": bool(l.included), "exclude_reason": l.exclude_reason, "hold": bool(l.hold),
            "attendance": l.attendance or {}, "paid_days_override": _f(l.paid_days_override) if l.paid_days_override is not None else None,
            "earnings": l.earnings or [], "deductions": l.deductions or [], "employer": l.employer or [],
            "gross": _f(l.gross), "total_deductions": _f(l.total_deductions), "net": _f(l.net), "flags": l.flags or [],
            "pay_status": l.pay_status, "utr": l.utr, "paid_on": l.paid_on.isoformat() if l.paid_on else None}


def _get_run(db, rid) -> models.PayrollRun:
    r = db.get(models.PayrollRun, rid)
    if not r:
        raise HTTPException(404, "Payroll run not found")
    return r


def _names(db, ids):
    ids = {i for i in ids if i}
    return {u.id: u.name for u in db.query(models.User).filter(models.User.id.in_(ids or {0}))}


@router.get("/runs")
def list_runs(db: Session = Depends(get_db), user=Depends(_staff)):
    runs = db.query(models.PayrollRun).order_by(models.PayrollRun.period.desc(), models.PayrollRun.id.desc()).limit(60).all()
    names = _names(db, [r.approved_by for r in runs] + [r.created_by for r in runs])
    return [_run_out(r, names) for r in runs]


@router.post("/runs")
def create_run(body: dict = Body(...), db: Session = Depends(get_db), user=Depends(_staff)):
    period = str(body.get("period") or "")[:7]
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", period):
        raise HTTPException(400, "Salary month must be YYYY-MM")
    if db.query(models.PayrollRun).filter(models.PayrollRun.period == period, models.PayrollRun.status != "cancelled").first():
        raise HTTPException(400, f"A payroll run for {docs.period_label(period)} already exists — open it instead.")
    cfg = get_cfg(db)
    cs, ce = eng.cycle_for(period, int(cfg["cycle"].get("start_day") or 1))
    pd = body.get("pay_date")
    run = models.PayrollRun(period=period, cycle_start=cs, cycle_end=ce, status="draft", created_by=user.id,
                            pay_date=date.fromisoformat(pd[:10]) if pd else eng.pay_date_for(period, int(cfg["cycle"].get("pay_day") or 0)),
                            rules_snapshot=cfg, note=(body.get("note") or "")[:1000] or None)
    db.add(run); db.flush()
    _compute(db, run, cfg)
    audit.record(db, user, "payroll.run_create", entity_type="payroll",
                 detail=f"Payroll {docs.period_label(period)} created ({run.totals.get('count', 0)} employees)", meta={"run_id": run.id})
    db.commit()
    return get_run(run.id, db, user)


@router.get("/runs/{rid}")
def get_run(rid: int, db: Session = Depends(get_db), user=Depends(_staff)):
    run = _get_run(db, rid)
    lines = (db.query(models.PayrollLine).filter(models.PayrollLine.run_id == run.id).all())
    lines.sort(key=lambda l: (not l.included, (l.snapshot or {}).get("name") or ""))
    adj = db.query(models.PayrollAdjustment).filter(models.PayrollAdjustment.run_id == run.id).all()
    names = _names(db, [run.approved_by, run.created_by] + [a.user_id for a in adj])
    return {**_run_out(run, names), "lines": [_line_out(l) for l in lines],
            "adjustments": [{"id": a.id, "user_id": a.user_id, "name": names.get(a.user_id), "kind": a.kind, "code": a.code,
                             "amount": _f(a.amount), "note": a.note, "source": a.source} for a in adj]}


@router.post("/runs/{rid}/recalculate")
def recalc(rid: int, db: Session = Depends(get_db), user=Depends(_staff)):
    run = _get_run(db, rid)
    cfg = get_cfg(db)
    run.rules_snapshot = cfg
    _compute(db, run, cfg)
    db.commit()
    return get_run(rid, db, user)


@router.patch("/runs/{rid}/lines/{lid}")
def edit_line(rid: int, lid: int, body: dict = Body(...), db: Session = Depends(get_db), user=Depends(_staff)):
    run = _get_run(db, rid)
    if run.status != "draft":
        raise HTTPException(400, "This run is approved and locked. Reopen it to change.")
    l = db.get(models.PayrollLine, lid)
    if not l or l.run_id != run.id:
        raise HTTPException(404, "Line not found")
    name = (l.snapshot or {}).get("name")
    if "included" in body:
        inc = bool(body["included"])
        if not inc and not (body.get("exclude_reason") or "").strip():
            raise HTTPException(400, "Give a reason for excluding this employee.")
        l.included = inc
        l.exclude_reason = None if inc else body.get("exclude_reason")[:200]
        audit.record(db, user, "payroll.line_include", entity_type="payroll", target_user_id=l.user_id,
                     detail=f"{name}: {'included' if inc else 'excluded — ' + l.exclude_reason}")
    if "hold" in body:
        l.hold = bool(body["hold"])
        audit.record(db, user, "payroll.line_hold", entity_type="payroll", target_user_id=l.user_id,
                     detail=f"{name}: salary {'on hold' if l.hold else 'hold released'}")
    if "paid_days_override" in body:
        v = body["paid_days_override"]
        l.paid_days_override = None if v in (None, "") else _num(v, "Paid days")
        audit.record(db, user, "payroll.line_days", entity_type="payroll", target_user_id=l.user_id,
                     detail=f"{name}: paid days set to {v if v not in (None, '') else 'auto'}")
    db.flush()
    _compute(db, run, get_cfg(db))
    db.commit()
    return get_run(rid, db, user)


# ───────────────────────────────────────────────────────────── adjustments
def _check_adj(cfg, kind, code):
    t = {a["code"]: a for a in cfg.get("adjustment_types") or []}
    if code not in t:
        raise HTTPException(400, f"Unknown adjustment type '{code}'. Add it in Settings → Adjustment types.")
    return t[code]["kind"]


@router.post("/runs/{rid}/adjustments")
def add_adjustment(rid: int, body: dict = Body(...), db: Session = Depends(get_db), user=Depends(_staff)):
    run = _get_run(db, rid)
    if run.status != "draft":
        raise HTTPException(400, "This run is locked.")
    cfg = get_cfg(db)
    code = str(body.get("code") or "").upper()
    kind = _check_adj(cfg, None, code)
    amt = _num(body.get("amount"), "Amount")
    if amt <= 0:
        raise HTTPException(400, "Amount must be more than 0")
    uid = int(body.get("user_id") or 0)
    if not db.get(models.User, uid):
        raise HTTPException(404, "Employee not found")
    db.add(models.PayrollAdjustment(run_id=run.id, user_id=uid, kind=kind, code=code, amount=amt,
                                    note=(body.get("note") or "")[:300] or None, created_by=user.id))
    audit.record(db, user, "payroll.adjustment", entity_type="payroll", target_user_id=uid, detail=f"{code} ₹{amt} ({kind})")
    db.flush()
    _compute(db, run, cfg)
    db.commit()
    return get_run(rid, db, user)


@router.delete("/runs/{rid}/adjustments/{aid}")
def del_adjustment(rid: int, aid: int, db: Session = Depends(get_db), user=Depends(_staff)):
    run = _get_run(db, rid)
    if run.status != "draft":
        raise HTTPException(400, "This run is locked.")
    a = db.get(models.PayrollAdjustment, aid)
    if not a or a.run_id != run.id:
        raise HTTPException(404, "Not found")
    audit.record(db, user, "payroll.adjustment_delete", entity_type="payroll", target_user_id=a.user_id, detail=f"{a.code} ₹{a.amount} removed")
    db.delete(a); db.flush()
    _compute(db, run, get_cfg(db))
    db.commit()
    return get_run(rid, db, user)


@router.get("/runs/{rid}/adjustments-template.xlsx")
def adj_template(rid: int, db: Session = Depends(get_db), user=Depends(_staff)):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    run = _get_run(db, rid)
    cfg = get_cfg(db)
    wb = Workbook(); ws = wb.active; ws.title = "Adjustments"
    ws.append(["Emp ID", "Name", "Type", "Amount", "Note"])
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="1E3A8A")
    for l in db.query(models.PayrollLine).filter(models.PayrollLine.run_id == run.id):
        ws.append([(l.snapshot or {}).get("emp_code"), (l.snapshot or {}).get("name"), "INCENTIVE", "", ""])
    t = wb.create_sheet("Types")
    t.append(["Type code", "Name", "Earning / deduction"])
    for a in cfg.get("adjustment_types") or []:
        t.append([a["code"], a["name"], a["kind"]])
    for w, col in ((10, "A"), (26, "B"), (14, "C"), (12, "D"), (30, "E")):
        ws.column_dimensions[col].width = w
    out = io.BytesIO(); wb.save(out)
    return Response(out.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="adjustments_{run.period}.xlsx"'})


@router.post("/runs/{rid}/adjustments/upload")
async def upload_adjustments(rid: int, file: UploadFile = File(...), commit: bool = Form(False),
                             db: Session = Depends(get_db), user=Depends(_staff)):
    run = _get_run(db, rid)
    if run.status != "draft":
        raise HTTPException(400, "This run is locked.")
    cfg = get_cfg(db)
    rows = _read_sheet(await file.read(), file.filename or "x.xlsx")
    codes = _user_by_code(db)
    ok, errors = [], []
    for i, r in enumerate(rows, 2):
        amt = _col(r, "amount")
        if amt in (None, ""):
            continue
        code = str(_col(r, "empid", "employeeid", "empcode") or "").strip().upper()
        u = codes.get(code)
        if not u:
            errors.append(f"Row {i}: unknown Emp ID '{code}'"); continue
        t = str(_col(r, "type", "code") or "").strip().upper()
        try:
            kind = _check_adj(cfg, None, t)
            a = _num(amt, "Amount")
            if a <= 0:
                raise HTTPException(400, "Amount must be more than 0")
        except HTTPException as e:
            errors.append(f"Row {i} ({u.name}): {e.detail}"); continue
        ok.append({"user_id": u.id, "name": u.name, "code": t, "kind": kind, "amount": float(a), "note": str(_col(r, "note") or "")[:300]})
    if commit:
        if errors:
            raise HTTPException(400, {"message": "Nothing saved — fix these rows first", "errors": errors})
        for o in ok:
            db.add(models.PayrollAdjustment(run_id=run.id, user_id=o["user_id"], kind=o["kind"], code=o["code"],
                                            amount=Decimal(str(o["amount"])), note=o["note"] or None, source="upload",
                                            created_by=user.id))
        audit.record(db, user, "payroll.adjustment_upload", entity_type="payroll",
                     detail=f"{len(ok)} adjustments uploaded for {docs.period_label(run.period)}")
        db.flush()
        _compute(db, run, cfg)
        db.commit()
    return {"rows": len(rows), "valid": ok, "errors": errors, "committed": bool(commit)}


# ───────────────────────────────────────────────────────────── approve / reopen / pay
def _hash(lines):
    blob = json.dumps(sorted((l.id, l.user_id, str(l.net), bool(l.included), bool(l.hold),
                              (l.snapshot or {}).get("account_fp")) for l in lines))
    return hashlib.sha256(blob.encode()).hexdigest()


@router.post("/runs/{rid}/approve")
def approve(rid: int, body: dict = Body(...), db: Session = Depends(get_db), user=Depends(_admin)):
    run = _get_run(db, rid)
    if run.status != "draft":
        raise HTTPException(400, f"Run is {run.status}; only a draft can be approved.")
    _check_secret(user, body.get("password"), body.get("otp"))
    lines = db.query(models.PayrollLine).filter(models.PayrollLine.run_id == run.id).all()
    bad = [f"{(l.snapshot or {}).get('name')}: {f['text']}" for l in lines if l.included
           for f in (l.flags or []) if f.get("level") == "error"]
    if bad:
        raise HTTPException(400, {"message": "Fix or exclude these employees before approving", "errors": bad[:30]})
    run.totals = _totals(db, run)
    try:
        typed = Decimal(str(body.get("confirm_total")).replace(",", "").strip())
    except Exception:
        raise HTTPException(400, "Type the net total to confirm")
    if typed.quantize(Decimal("1")) != Decimal(str(run.totals["net"])).quantize(Decimal("1")):
        raise HTTPException(400, f"Typed total does not match the net payable ₹{run.totals['net']:,.2f}")
    for l in lines:                                  # recover advances now that the amounts are final
        if not l.included:
            continue
        for d in l.deductions or []:
            if d.get("advance_id"):
                a = db.get(models.SalaryAdvance, d["advance_id"])
                if a:
                    a.balance = max(Decimal("0"), Decimal(str(a.balance)) - Decimal(str(d["amount"])))
                    if a.balance <= 0:
                        a.status = "closed"
    run.status, run.approved_by, run.approved_at = "approved", user.id, datetime.now(timezone.utc)
    run.approval_hash = _hash(lines)
    audit.record(db, user, "payroll.approve", entity_type="payroll",
                 detail=f"Payroll {docs.period_label(run.period)} approved: {run.totals['count']} employees, net ₹{run.totals['net']:,.2f}",
                 meta={"run_id": run.id, "hash": run.approval_hash})
    db.commit()
    return get_run(rid, db, user)


@router.post("/runs/{rid}/reopen")
def reopen(rid: int, body: dict = Body(...), db: Session = Depends(get_db), user=Depends(_admin)):
    run = _get_run(db, rid)
    if run.status != "approved":
        raise HTTPException(400, "Only an approved (unpaid) run can be reopened.")
    if run.payout_batch_id:
        b = db.get(models.PayoutBatch, run.payout_batch_id)
        if b and b.status not in ("cancelled", "draft"):
            raise HTTPException(400, "A payout batch for this run is already approved/sent — it cannot be reopened.")
    reason = (body.get("reason") or "").strip()
    if len(reason) < 5:
        raise HTTPException(400, "Give a reason for reopening.")
    _check_secret(user, body.get("password"), body.get("otp"))
    for l in db.query(models.PayrollLine).filter(models.PayrollLine.run_id == run.id, models.PayrollLine.included == True):  # noqa: E712
        for d in l.deductions or []:
            if d.get("advance_id"):
                a = db.get(models.SalaryAdvance, d["advance_id"])
                if a:
                    a.balance = Decimal(str(a.balance)) + Decimal(str(d["amount"]))
                    a.status = "active"
    run.status, run.approved_by, run.approved_at, run.approval_hash, run.released = "draft", None, None, None, False
    audit.record(db, user, "payroll.reopen", entity_type="payroll", detail=f"Payroll {docs.period_label(run.period)} reopened: {reason}"[:300])
    db.commit()
    return get_run(rid, db, user)


@router.post("/runs/{rid}/cancel")
def cancel(rid: int, body: dict = Body(default={}), db: Session = Depends(get_db), user=Depends(_admin)):
    run = _get_run(db, rid)
    if run.status != "draft":
        raise HTTPException(400, "Only a draft can be cancelled (reopen an approved run first).")
    run.status = "cancelled"
    audit.record(db, user, "payroll.cancel", entity_type="payroll", detail=f"Payroll {docs.period_label(run.period)} cancelled {body.get('reason') or ''}"[:300])
    db.commit()
    return {"ok": True}


def _verify_frozen(db, run, lines):
    if run.status not in ("approved", "paid"):
        raise HTTPException(400, "Approve the run first.")
    if _hash(lines) != run.approval_hash:
        raise HTTPException(409, "Run contents changed after approval — refusing. Reopen and re-approve.")


@router.post("/runs/{rid}/mark-paid")
def mark_paid(rid: int, body: dict = Body(default={}), db: Session = Depends(get_db), user=Depends(_admin)):
    run = _get_run(db, rid)
    lines = db.query(models.PayrollLine).filter(models.PayrollLine.run_id == run.id).all()
    _verify_frozen(db, run, lines)
    on = date.fromisoformat(str(body.get("paid_on") or _today().isoformat())[:10])
    n = 0
    for l in lines:
        if l.included and not l.hold and l.pay_status != "paid":
            l.pay_status, l.paid_on = "paid", on
            n += 1
    run.status, run.paid_at = "paid", datetime.now(timezone.utc)
    audit.record(db, user, "payroll.paid", entity_type="payroll", detail=f"Payroll {docs.period_label(run.period)} marked paid ({n} employees) on {on}")
    db.commit()
    return get_run(rid, db, user)


@router.post("/runs/{rid}/bank-status")
async def bank_status(rid: int, file: UploadFile = File(...), db: Session = Depends(get_db), user=Depends(_admin)):
    """Bank's response / status report → UTR + paid / failed per employee."""
    run = _get_run(db, rid)
    lines = db.query(models.PayrollLine).filter(models.PayrollLine.run_id == run.id).all()
    _verify_frozen(db, run, lines)
    rows = _read_sheet(await file.read(), file.filename or "x.xlsx")
    byref = {f"PR{run.id}{(l.snapshot or {}).get('emp_code') or l.user_id}"[:20].upper(): l for l in lines}
    bycode = {str((l.snapshot or {}).get("emp_code") or "").upper(): l for l in lines}
    matched, failed, unknown = 0, 0, []
    for i, r in enumerate(rows, 2):
        ref = str(_col(r, "customerref", "reference", "refno", "crn", "customerreference") or "").strip().upper()
        code = str(_col(r, "empid", "employeeid", "empcode") or "").strip().upper()
        l = byref.get(ref) or bycode.get(code)
        if not l:
            acct = re.sub(r"\D", "", str(_col(r, "beneficiaryaccount", "beneaccount", "accountno", "accountnumber", "account") or ""))
            amt = _col(r, "amount", "amt")
            for x in lines:
                if acct and (x.snapshot or {}).get("account_masked", "").endswith(acct[-4:]) and amt not in (None, "") \
                        and abs(float(str(amt).replace(",", "")) - _f(x.net)) < 0.5:
                    l = x; break
        if not l:
            unknown.append(f"Row {i}"); continue
        st = str(_col(r, "status", "transactionstatus") or "").lower()
        utr = str(_col(r, "utr", "utrno", "bankreference", "transactionreference") or "").strip()
        if any(k in st for k in ("fail", "reject", "return", "error")):
            l.pay_status = "failed"; failed += 1
        else:
            l.pay_status, l.paid_on = "paid", l.paid_on or _today()
        if utr:
            l.utr = utr[:40]
        matched += 1
    if all(l.pay_status == "paid" for l in lines if l.included and not l.hold):
        run.status, run.paid_at = "paid", run.paid_at or datetime.now(timezone.utc)
    audit.record(db, user, "payroll.bank_status", entity_type="payroll",
                 detail=f"Bank status for {docs.period_label(run.period)}: {matched} matched, {failed} failed, {len(unknown)} unmatched")
    db.commit()
    return {"matched": matched, "failed": failed, "unmatched": unknown, "run": get_run(rid, db, user)}


@router.post("/runs/{rid}/release")
def release(rid: int, body: dict = Body(default={}), db: Session = Depends(get_db), user=Depends(_admin)):
    run = _get_run(db, rid)
    if run.status not in ("approved", "paid"):
        raise HTTPException(400, "Approve the run before releasing payslips.")
    run.released = bool(body.get("released", True))
    audit.record(db, user, "payroll.release", entity_type="payroll",
                 detail=f"Payslips {docs.period_label(run.period)} {'released to employees' if run.released else 'hidden'}")
    db.commit()
    return get_run(rid, db, user)


@router.post("/runs/{rid}/send-to-gateway")
def send_to_gateway(rid: int, db: Session = Depends(get_db), user=Depends(_admin)):
    """Create a RazorpayX payout batch from this approved run (it still needs its own approval there)."""
    from . import payouts
    run = _get_run(db, rid)
    lines = db.query(models.PayrollLine).filter(models.PayrollLine.run_id == run.id).all()
    _verify_frozen(db, run, lines)
    if run.payout_batch_id:
        b = db.get(models.PayoutBatch, run.payout_batch_id)
        if b and b.status != "cancelled":
            raise HTTPException(400, f"Already sent to the gateway as {b.ref}.")
    items = [{"user_id": l.user_id, "amount": f"{_f(l.net):.2f}", "mode": "NEFT"} for l in lines
             if l.included and not l.hold and _f(l.net) > 0 and (l.snapshot or {}).get("payment_mode", "bank") == "bank"]
    if not items:
        raise HTTPException(400, "No bank payments in this run.")
    out = payouts.create_batch({"period": run.period, "title": f"Salary {docs.period_label(run.period)}", "items": items,
                                "source": "payroll_run", "source_id": run.id,
                                "narration": f"SALARY {docs.period_label(run.period)}"}, db, user)
    run.payout_batch_id = out["id"]
    db.commit()
    return {"ok": True, "batch": out}


@router.post("/runs/{rid}/email-payslips")
def email_payslips(rid: int, db: Session = Depends(get_db), user=Depends(_admin)):
    from .manpower import _send_email
    run = _get_run(db, rid)
    if not run.released:
        raise HTTPException(400, "Release the payslips first.")
    cfg = run.rules_snapshot or get_cfg(db)
    sent, skipped, failed = 0, [], []
    for l in db.query(models.PayrollLine).filter(models.PayrollLine.run_id == run.id, models.PayrollLine.included == True):  # noqa: E712
        to = (l.snapshot or {}).get("email") or ""
        if "@" not in to or to.endswith(".local") or to.endswith(".test"):
            skipped.append((l.snapshot or {}).get("name")); continue
        try:
            pdf = docs.payslip_pdf([(run, l, _ytd(db, l))], cfg)
            _send_email(to, f"Payslip {docs.period_label(run.period)}",
                        f"<p>Dear {(l.snapshot or {}).get('name')},</p><p>Your payslip for {docs.period_label(run.period)} is attached.</p>",
                        attachments=[(f"Payslip_{run.period}.pdf", pdf, "application/pdf")])
            sent += 1
        except HTTPException as e:
            raise e
        except Exception as e:
            failed.append(f"{(l.snapshot or {}).get('name')}: {str(e)[:80]}")
    audit.record(db, user, "payroll.email", entity_type="payroll", detail=f"Payslips emailed: {sent}, skipped {len(skipped)}, failed {len(failed)}")
    db.commit()
    return {"sent": sent, "skipped": skipped, "failed": failed}


# ───────────────────────────────────────────────────────────── downloads
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _file(data, name, media):
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})


def _ytd(db, line):
    run = db.get(models.PayrollRun, line.run_id)
    y, m = int(run.period[:4]), int(run.period[5:7])
    fy0 = y if m >= 4 else y - 1
    start, label = f"{fy0}-04", f"FY {fy0}-{str(fy0 + 1)[2:]}"
    runs = [r.id for r in db.query(models.PayrollRun).filter(models.PayrollRun.period >= start, models.PayrollRun.period <= run.period,
                                                             models.PayrollRun.status.in_(("approved", "paid")))]
    if run.id not in runs:
        runs.append(run.id)
    t = {"fy": label, "gross": 0.0, "deductions": 0.0, "net": 0.0, "pf": 0.0, "tds": 0.0}
    for l in db.query(models.PayrollLine).filter(models.PayrollLine.run_id.in_(runs), models.PayrollLine.user_id == line.user_id,
                                                 models.PayrollLine.included == True):  # noqa: E712
        t["gross"] += _f(l.gross); t["deductions"] += _f(l.total_deductions); t["net"] += _f(l.net)
        t["pf"] += sum(d["amount"] for d in l.deductions or [] if d["code"] == "PF")
        t["tds"] += sum(d["amount"] for d in l.deductions or [] if d["code"] == "TDS")
    return t


@router.get("/runs/{rid}/register.xlsx")
def dl_register(rid: int, db: Session = Depends(get_db), user=Depends(_staff)):
    run = _get_run(db, rid)
    lines = db.query(models.PayrollLine).filter(models.PayrollLine.run_id == run.id).all()
    lines.sort(key=lambda l: (not l.included, (l.snapshot or {}).get("name") or ""))
    audit.record(db, user, "download", entity_type="payroll", detail=f"Salary register {run.period}"); db.commit()
    return _file(docs.register_xlsx(run, lines, run.rules_snapshot or get_cfg(db)), f"Salary_Register_{run.period}.xlsx", XLSX)


@router.get("/runs/{rid}/payslips.pdf")
def dl_payslips(rid: int, line_id: int | None = None, db: Session = Depends(get_db), user=Depends(_staff)):
    run = _get_run(db, rid)
    q = db.query(models.PayrollLine).filter(models.PayrollLine.run_id == run.id, models.PayrollLine.included == True)  # noqa: E712
    if line_id:
        q = q.filter(models.PayrollLine.id == line_id)
    lines = sorted(q.all(), key=lambda l: (l.snapshot or {}).get("name") or "")
    if not lines:
        raise HTTPException(404, "No payslips")
    cfg = run.rules_snapshot or get_cfg(db)
    pdf = docs.payslip_pdf([(run, l, _ytd(db, l)) for l in lines], cfg)
    audit.record(db, user, "download", entity_type="payroll", detail=f"Payslips {run.period} ({len(lines)})"); db.commit()
    nm = f"Payslip_{run.period}_{(lines[0].snapshot or {}).get('emp_code')}.pdf" if line_id else f"Payslips_{run.period}.pdf"
    return _file(pdf, nm, "application/pdf")


@router.get("/runs/{rid}/bank-file")
def dl_bank_file(rid: int, template_id: int = Query(...), db: Session = Depends(get_db), user=Depends(_admin)):
    run = _get_run(db, rid)
    lines = db.query(models.PayrollLine).filter(models.PayrollLine.run_id == run.id).all()
    _verify_frozen(db, run, lines)
    t = db.get(models.BankFileTemplate, template_id)
    if not t:
        raise HTTPException(404, "Bank format not found")
    blocked = []

    class L:                                     # a copy carrying the full account, read fresh + checked
        pass
    payload = []
    for l in lines:
        c = L()
        for k in ("included", "hold", "net", "user_id", "id"):
            setattr(c, k, getattr(l, k))
        s = dict(l.snapshot or {})
        if l.included and not l.hold and s.get("payment_mode", "bank") == "bank":
            u = db.get(models.User, l.user_id)
            acct, ifsc = _bank(u) if u else ("", "")
            if not acct or rx.fingerprint(acct, ifsc) != s.get("account_fp"):
                blocked.append(s.get("name")); continue
            s["_account"], s["ifsc"] = acct, ifsc
        c.snapshot = s
        payload.append(c)
    if blocked:
        raise HTTPException(409, {"message": "Bank details changed after approval for these employees — reopen and re-approve",
                                  "errors": blocked})
    data, name, media = docs.bank_file(t, run, payload, run.rules_snapshot or get_cfg(db))
    digest = hashlib.sha256(data).hexdigest()
    audit.record(db, user, "payroll.bank_file", entity_type="payroll",
                 detail=f"Bank file {t.name} for {run.period}: ₹{run.totals.get('net', 0):,.2f}, sha256 {digest[:12]}")
    db.commit()
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"',
                                                     "X-File-SHA256": digest})


@router.get("/runs/{rid}/ecr.txt")
def dl_ecr(rid: int, db: Session = Depends(get_db), user=Depends(_staff)):
    run = _get_run(db, rid)
    lines = db.query(models.PayrollLine).filter(models.PayrollLine.run_id == run.id).all()
    return _file(docs.pf_ecr(run, lines), f"PF_ECR_{run.period}.txt", "text/plain")


@router.get("/runs/{rid}/statutory.xlsx")
def dl_statutory(rid: int, db: Session = Depends(get_db), user=Depends(_staff)):
    run = _get_run(db, rid)
    lines = db.query(models.PayrollLine).filter(models.PayrollLine.run_id == run.id).all()
    return _file(docs.statutory_xlsx(run, lines, run.rules_snapshot or get_cfg(db)), f"Statutory_{run.period}.xlsx", XLSX)


# ───────────────────────────────────────────────────────────── bank file formats
DEFAULT_TEMPLATES = [
    {"name": "Axis Bank — bulk salary (edit to match your Axis template)", "bank": "AXIS", "file_type": "xlsx",
     "options": {"same_bank_ifsc": "UTIB", "mode_same_bank": "I", "mode_other": "N", "date_format": "%d-%m-%Y",
                 "narration": "SALARY {MONTH} {CODE}", "debit_account": ""},
     "columns": [{"header": "Payment Mode", "field": "payment_mode"}, {"header": "Amount", "field": "amount"},
                 {"header": "Value Date", "field": "value_date"}, {"header": "Debit Account No", "field": "debit_account"},
                 {"header": "Beneficiary Name", "field": "beneficiary_name"}, {"header": "Beneficiary Account No", "field": "beneficiary_account"},
                 {"header": "Beneficiary IFSC", "field": "ifsc"}, {"header": "Beneficiary Email", "field": "email"},
                 {"header": "Narration", "field": "narration"}, {"header": "Customer Ref No", "field": "customer_ref"}]},
    {"name": "ICICI — bulk upload (edit to match your ICICI template)", "bank": "ICICI", "file_type": "xlsx",
     "options": {"same_bank_ifsc": "ICIC", "mode_same_bank": "WIB", "mode_other": "NFT", "date_format": "%d/%m/%Y",
                 "narration": "SALARY {MONTH} {CODE}", "debit_account": ""},
     "columns": [{"header": "Pay Type", "field": "payment_mode"}, {"header": "Debit A/c No", "field": "debit_account"},
                 {"header": "Beneficiary A/c No", "field": "beneficiary_account"}, {"header": "Beneficiary Name", "field": "beneficiary_name"},
                 {"header": "Amount", "field": "amount"}, {"header": "IFSC", "field": "ifsc"}, {"header": "Remarks", "field": "narration"}]},
    {"name": "Generic NEFT (CSV)", "bank": "ANY", "file_type": "csv",
     "options": {"same_bank_ifsc": "", "mode_same_bank": "NEFT", "mode_other": "NEFT", "date_format": "%d-%m-%Y",
                 "narration": "SALARY {MONTH}", "debit_account": ""},
     "columns": [{"header": "Sr No", "field": "serial"}, {"header": "Beneficiary Name", "field": "beneficiary_name"},
                 {"header": "Account Number", "field": "beneficiary_account"}, {"header": "IFSC", "field": "ifsc"},
                 {"header": "Amount", "field": "amount"}, {"header": "Remarks", "field": "narration"}]},
]


def _tpl_out(t):
    return {"id": t.id, "name": t.name, "bank": t.bank, "file_type": t.file_type, "delimiter": t.delimiter,
            "include_header": bool(t.include_header), "columns": t.columns or [], "options": t.options or {},
            "is_default": bool(t.is_default)}


@router.get("/bank-templates")
def bank_templates(db: Session = Depends(get_db), user=Depends(_staff)):
    rows = db.query(models.BankFileTemplate).order_by(models.BankFileTemplate.is_default.desc(), models.BankFileTemplate.id).all()
    if not rows:
        for i, d in enumerate(DEFAULT_TEMPLATES):
            db.add(models.BankFileTemplate(**d, include_header=True, delimiter=",", is_default=(i == 0)))
        db.commit()
        rows = db.query(models.BankFileTemplate).order_by(models.BankFileTemplate.is_default.desc(), models.BankFileTemplate.id).all()
    return [_tpl_out(t) for t in rows]


def _tpl_apply(t, body):
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Give the format a name")
    cols = body.get("columns") or []
    if not cols:
        raise HTTPException(400, "Add at least one column")
    for c in cols:
        if c.get("field") not in docs.BANK_FIELDS:
            raise HTTPException(400, f"Unknown field '{c.get('field')}' for column '{c.get('header')}'")
    fields = [c["field"] for c in cols]
    for need in ("amount", "beneficiary_account"):
        if need not in fields:
            raise HTTPException(400, f"A bank file needs a column mapped to {docs.BANK_FIELDS[need]}")
    if (body.get("file_type") or "xlsx") not in ("xlsx", "csv", "txt"):
        raise HTTPException(400, "File type must be xlsx, csv or txt")
    t.name, t.bank = name[:80], (body.get("bank") or "")[:60]
    t.file_type, t.delimiter = body.get("file_type") or "xlsx", (body.get("delimiter") or ",")[:4]
    t.include_header = bool(body.get("include_header", True))
    t.columns = [{"header": str(c.get("header") or "")[:80], "field": c["field"], "value": str(c.get("value") or "")[:80]} for c in cols]
    t.options = {k: str(v)[:60] for k, v in (body.get("options") or {}).items()}


@router.post("/bank-templates")
def add_template(body: dict = Body(...), db: Session = Depends(get_db), user=Depends(_admin)):
    t = models.BankFileTemplate()
    _tpl_apply(t, body)
    db.add(t)
    audit.record(db, user, "payroll.bank_template", entity_type="payroll", detail=f"Bank format '{t.name}' added")
    db.commit()
    return _tpl_out(t)


@router.put("/bank-templates/{tid}")
def edit_template(tid: int, body: dict = Body(...), db: Session = Depends(get_db), user=Depends(_admin)):
    t = db.get(models.BankFileTemplate, tid)
    if not t:
        raise HTTPException(404, "Not found")
    _tpl_apply(t, body)
    if body.get("is_default"):
        db.query(models.BankFileTemplate).update({"is_default": False})
        t.is_default = True
    audit.record(db, user, "payroll.bank_template", entity_type="payroll", detail=f"Bank format '{t.name}' updated")
    db.commit()
    return _tpl_out(t)


@router.delete("/bank-templates/{tid}")
def del_template(tid: int, db: Session = Depends(get_db), user=Depends(_admin)):
    t = db.get(models.BankFileTemplate, tid)
    if not t:
        raise HTTPException(404, "Not found")
    audit.record(db, user, "payroll.bank_template", entity_type="payroll", detail=f"Bank format '{t.name}' deleted")
    db.delete(t); db.commit()
    return {"ok": True}


@router.post("/bank-templates/parse")
async def parse_template(file: UploadFile = File(...), user=Depends(_admin)):
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 5 MB)")
    try:
        return docs.parse_bank_sample(content, file.filename or "x.xlsx")
    except Exception as e:
        raise HTTPException(400, f"Could not read this file: {str(e)[:120]}")


# ───────────────────────────────────────────────────────────── my payslips (every employee)
@router.get("/my")
def my_payslips(db: Session = Depends(get_db), user=Depends(_me)):
    out = []
    for l, r in (db.query(models.PayrollLine, models.PayrollRun).join(models.PayrollRun, models.PayrollRun.id == models.PayrollLine.run_id)
                 .filter(models.PayrollLine.user_id == user.id, models.PayrollLine.included == True,  # noqa: E712
                         models.PayrollRun.released == True, models.PayrollRun.status.in_(("approved", "paid")))  # noqa: E712
                 .order_by(models.PayrollRun.period.desc())):
        out.append({"line_id": l.id, "period": r.period, "label": docs.period_label(r.period), "gross": _f(l.gross),
                    "deductions": _f(l.total_deductions), "net": _f(l.net), "pay_status": l.pay_status, "hold": bool(l.hold),
                    "paid_on": l.paid_on.isoformat() if l.paid_on else None, "earnings": l.earnings, "deductions_list": l.deductions})
    return out


@router.get("/my/{line_id}.pdf")
def my_payslip_pdf(line_id: int, db: Session = Depends(get_db), user=Depends(_me)):
    l = db.get(models.PayrollLine, line_id)
    if not l or l.user_id != user.id:
        raise HTTPException(404, "Payslip not found")
    run = db.get(models.PayrollRun, l.run_id)
    if not run or not run.released or run.status not in ("approved", "paid") or not l.included:
        raise HTTPException(404, "Payslip not released yet")
    pdf = docs.payslip_pdf([(run, l, _ytd(db, l))], run.rules_snapshot or get_cfg(db))
    return _file(pdf, f"Payslip_{run.period}.pdf", "application/pdf")
