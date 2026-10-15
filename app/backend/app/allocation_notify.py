"""Tell FOS / callers when cases are allocated to them — from ANY path (portfolio upload, TL upload,
bulk reassign, transfer/swap, joint allocation, auto-allocate, relink).

How: SQLAlchemy "set" listeners record every change to assigned_fos_id / assigned_caller_id /
joint_fos_id during a transaction (remembering the value it had at the START, so A→None→A within one
upload is not "new"). Just before commit we send ONE summary notification per person:
    "12 new cases allocated to you" — ICICI · 2 BKT: 8 · RBL · CC: 4 — by <who>
The notification goes to the bell (web) and pops as a phone alert in the app (live push).
"""
from collections import defaultdict

from sqlalchemy import event
from sqlalchemy.orm import Session

from . import models

_FIELDS = {"assigned_fos_id": "fos", "assigned_caller_id": "caller", "joint_fos_id": "joint"}
_KEY = "_alloc_changes"


def _on_set(field):
    def handler(target, value, oldvalue, initiator):
        from sqlalchemy.orm import object_session
        from sqlalchemy.orm.base import NO_VALUE, NEVER_SET
        sess = object_session(target)
        store = (sess.info if sess is not None else target.__dict__).setdefault(_KEY, {})
        k = (id(target), field)
        if k not in store:
            orig = None if oldvalue in (NO_VALUE, NEVER_SET) else oldvalue
            store[k] = [target, orig]
        return value
    return handler


for _f in _FIELDS:
    event.listen(getattr(models.Case, _f), "set", _on_set(_f), retval=True, active_history=True)


@event.listens_for(Session, "before_attach")
def _carry_pending(session, instance):
    # Case() built before db.add(): its changes were parked on the object — move them to the session.
    parked = instance.__dict__.pop(_KEY, None) if isinstance(instance, models.Case) else None
    if parked:
        session.info.setdefault(_KEY, {}).update(parked)


@event.listens_for(Session, "before_commit")
def _send(session):
    changes = session.info.pop(_KEY, None)
    if not changes:
        return
    try:
        session.flush()                                 # new cases get their ids
    except Exception:
        return
    actor_id = session.info.get("actor_id")
    actor_name = session.info.get("actor_name") or "Admin"
    per_user = defaultdict(lambda: {"cases": [], "joint": 0})
    for (_, field), (case, orig) in changes.items():
        new = getattr(case, field, None)
        if not new or new == orig or getattr(case, "removed", False):
            continue
        if field == "joint_fos_id" and new == getattr(case, "assigned_fos_id", None):
            continue
        u = per_user[new]
        if case not in u["cases"]:
            u["cases"].append(case)
        if field == "joint_fos_id":
            u["joint"] += 1
    per_user.pop(actor_id, None)                       # don't notify yourself
    if not per_user:
        return
    active = {uid for (uid,) in session.query(models.User.id).filter(
        models.User.id.in_(list(per_user)), models.User.is_active.is_(True)).all()}
    from .routers.notifications import push
    for uid, info in per_user.items():
        if uid not in active:
            continue
        cases = info["cases"]
        n = len(cases)
        groups = defaultdict(int)
        for c in cases:
            groups[" · ".join(x for x in (c.bank, c.product) if x) or "Other"] += 1
        parts = [f"{g}: {k}" for g, k in sorted(groups.items(), key=lambda x: -x[1])]
        if len(parts) > 6:
            parts = parts[:6] + [f"+{len(parts) - 6} more"]
        if n == 1:
            c = cases[0]
            who = c.customer_name or c.account_no or f"Case #{c.id}"
            title = ("Joint case sent to you: " if info["joint"] else "New case allocated: ") + who
        else:
            title = f"{n} new cases allocated to you" + (f" ({info['joint']} joint)" if info["joint"] else "")
        body = " · ".join(parts) + f"\n— by {actor_name}"
        try:
            push(session, uid, title[:160], body, case_id=cases[0].id if n == 1 else None,
                 ntype="allocation", by_name=actor_name)
        except Exception:
            pass                                        # a failed alert must never block the save


@event.listens_for(Session, "after_rollback")
def _clear(session):
    session.info.pop(_KEY, None)
