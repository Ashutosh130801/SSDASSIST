"""Keep a case's close date in step with its CYCLE (and bank/product/period).

The close date is first computed at upload. Later the cycle can change — a DPR upload, the
"Correct columns" upload, a Live-Sheet / case edit — and before this module the close date stayed
on the OLD cycle (e.g. uploaded as CYC 15, corrected to CYC 18, but still closing on the 15th).

A flush hook recomputes close_date / closing_type whenever cycle, bank, product or period
changes on an existing case, from ANY code path. Due-date cases (BRBL) keep their sheet due date.
"""
from sqlalchemy import event, inspect as sa_inspect
from sqlalchemy.orm import Session

from . import models

_WATCH = ("cycle", "bank", "product", "period")


def recompute(db, case) -> bool:
    """Recompute one case's close date from its current fields. Returns True if it changed."""
    from . import closing
    from .products import custom_closing_type
    if not case.period:
        return False
    if (case.closing_type or "") == "due_date" and case.close_date:
        return False                                    # sheet due date — not cycle-driven
    with db.no_autoflush:
        force = custom_closing_type(db, case.bank, case.product)
    cd, ctype = closing.compute_close(case.bank, case.product, case.period, cyc=case.cycle, force_type=force)
    if cd != case.close_date or ctype != case.closing_type:
        case.close_date, case.closing_type = cd, ctype
        return True
    return False


@event.listens_for(Session, "before_flush")
def _sync_close_dates(session, flush_context, instances):
    for obj in list(session.dirty):
        if not isinstance(obj, models.Case):
            continue
        st = sa_inspect(obj)
        if any(st.attrs[a].history.has_changes() for a in _WATCH):
            try:
                recompute(session, obj)
            except Exception:
                pass                                    # never block a save over this
