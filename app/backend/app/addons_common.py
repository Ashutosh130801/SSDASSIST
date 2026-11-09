"""Shared helpers for the 🧩 Add-on modules."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException

from . import models
from . import services as svc

IST = timezone(timedelta(hours=5, minutes=30))
LEADS = ("admin", "headoffice", "manager", "teamlead")
OFFICE = ("admin", "headoffice", "manager")
CASE_WORKERS = ("admin", "headoffice", "manager", "teamlead", "fos", "telecaller", "backend")


def now_ist() -> datetime:
    return datetime.now(IST)


def conf(db, key: str) -> dict:
    return svc.settings_of(db, key)


def need(user: models.User, roles: tuple, what: str = "this add-on"):
    if user.role in ("techsupport",):
        return
    if user.role not in roles:
        raise HTTPException(403, f"Your role can't use {what}.")


def scoped_cases(db, user, all_periods: bool = False):
    """Cases this user may see — the exact same scope as the Accounts screen."""
    if user.role not in CASE_WORKERS + ("techsupport", "it_support_view"):
        raise HTTPException(403, "Your role has no access to case data.")
    from .routers.cases import _scope
    return _scope(db.query(models.Case), user, all_periods=all_periods)


def case_or_404(db, user, case_id: int, all_periods: bool = False) -> models.Case:
    c = scoped_cases(db, user, all_periods).filter(models.Case.id == case_id).first()
    if not c:
        raise HTTPException(404, "Case not found")
    return c


def D(v) -> Decimal:
    try:
        return Decimal(str(v if v not in (None, "") else 0))
    except Exception:
        return Decimal(0)


def money(v) -> str:
    return f"₹{D(v):,.2f}"


def outstanding(case) -> Decimal:
    from . import paymath
    p = D(case.pending_amount)
    return p if p > 0 else max(paymath.base_total(case) - D(case.received_amount), Decimal(0))


def mask_phone(p) -> str:
    d = "".join(ch for ch in str(p or "") if ch.isdigit())
    return ("XXXXXX" + d[-4:]) if len(d) >= 4 else ""


def post_payment(db, case, amount: Decimal, mode: str, note: str, actor=None, actor_id: int | None = None):
    """Book a collection on a case exactly like the manual payment flow (paymath + history + audit)."""
    from . import audit, paymath
    case.received_amount = D(case.received_amount) + amount
    paymath.recompute(case)
    uid = getattr(actor, "id", None) or actor_id or case.assigned_caller_id or case.assigned_fos_id
    if uid:
        db.add(models.CallLog(case_id=case.id, caller_id=uid, disposition="PAYMENT", ptp_amount=amount,
                              note=f"₹{amount} via {mode}" + (f" — {note}" if note else "")))
    audit.record(db, actor, "payment", case, new=str(amount), detail=f"Collected ₹{amount} via {mode}" + (f" ({note})" if note else ""))
    try:
        from . import webhooks_out
        webhooks_out.emit(db, "payment.received", {"case_id": case.id, "account_no": case.account_no, "bank": case.bank,
                                                   "amount": float(amount), "mode": mode, "paid_status": case.paid_status})
    except Exception:
        pass


def company_cfg(db) -> dict:
    """Company name / logo / address from the payroll settings (used on letters, notices, invoices)."""
    from .payroll_engine import merged_config
    row = db.get(models.PayrollConfig, 1)
    try:
        return merged_config(row.data if row else {})
    except Exception:
        return {}
