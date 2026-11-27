"""Team Follow-up.

HR / admin / head office create a *team follower* (primary role ``teamfollower`` in Manpower, or
the extra "Team follower" hat on a team lead / FOS / caller, which issues a FTL id) and add the FOS
and callers they should track. The follower then sees each member's COMPLETE performance —
collections, cases, visits, calls, PTPs, attendance and field tracking — irrespective of case or
portfolio. Read-only: nothing here lets a follower change a case.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import models, audit, presence
from ..database import get_db
from ..deps import get_current_user, require_roles
from ..follow_scope import member_ids

router = APIRouter(prefix="/api/team-follow", tags=["team-follow"])

MANAGE_ROLES = ("admin", "headoffice", "hr")
IST = timezone(timedelta(hours=5, minutes=30))
_ROLE_LABEL = {"fos": "Field Agent", "telecaller": "Tele-calling Agent", "teamlead": "Team Lead",
               "teamfollower": "Field TL"}


def _is_follower_account(u: models.User) -> bool:
    return u.role == "teamfollower" or bool(getattr(u, "also_team_follower", False))


def _can_be_member(u: models.User) -> bool:
    """FOS and callers (including dual-role staff who hold a FOS or caller id)."""
    return (u.role in ("fos", "telecaller") or bool(getattr(u, "also_field_agent", False))
            or bool(getattr(u, "also_caller", False)))


def _brief(u: models.User) -> dict:
    ids = [u.emp_code] if u.emp_code else []
    for flag, col in (("also_field_agent", "fos_emp_code"), ("also_caller", "tc_emp_code"),
                      ("also_team_lead", "tl_emp_code"), ("also_team_follower", "tf_emp_code")):
        if getattr(u, flag, False) and getattr(u, col, None):
            ids.append(getattr(u, col))
    return {"id": u.id, "name": u.name, "role": u.role, "role_label": _ROLE_LABEL.get(u.role, (u.role or "").title()),
            "emp_code": u.emp_code, "all_ids": " / ".join(ids), "branch": u.branch, "location": u.location,
            "phone": u.phone, "email": u.email, "is_active": bool(u.is_active),
            "also_field_agent": bool(getattr(u, "also_field_agent", False)),
            "also_caller": bool(getattr(u, "also_caller", False)),
            "also_team_lead": bool(getattr(u, "also_team_lead", False)),
            "photo_url": getattr(u, "photo_url", None)}


def _follower_out(db: Session, f: models.User) -> dict:
    mids = member_ids(db, f.id)
    members = db.query(models.User).filter(models.User.id.in_(mids or {-1})).order_by(models.User.name).all()
    return {**_brief(f),
            "tf_emp_code": f.tf_emp_code if f.role != "teamfollower" else f.emp_code,
            "primary_follower": f.role == "teamfollower",
            "members": [_brief(m) for m in members], "member_count": len(members)}


def _get_follower(db: Session, fid: int) -> models.User:
    f = db.query(models.User).filter(models.User.id == fid).first()
    if not f or not _is_follower_account(f):
        raise HTTPException(status_code=404, detail="Field TL not found")
    return f


# ------------------------------------------------------------------ management (HR / admin / HO)

@router.get("/followers")
def list_followers(db: Session = Depends(get_db), user: models.User = Depends(require_roles(*MANAGE_ROLES))):
    """Every team follower (primary role or extra hat) with the people they follow."""
    rows = (db.query(models.User)
            .filter(or_(models.User.role == "teamfollower", models.User.also_team_follower.is_(True)))
            .order_by(models.User.name).all())
    return [_follower_out(db, f) for f in rows]


@router.get("/candidates")
def candidates(q: str | None = None, db: Session = Depends(get_db),
               user: models.User = Depends(require_roles(*MANAGE_ROLES))):
    """Active FOS / callers that can be added under a follower (search by name / id / branch)."""
    rows = (db.query(models.User).filter(models.User.is_active.is_(True))
            .filter(or_(models.User.role.in_(("fos", "telecaller")), models.User.also_field_agent.is_(True),
                        models.User.also_caller.is_(True)))
            .order_by(models.User.name).all())
    out = [_brief(u) for u in rows]
    if q:
        s = q.strip().lower()
        out = [e for e in out if any(s in str(e.get(k) or "").lower()
                                     for k in ("name", "all_ids", "branch", "location", "phone", "email"))]
    return out


@router.get("/{fid}")
def get_follower(fid: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    if user.role not in MANAGE_ROLES + ("techsupport", "it_support_view") and user.id != fid:
        raise HTTPException(status_code=403, detail="Not allowed")
    return _follower_out(db, _get_follower(db, fid))


@router.post("/{fid}/members")
def add_members(fid: int, body: dict = Body(...), db: Session = Depends(get_db),
                user: models.User = Depends(require_roles(*MANAGE_ROLES))):
    """Add FOS / callers under a follower. body = {member_ids: [..]}. Already-added ones are skipped."""
    f = _get_follower(db, fid)
    want = {int(x) for x in (body.get("member_ids") or []) if str(x).strip().lstrip("-").isdigit()}
    want.discard(f.id)
    if not want:
        raise HTTPException(status_code=400, detail="Pick at least one FOS or caller to add")
    have = member_ids(db, f.id)
    users = db.query(models.User).filter(models.User.id.in_(want)).all()
    bad = [u.name for u in users if not _can_be_member(u)]
    if bad:
        raise HTTPException(status_code=400, detail="Only FOS / callers can be added: " + ", ".join(bad[:5]))
    added = []
    for u in users:
        if u.id in have:
            continue
        db.add(models.TeamFollow(follower_id=f.id, member_id=u.id, added_by=user.id))
        added.append(u.name)
    if added:
        audit.record(db, user, "staff_update", None, entity_type="staff", target_user_id=f.id,
                     detail=f"Field TL: added {', '.join(added)} under {f.name}")
    db.commit()
    return _follower_out(db, f)


@router.delete("/{fid}/members/{mid}")
def remove_member(fid: int, mid: int, db: Session = Depends(get_db),
                  user: models.User = Depends(require_roles(*MANAGE_ROLES))):
    f = _get_follower(db, fid)
    row = db.query(models.TeamFollow).filter(models.TeamFollow.follower_id == f.id,
                                            models.TeamFollow.member_id == mid).first()
    if row:
        m = db.query(models.User).filter(models.User.id == mid).first()
        db.delete(row)
        audit.record(db, user, "staff_update", None, entity_type="staff", target_user_id=f.id,
                     detail=f"Field TL: removed {m.name if m else mid} from {f.name}")
        db.commit()
    return _follower_out(db, f)


# ------------------------------------------------------------------ follower's own dashboard

def _d(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _ist_day_bounds(day):
    start = datetime(day.year, day.month, day.day, tzinfo=IST).astimezone(timezone.utc)
    return start, start + timedelta(days=1)


def _member_summary(db: Session, u: models.User, period: str | None, mstart, mend, today) -> dict:
    """One member's complete performance snapshot (the selected month's cases + today's activity)."""
    t0, t1 = _ist_day_bounds(today)
    fos_hat = u.role == "fos" or bool(getattr(u, "also_field_agent", False))
    caller_hat = u.role == "telecaller" or bool(getattr(u, "also_caller", False))
    own = or_(models.Case.assigned_fos_id == u.id, models.Case.assigned_caller_id == u.id,
              models.Case.joint_fos_id == u.id)
    cq = db.query(models.Case).filter(models.Case.removed.isnot(True), own)
    if period:
        cq = cq.filter(models.Case.period == period)
    cases = cq.all()
    paid = sum(1 for c in cases if (c.paid_status or "").upper() == "PAID")
    partial = sum(1 for c in cases if (c.paid_status or "").upper() == "PARTIAL")
    ptp_open = sum(1 for c in cases if (c.disposition or "").upper() == "PTP" and (c.paid_status or "").upper() != "PAID")
    enr = sum(_d(c.enr) for c in cases)
    recovered = sum(_d(c.received_amount) for c in cases)
    pending = sum(_d(c.pending_amount) for c in cases)
    banks = sorted({c.bank for c in cases if c.bank})

    def _in_month(col):
        conds = []
        if mstart is not None:
            conds.append(col >= mstart)
        if mend is not None:
            conds.append(col < mend)
        return conds

    vq = db.query(models.Visit).filter(models.Visit.officer_id == u.id)
    visits_m = vq.filter(*_in_month(models.Visit.created_at)).all()
    visits_t = vq.filter(models.Visit.created_at >= t0, models.Visit.created_at < t1).all()
    cl = db.query(models.CallLog).filter(models.CallLog.caller_id == u.id)
    calls_m = cl.filter(*_in_month(models.CallLog.created_at)).all()
    calls_t = cl.filter(models.CallLog.created_at >= t0, models.CallLog.created_at < t1).all()
    is_pay = lambda x: (x.disposition or "") in ("PAYMENT", "PAID")  # noqa: E731
    dials_m = [x for x in calls_m if not is_pay(x)]
    dials_t = [x for x in calls_t if not is_pay(x)]
    coll_calls_m = sum(_d(x.ptp_amount) for x in calls_m if is_pay(x))
    coll_visits_m = sum(_d(v.amount_collected) for v in visits_m if _d(v.amount_collected) > 0)
    coll_t = sum(_d(x.ptp_amount) for x in calls_t if is_pay(x)) + \
        sum(_d(v.amount_collected) for v in visits_t if _d(v.amount_collected) > 0)

    att = db.query(models.Attendance).filter(models.Attendance.user_id == u.id,
                                             models.Attendance.date == today).first()
    last_ping = None
    if fos_hat:
        lp = db.query(func.max(models.LocationPing.created_at)).filter(models.LocationPing.officer_id == u.id).scalar()
        last_ping = _aware(lp).isoformat() if lp else None
    return {
        **_brief(u),
        "fos_hat": fos_hat, "caller_hat": caller_hat,
        "presence": presence.presence_dict(u),
        "attendance": {"status": att.status if att else None,
                       "check_in_at": _aware(att.check_in_at).isoformat() if att and att.check_in_at else None,
                       "check_out_at": _aware(att.check_out_at).isoformat() if att and att.check_out_at else None,
                       "late": bool(att.late) if att else False},
        "cases": {"assigned": len(cases), "paid": paid, "partial": partial, "unpaid": len(cases) - paid - partial,
                  "ptp_open": ptp_open, "banks": banks},
        "money": {"enr": round(enr, 2), "recovered": round(recovered, 2), "pending": round(pending, 2),
                  "recovery_pct": round(recovered / enr * 100, 2) if enr else 0.0,
                  "collected_calls": round(coll_calls_m, 2), "collected_visits": round(coll_visits_m, 2),
                  "collected_logs": round(coll_calls_m + coll_visits_m, 2), "collected_today": round(coll_t, 2)},
        "activity": {"visits_month": len(visits_m), "visits_today": len(visits_t),
                     "calls_month": len(dials_m), "calls_today": len(dials_t),
                     "last_ping": last_ping},
    }


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@router.get("/me/members")
def my_members(month_bucket: str | None = "current", follower_id: int | None = None,
               db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """The follower's members, each with a complete performance snapshot + team totals.
    HR / admin / HO may preview any follower's board with follower_id=."""
    fid = user.id
    if follower_id and follower_id != user.id:
        if user.role not in MANAGE_ROLES + ("techsupport", "it_support_view"):
            raise HTTPException(status_code=403, detail="Not allowed")
        fid = _get_follower(db, follower_id).id
    elif user.role != "teamfollower" and user.role not in MANAGE_ROLES:
        raise HTTPException(status_code=403, detail="Switch to the Field TL view to see the people under you")
    from .mis import _period_for
    from .team import _month_bounds_utc
    period = _period_for(month_bucket)
    mstart, mend = _month_bounds_utc(month_bucket)
    today = datetime.now(IST).date()
    mids = member_ids(db, fid)
    users = db.query(models.User).filter(models.User.id.in_(mids or {-1})).order_by(models.User.name).all()
    rows = [_member_summary(db, u, period, mstart, mend, today) for u in users]
    tot = {"members": len(rows),
           "present": sum(1 for r in rows if r["attendance"]["check_in_at"]),
           "online": sum(1 for r in rows if (r["presence"] or {}).get("state") in ("active", "online", "idle")),
           "assigned": sum(r["cases"]["assigned"] for r in rows),
           "paid": sum(r["cases"]["paid"] for r in rows),
           "ptp_open": sum(r["cases"]["ptp_open"] for r in rows),
           "enr": round(sum(r["money"]["enr"] for r in rows), 2),
           "recovered": round(sum(r["money"]["recovered"] for r in rows), 2),
           "pending": round(sum(r["money"]["pending"] for r in rows), 2),
           "collected_logs": round(sum(r["money"]["collected_logs"] for r in rows), 2),
           "collected_today": round(sum(r["money"]["collected_today"] for r in rows), 2),
           "visits_today": sum(r["activity"]["visits_today"] for r in rows),
           "calls_today": sum(r["activity"]["calls_today"] for r in rows),
           "visits_month": sum(r["activity"]["visits_month"] for r in rows),
           "calls_month": sum(r["activity"]["calls_month"] for r in rows)}
    tot["recovery_pct"] = round(tot["recovered"] / tot["enr"] * 100, 2) if tot["enr"] else 0.0
    f = db.query(models.User).filter(models.User.id == fid).first()
    return {"follower": {"id": f.id, "name": f.name,
                         "tf_emp_code": f.emp_code if f.role == "teamfollower" else f.tf_emp_code},
            "month_bucket": month_bucket, "period": period, "totals": tot, "members": rows}
