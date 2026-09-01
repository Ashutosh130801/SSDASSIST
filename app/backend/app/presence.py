"""Live presence for every user (callers, managers, HR, FOS...), the way chat apps do it:
a heartbeat keeps a `last_seen`, real activity keeps a `last_active_at`, and the state is
derived from how fresh those are. FOS also have GPS pings, but presence here is signal-agnostic.

States:
  active  — seen recently AND did something recently (input, or a logged call/visit/payment)
  idle    — seen recently but no activity for a while (logged in, but away / on another tab)
  offline — no heartbeat within the timeout (tab closed, app killed, network gone)
"""
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from . import models

IST = timezone(timedelta(hours=5, minutes=30))

ONLINE_TIMEOUT = 75      # seconds since last heartbeat to still count as online
IDLE_AFTER = 180         # seconds since last real activity before "online" becomes "idle"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def touch(db: Session, user_id: int, platform: str | None = None, active: bool = True) -> None:
    """Mark a heartbeat (and, when active, real activity) for a user. Called by the heartbeat
    endpoint and by work actions (call/visit/payment) so a caller on a call isn't seen as idle.
    Does NOT commit — the caller's own commit flushes it."""
    if not user_id:
        return
    now = now_utc()
    vals = {"last_seen": now}
    if platform:
        vals["last_platform"] = platform
    if active:
        vals["last_active_at"] = now
    db.query(models.User).filter(models.User.id == user_id).update(vals)


def state_for(u: models.User, now: datetime | None = None) -> str:
    now = now or now_utc()
    seen = _aware(getattr(u, "last_seen", None))
    if not seen or (now - seen).total_seconds() > ONLINE_TIMEOUT:
        return "offline"
    act = _aware(getattr(u, "last_active_at", None))
    if not act or (now - act).total_seconds() > IDLE_AFTER:
        return "idle"
    return "active"


def presence_dict(u: models.User, now: datetime | None = None) -> dict:
    """Compact presence payload for a user, for profile cards / team lists / attendance rows."""
    now = now or now_utc()
    seen = _aware(getattr(u, "last_seen", None))
    act = _aware(getattr(u, "last_active_at", None))
    st = state_for(u, now)
    idle_sec = int((now - act).total_seconds()) if (st == "idle" and act) else 0
    return {
        "state": st,                                   # active / idle / offline
        "platform": getattr(u, "last_platform", None) or None,
        "last_seen": seen.isoformat() if seen else None,
        "idle_seconds": idle_sec,                      # how long idle (for "idle 12m")
    }
