"""Single source of truth for a case's money maths — settlement (NORM/STAB) vs plain
outstanding, PAID / PARTIAL / UNPAID, what counts as cash collection, partial-only payments,
and any excess over settlement. EVERY payment path and every metric must use these helpers so
nothing can drift out of sync.

Rules (agreed):
- A "settlement" case carries a NORM and/or STAB amount (the minimum the customer may pay to
  close, e.g. credit-card / PL-BL). The settle target honours the payment's NORM/STAB tag:
  tagged STAB -> stab_amount, tagged NORM -> norm_amount, untagged -> the cheaper of the two.
    * received >= target            -> PAID   (full received counts as cash; excess tracked)
    * 0 < received < target         -> PARTIAL (does NOT count as cash; shown as a partial)
    * received == 0                 -> UNPAID
- A "plain" case has no NORM/STAB (e.g. 180+ write-off). It is PAID when the outstanding is
  fully paid, else PARTIAL. All of its received counts as cash collection.
"""
from decimal import Decimal

from sqlalchemy import case as sa_case, func

from . import models

Z = Decimal(0)


def _d(v) -> Decimal:
    try:
        return Decimal(str(v or 0))
    except Exception:
        return Z


def base_total(case) -> Decimal:
    """Full worth of the case = base for plain 'pending' (funding -> TOS -> ENR -> POS)."""
    for v in (getattr(case, "funding_amount", 0), getattr(case, "total_outstanding", 0),
              getattr(case, "enr", 0), getattr(case, "principal_outstanding", 0)):
        d = _d(v)
        if d > 0:
            return d
    return Z


def norm_amt(case) -> Decimal:
    return _d(getattr(case, "norm_amount", 0))


def stab_amt(case) -> Decimal:
    return _d(getattr(case, "stab_amount", 0))


def is_settlement(case) -> bool:
    return norm_amt(case) > 0 or stab_amt(case) > 0


def settle_target(case) -> Decimal:
    """Minimum needed to mark this case PAID, honouring the NORM/STAB tag on the payment."""
    n, s = norm_amt(case), stab_amt(case)
    tag = (getattr(case, "norm_stab", None) or "").upper()
    if "STAB" in tag and s > 0:
        return s
    if "NORM" in tag and n > 0:
        return n
    opts = [x for x in (n, s) if x > 0]
    return min(opts) if opts else Z


def compute_status(case) -> str:
    """PAID / PARTIAL / UNPAID from received + settlement/base — pure, no side effects."""
    # Auto-debit / e-NACH settlement resolves the case as PAID even at ₹0 collected.
    if getattr(case, "auto_debit", False):
        return "PAID"
    recv = _d(getattr(case, "received_amount", 0))
    if is_settlement(case):
        tgt = settle_target(case)
        if recv <= 0:
            return "UNPAID"
        if tgt > 0 and recv >= tgt:
            return "PAID"
        return "PARTIAL"
    base = base_total(case)
    if recv <= 0:
        return "UNPAID"
    if recv >= base:               # base 0 with a payment also settles a plain case
        return "PAID"
    return "PARTIAL"


def autotag(case) -> None:
    """For a settlement (NORM/STAB) case, derive the NORM/STAB tag from the CUMULATIVE received —
    the amount decides, never a manual pick: received >= norm -> NORM, else >= stab -> STAB, else
    below the lower threshold -> no tag (PARTIAL). Plain (no norm/stab) cases are left untouched so
    a user's free NORM/STAB/PAID choice on them is preserved. Skipped when auto_debit settles at ₹0."""
    if getattr(case, "auto_debit", False) or not is_settlement(case):
        return
    n, s, recv = norm_amt(case), stab_amt(case), _d(getattr(case, "received_amount", 0))
    if n > 0 and recv >= n:
        case.norm_stab = "NORM"
    elif s > 0 and recv >= s:
        case.norm_stab = "STAB"
    else:
        case.norm_stab = None            # below the lower of the two -> partial, no tag


def recompute(case) -> str:
    """Apply the money maths to a case in place: set paid_status, pending_amount, and (only when
    it flips into/out of PAID) the working status / follow-up. Returns the new paid_status."""
    autotag(case)                         # amount-derived NORM/STAB before status is computed
    st = compute_status(case)
    recv = _d(getattr(case, "received_amount", 0))
    pend = base_total(case) - recv
    case.pending_amount = pend if pend > 0 else Z
    case.paid_status = st
    if st == "PAID":
        case.status = "paid"
        case.follow_up_date = None
    elif (getattr(case, "status", None) or "") == "paid":
        # was paid, now isn't (e.g. reversal / recompute) -> return to the working pool
        case.status = "allocated"
    return st


def cash_qualified(case) -> Decimal:
    """Amount that counts toward CASH COLLECTION for this case."""
    recv = _d(getattr(case, "received_amount", 0))
    if not is_settlement(case):
        return recv                                    # plain case -> all received counts
    return recv if (getattr(case, "paid_status", "") or "").upper() == "PAID" else Z


def partial_amount(case) -> Decimal:
    """Below-settlement money on a NORM/STAB case — tracked separately, NOT cash collection."""
    if is_settlement(case) and (getattr(case, "paid_status", "") or "").upper() == "PARTIAL":
        return _d(getattr(case, "received_amount", 0))
    return Z


def excess_over(case) -> Decimal:
    """How much more than the settlement target was paid (settled NORM/STAB cases only)."""
    if is_settlement(case) and (getattr(case, "paid_status", "") or "").upper() == "PAID":
        e = _d(getattr(case, "received_amount", 0)) - settle_target(case)
        return e if e > 0 else Z
    return Z


def remaining_to_norm(case):
    n = norm_amt(case)
    if n <= 0:
        return None
    r = n - _d(getattr(case, "received_amount", 0))
    return r if r > 0 else Z


def remaining_to_stab(case):
    s = stab_amt(case)
    if s <= 0:
        return None
    r = s - _d(getattr(case, "received_amount", 0))
    return r if r > 0 else Z


# --- SQL aggregation expressions (must mirror the Python logic above) ------------------------
def _norm_col():
    return func.coalesce(models.Case.norm_amount, 0)


def _stab_col():
    return func.coalesce(models.Case.stab_amount, 0)


def cash_expr():
    """Per-row cash-collection contribution: plain case -> received; settlement case -> received
    only when PAID; else 0. Use inside func.sum(...)."""
    recv = func.coalesce(models.Case.received_amount, 0)
    is_plain = (_norm_col() <= 0) & (_stab_col() <= 0)
    return sa_case(
        (is_plain, recv),
        (models.Case.paid_status == "PAID", recv),
        else_=0,
    )


def partial_expr():
    """Per-row partial-payment contribution: settlement case that is PARTIAL -> received; else 0."""
    recv = func.coalesce(models.Case.received_amount, 0)
    is_settle = (_norm_col() > 0) | (_stab_col() > 0)
    return sa_case(
        (is_settle & (models.Case.paid_status == "PARTIAL"), recv),
        else_=0,
    )
