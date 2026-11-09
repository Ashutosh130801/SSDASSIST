"""Payroll calculation engine — configurable for any organisation.

Everything that differs between companies lives in the payroll config (rules), not in code:
salary cycle, pay-day basis, attendance/LOP rules, salary components, statutory deductions
(PF / ESI / Professional Tax / LWF / TDS), adjustment types and payslip settings.

All money is Decimal; the net is rounded per the config. Pure functions where possible so the
maths is unit-tested without a database.
"""
from __future__ import annotations

import copy
import calendar
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING

from .tax_engine import DEFAULT_TAX

D = Decimal
ZERO = D("0")


def q2(x) -> Decimal:
    return D(str(x or 0)).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def rupee(x) -> Decimal:
    return D(str(x or 0)).quantize(D("1"), rounding=ROUND_HALF_UP)


def ceil_rupee(x) -> Decimal:
    return D(str(x or 0)).quantize(D("1"), rounding=ROUND_CEILING)


# ───────────────────────────────────────────────────────────── default rules
DEFAULT_COMPONENTS = [
    {"code": "BASIC", "name": "Basic Salary", "calc": "percent_gross", "value": 50, "prorate": True, "pf": True, "esi": True},
    {"code": "HRA", "name": "House Rent Allowance", "calc": "percent_basic", "value": 40, "prorate": True, "pf": False, "esi": True},
    {"code": "CONV", "name": "Conveyance Allowance", "calc": "fixed", "value": 1600, "prorate": True, "pf": False, "esi": True},
    {"code": "SPECIAL", "name": "Special Allowance", "calc": "balance", "value": 0, "prorate": True, "pf": False, "esi": True},
]

DEFAULT_ADJUSTMENT_TYPES = [
    {"code": "INCENTIVE", "name": "Performance Incentive", "kind": "earning", "esi": True, "pt": True},
    {"code": "BONUS", "name": "Bonus", "kind": "earning", "esi": False, "pt": True},
    {"code": "ARREARS", "name": "Arrears", "kind": "earning", "esi": True, "pt": True},
    {"code": "OVERTIME", "name": "Overtime", "kind": "earning", "esi": True, "pt": True},
    {"code": "REIMB", "name": "Reimbursement", "kind": "earning", "esi": False, "pt": False, "taxable": False},
    {"code": "OTHER_EARN", "name": "Other Earning", "kind": "earning", "esi": True, "pt": True},
    {"code": "FINE", "name": "Penalty / Fine", "kind": "deduction"},
    {"code": "OTHER_DED", "name": "Other Deduction", "kind": "deduction"},
]

# Professional-tax slabs (monthly gross → tax). Andhra Pradesh / Telangana as the starting point;
# each org edits its own state's slabs in Settings.
DEFAULT_PT_SLABS = [
    {"min": 0, "max": 15000, "amount": 0},
    {"min": 15000.01, "max": 20000, "amount": 150},
    {"min": 20000.01, "max": None, "amount": 200},
]

DEFAULT_CONFIG = {
    "company": {"name": "", "address": "", "logo": "", "pan": "", "tan": "", "pf_code": "", "esi_code": "",
                "signatory": "", "footer": "This is a computer-generated payslip and does not require a signature."},
    "cycle": {"start_day": 21, "pay_day": 0},        # start_day 1 = calendar month; pay_day 0 = last day of month
    "pay_basis": "calendar",                         # calendar | fixed_30 | fixed_26 | working
    "attendance": {
        "use_attendance": True,                      # absences / half days from Attendance cut pay
        "unpaid_leave_keywords": ["unpaid", "lop", "without pay"],
        "late_every": 3, "late_deduct_days": 0.5,    # every 3 late marks = 0.5 day LOP (0 = off)
    },
    "components": DEFAULT_COMPONENTS,
    "adjustment_types": DEFAULT_ADJUSTMENT_TYPES,
    "statutory": {
        "pf": {"enabled": True, "employee_rate": 12, "employer_rate": 12, "eps_rate": 8.33,
               "wage_ceiling": 15000, "restrict_to_ceiling": True},
        "esi": {"enabled": True, "employee_rate": 0.75, "employer_rate": 3.25, "threshold": 21000},
        "pt": {"enabled": True, "state": "Andhra Pradesh", "slabs": DEFAULT_PT_SLABS},
        "lwf": {"enabled": False, "employee": 0, "employer": 0, "months": [6, 12]},
    },
    "rounding": "rupee",                             # rupee | paise
    "checks": {"net_change_pct": 25},
    "payslip": {"show_employer": True, "show_attendance": True, "show_ytd": True,
                "title": "PAYSLIP", "accent": "#1E3A8A"},
    "income_tax": DEFAULT_TAX,
    "fnf": {"notice_days": 30, "encash_leave_types": ["Earned"], "encash_basis": "basic", "encash_divisor": 30,
            "encash_max_days": 45, "gratuity_min_years": 5, "gratuity_cap": 2000000},
}


def merged_config(stored: dict | None) -> dict:
    """Stored config over the defaults (new keys added later still get a value)."""
    cfg = copy.deepcopy(DEFAULT_CONFIG)

    def deep(dst, src):
        for k, v in (src or {}).items():
            if isinstance(v, dict) and isinstance(dst.get(k), dict):
                deep(dst[k], v)
            else:
                dst[k] = v
    deep(cfg, stored or {})
    return cfg


def validate_config(cfg: dict) -> list[str]:
    errs = []
    comps = cfg.get("components") or []
    codes = [c.get("code") for c in comps]
    if not comps:
        errs.append("At least one salary component is needed.")
    if len(set(codes)) != len(codes):
        errs.append("Component codes must be unique.")
    if sum(1 for c in comps if c.get("calc") == "balance") > 1:
        errs.append("Only one component can take the balance.")
    for c in comps:
        if c.get("calc") not in ("percent_gross", "percent_basic", "fixed", "balance"):
            errs.append(f"{c.get('code')}: unknown calculation '{c.get('calc')}'.")
        if not str(c.get("code") or "").strip() or not str(c.get("name") or "").strip():
            errs.append("Every component needs a code and a name.")
    if any(c.get("calc") == "percent_basic" for c in comps) and "BASIC" not in codes:
        errs.append("A '% of Basic' component needs a component with code BASIC.")
    sd = int((cfg.get("cycle") or {}).get("start_day") or 1)
    if not 1 <= sd <= 28:
        errs.append("Cycle start day must be between 1 and 28.")
    if cfg.get("pay_basis") not in ("calendar", "fixed_30", "fixed_26", "working"):
        errs.append("Unknown pay-day basis.")
    akinds = [a.get("code") for a in cfg.get("adjustment_types") or []]
    if len(set(akinds)) != len(akinds):
        errs.append("Adjustment type codes must be unique.")
    return errs


# ───────────────────────────────────────────────────────────── cycle
def cycle_for(period: str, start_day: int) -> tuple[date, date]:
    """period YYYY-MM = the month the cycle ENDS in. start_day 21 → 21 Oct … 20 Nov for 2026-11;
    start_day 1 → the calendar month."""
    y, m = int(period[:4]), int(period[5:7])
    if start_day <= 1:
        return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])
    end = date(y, m, start_day - 1)
    py, pm = (y - 1, 12) if m == 1 else (y, m - 1)
    return date(py, pm, start_day), end


def pay_date_for(period: str, pay_day: int) -> date:
    y, m = int(period[:4]), int(period[5:7])
    last = calendar.monthrange(y, m)[1]
    return date(y, m, last if not pay_day or pay_day > last else pay_day)


# ───────────────────────────────────────────────────────────── structure
def split_gross(gross, components, overrides=None) -> list[dict]:
    """Monthly gross → full (unprorated) component amounts."""
    gross = q2(gross)
    overrides = {k: q2(v) for k, v in (overrides or {}).items() if v not in (None, "")}
    out, by = [], {}
    for c in components:                                   # pass 1: % of gross, fixed, overrides
        code = c["code"]
        if code in overrides:
            amt = overrides[code]
        elif c["calc"] == "percent_gross":
            amt = q2(gross * D(str(c.get("value") or 0)) / 100)
        elif c["calc"] == "fixed":
            amt = q2(c.get("value") or 0)
        else:
            continue
        by[code] = amt
    for c in components:                                   # pass 2: % of basic
        if c["code"] not in by and c["calc"] == "percent_basic":
            by[c["code"]] = q2(by.get("BASIC", ZERO) * D(str(c.get("value") or 0)) / 100)
    used = sum(by.values(), ZERO)
    for c in components:                                   # pass 3: balance
        if c["code"] not in by and c["calc"] == "balance":
            by[c["code"]] = max(ZERO, gross - used)
    # never exceed the gross: trim from the last non-balance components if % add up too high
    over = sum(by.values(), ZERO) - gross
    if over > 0:
        for c in reversed(components):
            if over <= 0:
                break
            cut = min(by.get(c["code"], ZERO), over)
            by[c["code"]] = by.get(c["code"], ZERO) - cut
            over -= cut
    for c in components:
        out.append({"code": c["code"], "name": c["name"], "full": by.get(c["code"], ZERO),
                    "prorate": c.get("prorate", True), "pf": bool(c.get("pf")), "esi": c.get("esi", True)})
    return out


# ───────────────────────────────────────────────────────────── attendance → LOP
def attendance_lop(days: list[dict], cfg: dict, cycle_start: date, cycle_end: date,
                   joining: date | None, exit_day: date | None, exempt: bool) -> dict:
    """days = one dict per cycle day from leave_policy.day_credit (+ 'date', 'unpaid_leave').
    Returns counts + LOP in the pay-basis unit + the divisor."""
    att = cfg.get("attendance") or {}
    n = (cycle_end - cycle_start).days + 1
    sundays = sum(1 for i in range(n) if (cycle_start + timedelta(days=i)).weekday() == 6)
    basis = cfg.get("pay_basis", "calendar")
    divisor = {"calendar": D(n), "fixed_30": D(30), "fixed_26": D(26), "working": D(n - sundays)}[basis]
    # LOP days are actual days; days before joining / after leaving scale to the basis (a 26-day
    # basis month with 31 calendar days counts 10 not-employed days as 10 × 26/31).
    ne_unit = divisor / D(n) if basis in ("fixed_30", "fixed_26") else D(1)

    present = leave = absent = unpaid = ZERO
    late = half = weekoff = 0
    not_employed = ZERO
    for d in days:
        day = d["date"]
        if (joining and day < joining) or (exit_day and day > exit_day):
            if basis == "working" and day.weekday() == 6:
                continue
            not_employed += 1
            continue
        present += D(str(d.get("present", 0)))
        leave += D(str(d.get("leave", 0)))
        absent += D(str(d.get("absent", 0)))
        unpaid += D(str(d.get("unpaid_leave", 0)))
        late += int(d.get("late", 0))
        half += int(d.get("half_days", 0)) + int(d.get("late_half", 0))
        weekoff += int(d.get("weekoff", 0))
    late_lop = ZERO
    every = int(att.get("late_every") or 0)
    if every > 0 and D(str(att.get("late_deduct_days") or 0)) > 0:
        late_lop = D(late // every) * D(str(att.get("late_deduct_days")))
    use = att.get("use_attendance", True) and not exempt
    lop_days = (absent + unpaid + late_lop) if use else ZERO
    lop = q2(lop_days + not_employed * ne_unit)
    lop = min(lop, divisor)
    return {"cycle_days": n, "divisor": float(divisor), "basis": basis,
            "present": float(present), "leave": float(leave), "absent": float(absent),
            "unpaid_leave": float(unpaid), "late": late, "late_lop": float(late_lop), "half_days": half,
            "weekoff": weekoff, "not_employed": float(not_employed), "attendance_used": bool(use),
            "lop": float(lop), "paid_days": float(q2(divisor - lop))}


# ───────────────────────────────────────────────────────────── statutory
def pt_for(amount, slabs) -> Decimal:
    amount = q2(amount)
    for s in slabs or []:
        lo = q2(s.get("min") or 0)
        hi = s.get("max")
        if amount >= lo and (hi in (None, "") or amount <= q2(hi)):
            return q2(s.get("amount") or 0)
    return ZERO


def compute_line(*, gross_monthly, components, overrides, att: dict, paid_days_override,
                 adjustments: list[dict], adj_types: dict, advances: list[dict], flags_in: dict,
                 cfg: dict, period: str) -> dict:
    """One employee's payslip. adjustments = [{kind, code, amount, note}]; advances =
    [{id, emi, balance}] active for this period. flags_in = pf/esi/pt/lwf applicable + tds."""
    divisor = D(str(att["divisor"]))
    paid = D(str(paid_days_override)) if paid_days_override is not None else D(str(att["paid_days"]))
    paid = max(ZERO, min(paid, divisor))
    factor = paid / divisor if divisor else ZERO

    parts = split_gross(gross_monthly, components, overrides)
    earnings = []
    pf_base = esi_base = pt_base = ZERO
    for p in parts:
        amt = q2(p["full"] * factor) if p["prorate"] else p["full"]
        earnings.append({"code": p["code"], "name": p["name"], "full": float(p["full"]), "amount": float(amt)})
        if p["pf"]:
            pf_base += amt
        if p["esi"]:
            esi_base += amt
        pt_base += amt
    for a in adjustments:
        if a["kind"] != "earning":
            continue
        t = adj_types.get(a["code"], {})
        amt = q2(a["amount"])
        earnings.append({"code": a["code"], "name": t.get("name", a["code"]), "full": float(amt),
                         "amount": float(amt), "note": a.get("note") or "", "adjustment": True})
        if t.get("esi", True):
            esi_base += amt
        if t.get("pt", True):
            pt_base += amt
    gross = q2(sum((D(str(e["amount"])) for e in earnings), ZERO))

    st = cfg.get("statutory") or {}
    deductions, employer = [], []

    pf = st.get("pf") or {}
    if pf.get("enabled") and flags_in.get("pf"):
        ceiling = q2(pf.get("wage_ceiling") or 15000)
        pf_wage = min(pf_base, ceiling) if pf.get("restrict_to_ceiling", True) else pf_base
        ee = rupee(pf_wage * D(str(pf.get("employee_rate", 12))) / 100)
        er_total = rupee(pf_wage * D(str(pf.get("employer_rate", 12))) / 100)
        eps = rupee(min(pf_base, ceiling) * D(str(pf.get("eps_rate", 8.33))) / 100)
        eps = min(eps, er_total)
        if ee > 0:
            deductions.append({"code": "PF", "name": f"Provident Fund ({pf.get('employee_rate', 12)}%)", "amount": float(ee)})
        if er_total > 0:
            employer.append({"code": "PF_EPS", "name": "Employer PF — Pension (EPS)", "amount": float(eps)})
            employer.append({"code": "PF_EPF", "name": "Employer PF — EPF", "amount": float(er_total - eps)})
        att_pf = {"pf_wage": float(pf_wage), "eps_wage": float(min(pf_base, ceiling)), "edli_wage": float(min(pf_base, ceiling))}
    else:
        att_pf = {"pf_wage": 0.0, "eps_wage": 0.0, "edli_wage": 0.0}

    esi = st.get("esi") or {}
    esi_full = q2(gross_monthly)
    esi_wage = ZERO
    if esi.get("enabled") and flags_in.get("esi") and esi_full <= q2(esi.get("threshold") or 21000):
        esi_wage = esi_base
        ee = ceil_rupee(esi_base * D(str(esi.get("employee_rate", 0.75))) / 100)
        er = ceil_rupee(esi_base * D(str(esi.get("employer_rate", 3.25))) / 100)
        if ee > 0:
            deductions.append({"code": "ESI", "name": f"ESI ({esi.get('employee_rate', 0.75)}%)", "amount": float(ee)})
        if er > 0:
            employer.append({"code": "ESI_ER", "name": "Employer ESI", "amount": float(er)})

    pt = st.get("pt") or {}
    if pt.get("enabled") and flags_in.get("pt"):
        tax = pt_for(pt_base, pt.get("slabs"))
        if tax > 0:
            deductions.append({"code": "PT", "name": "Professional Tax", "amount": float(tax)})

    lwf = st.get("lwf") or {}
    if lwf.get("enabled") and flags_in.get("lwf") and int(period[5:7]) in [int(x) for x in (lwf.get("months") or [])]:
        if q2(lwf.get("employee") or 0) > 0:
            deductions.append({"code": "LWF", "name": "Labour Welfare Fund", "amount": float(q2(lwf.get("employee")))})
        if q2(lwf.get("employer") or 0) > 0:
            employer.append({"code": "LWF_ER", "name": "Employer LWF", "amount": float(q2(lwf.get("employer")))})

    tds = q2(flags_in.get("tds") or 0)
    if tds > 0:
        deductions.append({"code": "TDS", "name": "Income Tax (TDS)", "amount": float(tds)})

    for a in adjustments:
        if a["kind"] == "deduction":
            t = adj_types.get(a["code"], {})
            deductions.append({"code": a["code"], "name": t.get("name", a["code"]), "amount": float(q2(a["amount"])),
                               "note": a.get("note") or "", "adjustment": True})

    flags = []
    room = gross - sum((D(str(x["amount"])) for x in deductions), ZERO)
    for adv in advances:                                   # recover advances / loans last, never into negative
        want = min(q2(adv["emi"]), q2(adv["balance"]))
        take = max(ZERO, min(want, room))
        if take < want:
            flags.append({"level": "warn", "text": f"Advance recovery cut to ₹{take} (net would go negative)"})
        if take > 0:
            deductions.append({"code": "ADVANCE", "name": "Advance / Loan Recovery", "amount": float(take),
                               "advance_id": adv["id"]})
            room -= take

    total_ded = q2(sum((D(str(x["amount"])) for x in deductions), ZERO))
    net = gross - total_ded
    net = rupee(net) if cfg.get("rounding", "rupee") == "rupee" else q2(net)
    return {"earnings": earnings, "deductions": deductions, "employer": employer,
            "gross": float(gross), "total_deductions": float(total_ded), "net": float(net),
            "paid_days": float(q2(paid)), "factor": float(factor), "flags": flags,
            "statutory_wages": {**att_pf, "esi_wage": float(esi_wage), "pt_wage": float(pt_base)}}


def words_inr(n) -> str:
    """₹ amount in Indian words: 132293 → 'One Lakh Thirty Two Thousand Two Hundred Ninety Three'."""
    ones = ("Zero One Two Three Four Five Six Seven Eight Nine Ten Eleven Twelve Thirteen Fourteen "
            "Fifteen Sixteen Seventeen Eighteen Nineteen").split()
    tens = "_ _ Twenty Thirty Forty Fifty Sixty Seventy Eighty Ninety".split()

    def two(x):
        return ones[x] if x < 20 else tens[x // 10] + ("" if x % 10 == 0 else " " + ones[x % 10])

    def three(x):
        h, r = divmod(x, 100)
        return ((ones[h] + " Hundred" + (" " if r else "")) if h else "") + (two(r) if r else "")
    amt = q2(n)
    rupees, paise = int(amt), int((amt - int(amt)) * 100)
    parts, x = [], rupees
    for div, lab in ((10000000, "Crore"), (100000, "Lakh"), (1000, "Thousand")):
        k, x = divmod(x, div)
        if k:
            parts.append(three(k) + " " + lab)
    if x:
        parts.append(three(x))
    s = "Rupees " + (" ".join(parts) or "Zero")
    if paise:
        s += " and " + two(paise) + " Paise"
    return s + " Only"
