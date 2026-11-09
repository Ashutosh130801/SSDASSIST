"""Payroll extras: income-tax declarations + projections, annual tax statement (Form 16 Part B layout),
24Q TDS summary, and Full & Final settlement for leavers. Same locks and roles as routers/payroll.py."""
from __future__ import annotations

import math
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import audit, models
from .. import payroll_docs as docs
from .. import payroll_engine as eng
from .. import tax_engine as tx
from ..database import get_db
from .payroll import (_admin, _check_secret, _days, _f, _file, _me, _num, _salary_for, _snapshot, _staff, _staff_users,
                      _taxable_parts, _today, get_cfg, project_tax, XLSX)

router = APIRouter(prefix="/api/payroll", tags=["payroll"])


# ───────────────────────────────────────────────────────────── income tax
def _cur_fy():
    return tx.fy_of(_today().strftime("%Y-%m"))


def _decl_out(d, uid, fy, cfg):
    return {"user_id": uid, "fy": fy, "regime": (d.regime if d else None) or (cfg.get("income_tax") or {}).get("default_regime", "new"),
            "metro": bool(d.metro) if d else False, "data": (d.data if d else {}) or {}, "locked": bool(d.locked) if d else False,
            "saved": bool(d), "updated_at": d.updated_at.isoformat() if d and d.updated_at else None}


def _save_decl(db, actor, uid, fy, body, cfg, staff: bool):
    d = db.query(models.TaxDeclaration).filter_by(user_id=uid, fy=fy).first()
    if d and d.locked and not staff:
        raise HTTPException(400, "Your declaration is locked by HR (proofs verified). Ask HR to change it.")
    if not d:
        d = models.TaxDeclaration(user_id=uid, fy=fy); db.add(d)
    regime = body.get("regime") or d.regime or "new"
    if regime not in ("new", "old"):
        raise HTTPException(400, "Regime must be new or old")
    data = {}
    for k in tx.DECL_FIELDS:
        v = (body.get("data") or {}).get(k)
        data[k] = float(_num(v, tx.DECL_FIELDS[k])) if v not in (None, "") else 0.0
    d.regime, d.metro, d.data, d.updated_by = regime, bool(body.get("metro")), data, actor.id
    if staff and "locked" in body:
        d.locked = bool(body["locked"])
    audit.record(db, actor, "payroll.tax_declaration", entity_type="payroll", target_user_id=uid,
                 detail=f"FY {fy}: {regime} regime" + (", locked" if d.locked else ""))
    return d


def _projection(db, u, cfg, fy=None):
    period = _today().strftime("%Y-%m")
    if fy and tx.fy_of(period) != fy:
        period = f"{int(fy[:4]) + 1}-03"                    # a past FY: project at its last month
    s = _salary_for(db, u.id, _today()) or _salary_for(db, u.id, date(2999, 1, 1))
    if not s:
        return None
    return project_tax(db, u, s, cfg, period, None)


@router.get("/tax/declarations")
def list_declarations(fy: str | None = None, db: Session = Depends(get_db), user=Depends(_staff)):
    cfg = get_cfg(db); fy = fy or _cur_fy()
    decls = {d.user_id: d for d in db.query(models.TaxDeclaration).filter_by(fy=fy)}
    out = []
    for u in _staff_users(db):
        if not u.is_active:
            continue
        p = _projection(db, u, cfg, fy)
        out.append({"id": u.id, "name": u.name, "emp_code": u.emp_code or u.hr_ref, "pan": u.pan_number,
                    "declaration": _decl_out(decls.get(u.id), u.id, fy, cfg),
                    "projection": p and {"regime": p["regime"], "annual_tax": p["annual"]["total"], "other_regime_tax": p["other"]["total"],
                                         "taxable": p["annual"]["taxable"], "monthly_tds": p["monthly_tds"], "tds_so_far": p["tds_so_far"]}})
    return {"fy": fy, "fields": tx.DECL_FIELDS, "rows": out}


@router.put("/tax/declarations/{uid}")
def put_declaration(uid: int, body: dict = Body(...), fy: str | None = None, db: Session = Depends(get_db), user=Depends(_staff)):
    if not db.get(models.User, uid):
        raise HTTPException(404, "Employee not found")
    cfg = get_cfg(db); fy = fy or _cur_fy()
    d = _save_decl(db, user, uid, fy, body, cfg, staff=True)
    db.commit()
    return _decl_out(d, uid, fy, cfg)


@router.get("/tax/preview/{uid}")
def tax_preview(uid: int, fy: str | None = None, db: Session = Depends(get_db), user=Depends(_staff)):
    u = db.get(models.User, uid)
    if not u:
        raise HTTPException(404, "Employee not found")
    p = _projection(db, u, get_cfg(db), fy)
    if not p:
        raise HTTPException(400, "Set this employee's salary first.")
    return p


@router.get("/my/tax")
def my_tax(fy: str | None = None, db: Session = Depends(get_db), user=Depends(_me)):
    cfg = get_cfg(db); fy = fy or _cur_fy()
    d = db.query(models.TaxDeclaration).filter_by(user_id=user.id, fy=fy).first()
    return {"fy": fy, "fields": tx.DECL_FIELDS, "declaration": _decl_out(d, user.id, fy, cfg),
            "allow_edit": bool((cfg.get("income_tax") or {}).get("allow_self_declaration", True)) and not (d and d.locked),
            "projection": _projection(db, user, cfg, fy)}


@router.put("/my/tax")
def put_my_tax(body: dict = Body(...), fy: str | None = None, db: Session = Depends(get_db), user=Depends(_me)):
    cfg = get_cfg(db); fy = fy or _cur_fy()
    if not (cfg.get("income_tax") or {}).get("allow_self_declaration", True):
        raise HTTPException(403, "HR enters tax declarations for your company.")
    d = _save_decl(db, user, user.id, fy, body, cfg, staff=False)
    db.commit()
    return my_tax(fy, db, user)


def _statement(db, u, fy, cfg) -> dict | None:
    periods = tx.fy_periods(fy)
    adj_types = {a["code"]: a for a in cfg.get("adjustment_types") or []}
    rows = (db.query(models.PayrollLine, models.PayrollRun).join(models.PayrollRun, models.PayrollRun.id == models.PayrollLine.run_id)
            .filter(models.PayrollLine.user_id == u.id, models.PayrollLine.included == True,  # noqa: E712
                    models.PayrollRun.period.in_(periods), models.PayrollRun.status.in_(("approved", "paid")))
            .order_by(models.PayrollRun.period).all())
    if not rows:
        return None
    tot = {"gross": 0.0, "basic": 0.0, "hra": 0.0, "pf": 0.0, "pt": 0.0, "tds": 0.0}
    months = []
    for l, r in rows:
        p = _taxable_parts({"earnings": l.earnings, "deductions": l.deductions}, adj_types)
        for k in tot:
            tot[k] += p[k]
        months.append({"label": docs.period_label(r.period), "gross": p["gross"], "tds": p["tds"],
                       "pay_date": r.pay_date.strftime("%d-%b-%Y") if r.pay_date else None})
    d = db.query(models.TaxDeclaration).filter_by(user_id=u.id, fy=fy).first()
    regime = (d.regime if d else None) or (cfg.get("income_tax") or {}).get("default_regime", "new")
    data = (d.data if d else {}) or {}
    last = f"{int(fy[:4]) + 1}-03"
    provisional = not any(r.period == last for _, r in rows)
    tax = tx.compute_annual(regime=regime, cfg=cfg.get("income_tax") or tx.DEFAULT_TAX, gross=tot["gross"], basic=tot["basic"],
                            hra=tot["hra"], pf=tot["pf"], pt=tot["pt"], decl=data, metro=bool(d.metro) if d else False)
    if provisional:
        # Year not finished: show the same full-year projection the monthly TDS is based on.
        l_last, r_last = rows[-1]
        s = _salary_for(db, u.id, r_last.cycle_end)
        if s:
            p = project_tax(db, u, s, cfg, r_last.period, _taxable_parts({"earnings": l_last.earnings, "deductions": l_last.deductions}, adj_types),
                            exclude_run_id=r_last.id)
            tax = p["annual"]
    snap = rows[-1][0].snapshot or {}
    return {"employee": {**snap, "pan": u.pan_number or snap.get("pan")}, "fy": fy, "months": months, "tax": tax, "regime": regime,
            "tds_total": round(tot["tds"] + float(data.get("tds_outside") or 0), 2), "prev_income": float(data.get("prev_employer_income") or 0),
            "provisional": provisional}


@router.get("/tax/form16.pdf")
def form16(fy: str | None = None, user_id: int | None = None, db: Session = Depends(get_db), user=Depends(_staff)):
    cfg = get_cfg(db); fy = fy or _cur_fy()
    users = [db.get(models.User, user_id)] if user_id else _staff_users(db)
    items = [s for s in (_statement(db, u, fy, cfg) for u in users if u) if s]
    if not items:
        raise HTTPException(404, "No approved payroll in this financial year yet.")
    audit.record(db, user, "download", entity_type="payroll", detail=f"Annual tax statements FY {fy} ({len(items)})"); db.commit()
    return _file(docs.form16_pdf(items, cfg), f"Tax_Statement_FY{fy}{'_' + str(user_id) if user_id else ''}.pdf", "application/pdf")


@router.get("/my/form16.pdf")
def my_form16(fy: str | None = None, db: Session = Depends(get_db), user=Depends(_me)):
    cfg = get_cfg(db); fy = fy or _cur_fy()
    s = _statement(db, user, fy, cfg)
    if not s:
        raise HTTPException(404, "No approved payroll in this financial year yet.")
    return _file(docs.form16_pdf([s], cfg), f"Tax_Statement_FY{fy}.pdf", "application/pdf")


@router.get("/tax/24q.xlsx")
def tds_24q(fy: str | None = None, quarter: str = Query("Q1", pattern="^Q[1-4]$"), db: Session = Depends(get_db), user=Depends(_staff)):
    fy = fy or _cur_fy()
    periods = tx.fy_periods(fy)[(int(quarter[1]) - 1) * 3:(int(quarter[1])) * 3]
    rows = []
    q = (db.query(models.PayrollLine, models.PayrollRun).join(models.PayrollRun, models.PayrollRun.id == models.PayrollLine.run_id)
         .filter(models.PayrollRun.period.in_(periods), models.PayrollRun.status.in_(("approved", "paid")),
                 models.PayrollLine.included == True).order_by(models.PayrollRun.period))  # noqa: E712
    users = {u.id: u for u in db.query(models.User).all()}
    for l, r in q:
        s = l.snapshot or {}
        tds = sum(d["amount"] for d in l.deductions or [] if d["code"] == "TDS")
        u = users.get(l.user_id)
        rows.append([docs.period_label(r.period), s.get("emp_code"), s.get("name"), (u.pan_number if u else None) or "PANNOTAVBL",
                     "192", r.pay_date.strftime("%d-%m-%Y") if r.pay_date else "", float(l.gross), float(tds),
                     ((l.attendance or {}).get("tax") or {}).get("regime", "")])
    return _file(docs.tds_24q_xlsx(rows, fy, quarter), f"TDS_24Q_FY{fy}_{quarter}.xlsx", XLSX)


# ───────────────────────────────────────────────────────────── full & final settlement
def _fnf_out(f, names):
    return {"id": f.id, "user_id": f.user_id, "name": names.get(f.user_id), "last_working_day": f.last_working_day.isoformat(),
            "reason": f.reason, "status": f.status, "items": f.items or [], "workings": f.workings or {},
            "total_earnings": _f(f.total_earnings), "total_deductions": _f(f.total_deductions), "net": _f(f.net), "note": f.note,
            "approved_at": f.approved_at.isoformat() if f.approved_at else None, "paid_on": f.paid_on.isoformat() if f.paid_on else None,
            "utr": f.utr, "created_at": f.created_at.isoformat() if f.created_at else None}


def _period_for(day: date, start_day: int) -> str:
    if start_day <= 1 or day.day < start_day:
        return day.strftime("%Y-%m")
    y, m = (day.year + 1, 1) if day.month == 12 else (day.year, day.month + 1)
    return f"{y}-{m:02d}"


@router.post("/fnf/preview")
def fnf_preview(body: dict = Body(...), db: Session = Depends(get_db), user=Depends(_staff)):
    """Suggested settlement lines for a leaver (all editable before saving)."""
    from .leaves import DEFAULT_ALLOWANCE, _year_totals
    u = db.get(models.User, int(body.get("user_id") or 0))
    if not u:
        raise HTTPException(404, "Employee not found")
    try:
        lwd = date.fromisoformat(str(body.get("last_working_day"))[:10])
    except ValueError:
        raise HTTPException(400, "Last working day must be a date")
    cfg = get_cfg(db)
    fc = cfg.get("fnf") or {}
    s = _salary_for(db, u.id, lwd)
    if not s:
        raise HTTPException(400, "Set this employee's salary first (Employee salaries).")
    parts = {p["code"]: float(p["full"]) for p in eng.split_gross(s.monthly_gross, cfg["components"], s.overrides)}
    gross_m, basic_m = float(s.monthly_gross), parts.get("BASIC", 0.0)
    items, work = [], {}

    # 1. salary for the last (unpaid) cycle
    period = _period_for(lwd, int(cfg["cycle"].get("start_day") or 1))
    cs, ce = eng.cycle_for(period, int(cfg["cycle"].get("start_day") or 1))
    paid_run = (db.query(models.PayrollLine).join(models.PayrollRun, models.PayrollRun.id == models.PayrollLine.run_id)
                .filter(models.PayrollRun.period == period, models.PayrollRun.status.in_(("approved", "paid")),
                        models.PayrollLine.user_id == u.id, models.PayrollLine.included == True).first())  # noqa: E712
    if paid_run:
        work["salary"] = f"{docs.period_label(period)} salary already paid in the payroll run — not repeated here."
    else:
        days = _days(db, u, cs, ce, cfg)
        att = eng.attendance_lop(days, cfg, cs, ce, u.joining_date if u.joining_date and cs <= u.joining_date <= ce else None,
                                 lwd, bool(s.attendance_exempt))
        res = eng.compute_line(gross_monthly=s.monthly_gross, components=cfg["components"], overrides=s.overrides, att=att,
                               paid_days_override=None, adjustments=[], adj_types={}, advances=[],
                               flags_in={"pf": s.pf_applicable, "esi": s.esi_applicable, "pt": s.pt_applicable, "lwf": False, "tds": 0},
                               cfg=cfg, period=period)
        rng = f"{cs.strftime('%d %b')} – {lwd.strftime('%d %b %Y')}"
        if res["gross"] > 0:
            items.append({"kind": "earning", "code": "SALARY", "name": f"Salary {rng}", "amount": res["gross"],
                          "note": f"{res['paid_days']:g} paid days"})
            for d in res["deductions"]:
                items.append({"kind": "deduction", "code": d["code"], "name": d["name"], "amount": d["amount"], "note": "on last salary"})
        work["salary"] = f"Cycle {cs:%d %b}–{ce:%d %b}: paid days {res['paid_days']:g} of {att['divisor']:g} (LOP {att['lop']:g}, after LWD not employed)."

    # 2. leave encashment
    types = fc.get("encash_leave_types") or ["Earned"]
    tot = _year_totals(db, [u.id], lwd.year).get(u.id, {})
    bal = sum(max(0.0, DEFAULT_ALLOWANCE.get(t, 0) - tot.get(t, {}).get("approved", 0.0)) for t in types)
    if body.get("encash_days") not in (None, ""):
        bal = float(body["encash_days"])
    bal = min(bal, float(fc.get("encash_max_days") or 9999))
    per_day = (basic_m if fc.get("encash_basis", "basic") == "basic" else gross_m) / float(fc.get("encash_divisor") or 30)
    if bal > 0:
        items.append({"kind": "earning", "code": "LEAVE_ENCASH", "name": "Leave encashment", "amount": round(bal * per_day, 2),
                      "note": f"{bal:g} day(s) × ₹{per_day:,.2f}"})
    work["leave"] = f"{', '.join(types)} leave balance {bal:g} day(s); per day = {fc.get('encash_basis', 'basic')} ÷ {fc.get('encash_divisor', 30)}."

    # 3. gratuity
    if u.joining_date:
        svc = (lwd - u.joining_date).days
        yrs = svc / 365.25
        completed = math.floor(yrs) + (1 if yrs - math.floor(yrs) >= 0.5 else 0)
        min_y = int(fc.get("gratuity_min_years") or 5)
        eligible = svc >= (min_y - 1) * 365 + 240
        if eligible and completed > 0:
            amt = min(15 / 26 * basic_m * completed, float(fc.get("gratuity_cap") or 2000000))
            items.append({"kind": "earning", "code": "GRATUITY", "name": "Gratuity", "amount": round(amt, 2),
                          "note": f"15/26 × ₹{basic_m:,.0f} × {completed} yr"})
        work["gratuity"] = f"Service {yrs:.2f} years ({'eligible' if eligible else f'not eligible — needs {min_y} years'})."
    else:
        work["gratuity"] = "No joining date in Manpower — gratuity not worked out."

    # 4. notice period
    notice = int(body.get("notice_days") if body.get("notice_days") not in (None, "") else fc.get("notice_days") or 0)
    served = int(body.get("notice_served_days") or 0)
    short = max(0, notice - served)
    day_gross = gross_m / 30
    if short and not body.get("waive_notice"):
        items.append({"kind": "deduction", "code": "NOTICE_RECOVERY", "name": "Notice period shortfall", "amount": round(short * day_gross, 2),
                      "note": f"{short} day(s) × ₹{day_gross:,.2f}"})
    pay_days = int(body.get("notice_pay_days") or 0)
    if pay_days:
        items.append({"kind": "earning", "code": "NOTICE_PAY", "name": "Notice pay in lieu", "amount": round(pay_days * day_gross, 2),
                      "note": f"{pay_days} day(s)"})
    work["notice"] = f"Notice {notice} days, served {served}" + (" (waived)" if body.get("waive_notice") else "") + "."

    # 5. advances / loans still open
    for a in db.query(models.SalaryAdvance).filter_by(user_id=u.id, status="active"):
        if float(a.balance or 0) > 0:
            items.append({"kind": "deduction", "code": "ADVANCE", "name": f"{a.kind.capitalize()} balance", "amount": float(a.balance),
                          "note": f"#{a.id}", "advance_id": a.id})
    return {"user_id": u.id, "name": u.name, "last_working_day": lwd.isoformat(), "items": items, "workings": work,
            "employee": _snapshot(u, s, cfg)}


def _totals(items):
    clean = []
    for i in items or []:
        if i.get("kind") not in ("earning", "deduction"):
            raise HTTPException(400, "Each line must be an earning or a deduction")
        amt = float(_num(i.get("amount") or 0, i.get("name") or "Amount"))
        if not (i.get("name") or "").strip():
            raise HTTPException(400, "Every line needs a name")
        clean.append({"kind": i["kind"], "code": str(i.get("code") or "OTHER")[:20], "name": str(i["name"])[:80], "amount": amt,
                      "note": str(i.get("note") or "")[:120], **({"advance_id": i["advance_id"]} if i.get("advance_id") else {})})
    e = round(sum(i["amount"] for i in clean if i["kind"] == "earning"), 2)
    d = round(sum(i["amount"] for i in clean if i["kind"] == "deduction"), 2)
    return clean, e, d, round(e - d)


@router.get("/fnf")
def fnf_list(db: Session = Depends(get_db), user=Depends(_staff)):
    rows = db.query(models.FnfSettlement).order_by(models.FnfSettlement.id.desc()).all()
    names = {u.id: u.name for u in db.query(models.User).filter(models.User.id.in_({r.user_id for r in rows} or {0}))}
    return [_fnf_out(r, names) for r in rows]


@router.post("/fnf")
def fnf_create(body: dict = Body(...), db: Session = Depends(get_db), user=Depends(_staff)):
    u = db.get(models.User, int(body.get("user_id") or 0))
    if not u:
        raise HTTPException(404, "Employee not found")
    if db.query(models.FnfSettlement).filter(models.FnfSettlement.user_id == u.id, models.FnfSettlement.status != "cancelled").first():
        raise HTTPException(400, f"{u.name} already has a settlement — open it instead.")
    items, e, d, net = _totals(body.get("items"))
    f = models.FnfSettlement(user_id=u.id, last_working_day=date.fromisoformat(str(body["last_working_day"])[:10]),
                             reason=(body.get("reason") or "resigned")[:40], items=items, workings=body.get("workings") or {},
                             total_earnings=e, total_deductions=d, net=net, note=(body.get("note") or "")[:2000] or None, created_by=user.id)
    db.add(f)
    audit.record(db, user, "payroll.fnf_create", entity_type="payroll", target_user_id=u.id, detail=f"F&F draft for {u.name}: net ₹{net:,.0f}")
    db.commit()
    return _fnf_out(f, {u.id: u.name})


@router.put("/fnf/{fid}")
def fnf_update(fid: int, body: dict = Body(...), db: Session = Depends(get_db), user=Depends(_staff)):
    f = db.get(models.FnfSettlement, fid)
    if not f:
        raise HTTPException(404, "Not found")
    if f.status != "draft":
        raise HTTPException(400, "Only a draft settlement can be edited.")
    items, e, d, net = _totals(body.get("items"))
    f.items, f.total_earnings, f.total_deductions, f.net = items, e, d, net
    if body.get("reason"):
        f.reason = body["reason"][:40]
    if "note" in body:
        f.note = (body.get("note") or "")[:2000] or None
    if body.get("last_working_day"):
        f.last_working_day = date.fromisoformat(str(body["last_working_day"])[:10])
    audit.record(db, user, "payroll.fnf_update", entity_type="payroll", target_user_id=f.user_id, detail=f"F&F #{f.id}: net ₹{net:,.0f}")
    db.commit()
    return _fnf_out(f, {f.user_id: (db.get(models.User, f.user_id) or models.User(name="?")).name})


@router.post("/fnf/{fid}/approve")
def fnf_approve(fid: int, body: dict = Body(...), db: Session = Depends(get_db), user=Depends(_admin)):
    f = db.get(models.FnfSettlement, fid)
    if not f or f.status != "draft":
        raise HTTPException(400, "Only a draft settlement can be approved.")
    _check_secret(user, body.get("password"), body.get("otp"))
    try:
        typed = Decimal(str(body.get("confirm_total")).replace(",", ""))
    except Exception:
        raise HTTPException(400, "Type the net amount to confirm")
    if abs(typed) .quantize(Decimal("1")) != abs(Decimal(str(f.net))).quantize(Decimal("1")):
        raise HTTPException(400, f"Typed amount does not match the net ₹{_f(f.net):,.0f}")
    for i in f.items or []:
        if i.get("advance_id"):
            a = db.get(models.SalaryAdvance, i["advance_id"])
            if a:
                a.balance = max(Decimal("0"), Decimal(str(a.balance)) - Decimal(str(i["amount"])))
                if a.balance <= 0:
                    a.status = "closed"
    u = db.get(models.User, f.user_id)
    if body.get("mark_left", True) and u and u.is_active:
        u.is_active = False
        u.blocked_reason = "Left — full & final settled"
        u.blocked_at = datetime.combine(f.last_working_day, datetime.min.time())
        u.blocked_by = user.id
    f.status, f.approved_by, f.approved_at = "approved", user.id, datetime.now(timezone.utc)
    audit.record(db, user, "payroll.fnf_approve", entity_type="payroll", target_user_id=f.user_id,
                 detail=f"F&F approved for {u.name if u else f.user_id}: net ₹{_f(f.net):,.0f}" + ("; marked as left" if body.get("mark_left", True) else ""))
    db.commit()
    return _fnf_out(f, {f.user_id: u.name if u else "?"})


@router.post("/fnf/{fid}/paid")
def fnf_paid(fid: int, body: dict = Body(default={}), db: Session = Depends(get_db), user=Depends(_admin)):
    f = db.get(models.FnfSettlement, fid)
    if not f or f.status != "approved":
        raise HTTPException(400, "Approve the settlement first.")
    f.status = "paid"
    f.paid_on = date.fromisoformat(str(body.get("paid_on") or _today().isoformat())[:10])
    f.utr = (body.get("utr") or "")[:40] or None
    audit.record(db, user, "payroll.fnf_paid", entity_type="payroll", target_user_id=f.user_id, detail=f"F&F #{f.id} paid {f.paid_on} {f.utr or ''}")
    db.commit()
    u = db.get(models.User, f.user_id)
    return _fnf_out(f, {f.user_id: u.name if u else "?"})


@router.post("/fnf/{fid}/cancel")
def fnf_cancel(fid: int, db: Session = Depends(get_db), user=Depends(_admin)):
    f = db.get(models.FnfSettlement, fid)
    if not f or f.status != "draft":
        raise HTTPException(400, "Only a draft settlement can be cancelled.")
    f.status = "cancelled"
    audit.record(db, user, "payroll.fnf_cancel", entity_type="payroll", target_user_id=f.user_id, detail=f"F&F #{f.id} cancelled")
    db.commit()
    return {"ok": True}


@router.get("/fnf/{fid}.pdf")
def fnf_letter(fid: int, db: Session = Depends(get_db), user=Depends(_staff)):
    f = db.get(models.FnfSettlement, fid)
    if not f:
        raise HTTPException(404, "Not found")
    cfg = get_cfg(db)
    u = db.get(models.User, f.user_id)
    s = _salary_for(db, u.id, f.last_working_day) or _salary_for(db, u.id, date(2999, 1, 1))
    emp = _snapshot(u, s, cfg) if s else {"name": u.name, "emp_code": u.emp_code}
    return _file(docs.fnf_pdf(f, emp, cfg), f"FnF_{emp.get('emp_code') or u.id}.pdf", "application/pdf")
