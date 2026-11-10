"""Team-lead scoping rules in one place.

* A team lead OWNS a case when the case's team_lead column names them (name / emp code / TL code).
* A team lead may READ (never change) another lead's case when both of them work that portfolio
  (same bank + product, and the same branch when the case has one) — "peer, read-only".
* Every write path that a team lead can reach calls guard_write() so a peer case can't be changed even
  if someone calls the API directly.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func

from . import models

READ_ONLY_MSG = "Read-only — this case belongs to another team lead."


def _ids(lead) -> set:
    out = set()
    for v in (getattr(lead, "name", None), getattr(lead, "emp_code", None), getattr(lead, "tl_emp_code", None)):
        if v and str(v).strip():
            out.add(str(v).strip().lower())
    return out


def owns(lead, case) -> bool:
    return bool(case is not None and (case.team_lead or "").strip().lower() in _ids(lead))


def works_portfolio(db, lead, bank, product, branch=None) -> bool:
    from .routers.cases import teamlead_case_filter
    q = db.query(models.Case.id).filter(models.Case.removed.isnot(True), teamlead_case_filter(lead),
                                        models.Case.bank == bank, models.Case.product == product)
    if branch:
        q = q.filter(func.lower(func.trim(models.Case.branch)) == str(branch).strip().lower())
    return q.first() is not None


def is_lead(user) -> bool:
    return getattr(user, "role", None) == "teamlead"


def location_specific(db, case) -> bool:
    """True only when the portfolio was uploaded for an explicit location (branch chosen at upload).
    A branch filled in later (from pincode / the FOS) does NOT make the portfolio location-specific."""
    bid = getattr(case, "import_batch_id", None)
    if not bid:
        return False
    b = db.query(models.ImportBatch.branch).filter(models.ImportBatch.id == bid).first()
    return bool(b and b[0] and str(b[0]).strip())


def peer_can_read(db, user, case) -> bool:
    """A team lead reading ANOTHER lead's case inside a portfolio both of them work.
    Same bank + product is enough; the branch must also match only for a location-specific portfolio."""
    if not is_lead(user) or case is None or owns(user, case) or not (case.team_lead or "").strip():
        return False
    branch = case.branch if location_specific(db, case) else None
    return works_portfolio(db, user, case.bank, case.product, branch)


def guard_write(db, user, case):
    """Block any change by a team lead on a case that isn't theirs (peer cases are read-only)."""
    if is_lead(user) and case is not None and not owns(user, case) and getattr(case, "escalated_to", None) != user.id:
        raise HTTPException(status_code=403, detail=READ_ONLY_MSG)


def lead_of(db):
    """resolve(team_lead cell) → User (or None)."""
    from .routers.team import _tl_resolver
    return _tl_resolver(db)


def own_case_ids(db, lead) -> set:
    from .routers.cases import teamlead_case_filter
    return {i for (i,) in db.query(models.Case.id).filter(teamlead_case_filter(lead)).all()}
