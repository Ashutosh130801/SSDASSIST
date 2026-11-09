"""Indian salary income-tax (TDS) engine — new and old regime, configurable per financial year.

Slabs / rebate / standard deduction / limits live in the payroll config ("income_tax") so an
organisation updates them each Budget without a code change. Defaults = FY 2025-26 and FY 2026-27
(Budget 2026 left the slabs unchanged).

Monthly TDS = (projected annual tax − TDS already deducted this FY) ÷ months left including this one.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

D = Decimal
ZERO = D("0")

DEFAULT_TAX = {
    "mode": "auto",                         # auto = RecoverIQ computes TDS; manual = use the per-employee monthly TDS
    "default_regime": "new",
    "allow_self_declaration": True,         # employees enter their own investment declarations
    "new": {"std_deduction": 75000,
            "slabs": [{"upto": 400000, "rate": 0}, {"upto": 800000, "rate": 5}, {"upto": 1200000, "rate": 10},
                      {"upto": 1600000, "rate": 15}, {"upto": 2000000, "rate": 20}, {"upto": 2400000, "rate": 25},
                      {"upto": None, "rate": 30}],
            "rebate_limit": 1200000, "rebate_max": 60000, "marginal_relief": True, "surcharge_cap": 25},
    "old": {"std_deduction": 50000,
            "slabs": [{"upto": 250000, "rate": 0}, {"upto": 500000, "rate": 5}, {"upto": 1000000, "rate": 20},
                      {"upto": None, "rate": 30}],
            "rebate_limit": 500000, "rebate_max": 12500, "marginal_relief": False, "surcharge_cap": 37,
            "limits": {"sec80c": 150000, "sec80d": 100000, "sec24b": 200000, "sec80ccd1b": 50000}},
    "cess": 4,
    "surcharge": [{"above": 5000000, "rate": 10}, {"above": 10000000, "rate": 15},
                  {"above": 20000000, "rate": 25}, {"above": 50000000, "rate": 37}],
}

DECL_FIELDS = {
    "sec80c": "80C — PPF, ELSS, LIC, tuition fees, home-loan principal (your PF is added automatically)",
    "sec80d": "80D — medical insurance premium",
    "sec24b": "24(b) — home-loan interest",
    "sec80ccd1b": "80CCD(1B) — extra NPS",
    "other_deductions": "Other Chapter VI-A (80E, 80G, 80TTA…)",
    "rent_paid_annual": "Rent paid for the year (for HRA exemption)",
    "prev_employer_income": "Salary from previous employer this year",
    "prev_employer_tds": "TDS deducted by previous employer",
    "tds_outside": "TDS already deducted this year outside RecoverIQ (by this employer)",
    "other_income": "Other income you want TDS on (interest etc.)",
}


def r(x) -> Decimal:
    return D(str(x or 0)).quantize(D("1"), rounding=ROUND_HALF_UP)


def fy_of(period: str) -> str:
    y, m = int(period[:4]), int(period[5:7])
    a = y if m >= 4 else y - 1
    return f"{a}-{str(a + 1)[2:]}"


def fy_periods(fy: str) -> list[str]:
    a = int(fy[:4])
    return [f"{a}-{m:02d}" for m in range(4, 13)] + [f"{a + 1}-{m:02d}" for m in range(1, 4)]


def slab_tax(income: Decimal, slabs) -> Decimal:
    tax, lower = ZERO, ZERO
    for s in slabs:
        upto = None if s.get("upto") in (None, "") else D(str(s["upto"]))
        rate = D(str(s.get("rate") or 0))
        if income <= lower:
            break
        top = income if upto is None else min(income, upto)
        tax += (top - lower) * rate / 100
        if upto is None:
            break
        lower = upto
    return tax


def tax_on(taxable, regime: str, cfg: dict) -> dict:
    """Annual tax on taxable income, with rebate 87A, marginal relief, surcharge and cess."""
    rc = cfg[regime]
    taxable = max(ZERO, r(taxable))
    base = slab_tax(taxable, rc["slabs"])
    rebate = ZERO
    if taxable <= D(str(rc["rebate_limit"])):
        rebate = min(base, D(str(rc["rebate_max"])))
    elif rc.get("marginal_relief"):
        excess = taxable - D(str(rc["rebate_limit"]))
        if base > excess:                                  # tax can't exceed income above the rebate limit
            rebate = base - excess
    after = base - rebate
    sur = ZERO
    cap = D(str(rc.get("surcharge_cap", 37)))
    for s in sorted(cfg.get("surcharge") or [], key=lambda x: x["above"]):
        if taxable > D(str(s["above"])):
            sur = after * min(D(str(s["rate"])), cap) / 100
    cess = (after + sur) * D(str(cfg.get("cess", 4))) / 100
    total = after + sur + cess
    total = (total / 10).quantize(D("1"), rounding=ROUND_HALF_UP) * 10     # sec 288B: round to ₹10
    return {"taxable": float(taxable), "slab_tax": float(r(base)), "rebate": float(r(rebate)),
            "surcharge": float(r(sur)), "cess": float(r(cess)), "total": float(total)}


def compute_annual(*, regime: str, cfg: dict, gross, basic, hra, pf, pt, decl: dict, metro: bool = False) -> dict:
    """Annual figures → taxable income + tax for one regime. Amounts are for the whole FY."""
    gross, basic, hra, pf, pt = (D(str(x or 0)) for x in (gross, basic, hra, pf, pt))
    dd = {k: D(str((decl or {}).get(k) or 0)) for k in DECL_FIELDS}
    rc = cfg[regime]
    income = gross + dd["prev_employer_income"]
    std = min(D(str(rc["std_deduction"])), income)
    lines = [("Gross salary", gross), ("Salary from previous employer", dd["prev_employer_income"])]
    exempt = ZERO
    ded = ZERO
    via = []
    if regime == "old":
        rent = dd["rent_paid_annual"]
        if rent > 0 and hra > 0:
            exempt = max(ZERO, min(hra, rent - basic * D("0.10"), basic * (D("0.5") if metro else D("0.4"))))
        lim = rc.get("limits") or {}
        c80 = min(dd["sec80c"] + pf, D(str(lim.get("sec80c", 150000))))
        d80 = min(dd["sec80d"], D(str(lim.get("sec80d", 100000))))
        i24 = min(dd["sec24b"], D(str(lim.get("sec24b", 200000))))
        n1b = min(dd["sec80ccd1b"], D(str(lim.get("sec80ccd1b", 50000))))
        oth = dd["other_deductions"]
        via = [("80C (incl. your PF)", c80), ("80D", d80), ("80CCD(1B)", n1b), ("Other VI-A", oth)]
        ded = c80 + d80 + n1b + oth
        house = i24
    else:
        house = ZERO
        pt = ZERO                                          # PT deduction not allowed in the new regime
    taxable = max(ZERO, income - exempt - std - pt - house + dd["other_income"] - ded)
    t = tax_on(taxable, regime, cfg)
    return {"regime": regime, "gross": float(r(income)), "hra_exempt": float(r(exempt)), "std_deduction": float(r(std)),
            "professional_tax": float(r(pt)), "house_loss": float(r(house)), "other_income": float(r(dd["other_income"])),
            "chapter_via": [{"name": n, "amount": float(r(v))} for n, v in via], "deductions": float(r(ded)),
            **t, "prev_employer_tds": float(r(dd["prev_employer_tds"]))}


def monthly_tds(annual_tax: float, tds_so_far: float, months_left_incl: int) -> float:
    left = max(0.0, annual_tax - tds_so_far)
    return float(r(left / max(1, months_left_incl)))
