"""Branch-oriented team management (web admin/manager).

No Branch table: a "branch" is the set of users/cases sharing a branch name, and its
manager is the manager-role user on that branch. Admin creating a branch = creating its
manager. Also serves per-staff performance windows (daily / weekly / monthly / overall).
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import func, case, or_, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user, require_roles
from ..security import hash_password
from .. import audit

router = APIRouter(prefix="/api/team", tags=["team"])

IST = timezone(timedelta(hours=5, minutes=30))


def _d(x) -> float:
    return float(x or 0)


def _teamlead_member_ids(db: Session, lead: models.User, period: str | None = None) -> list[int]:
    """FOS/caller ids a team lead oversees — derived per-case from the upload sheet:
    the distinct staff assigned to cases whose team_lead field names this lead. A FOS
    or caller only counts here for the cases that carry the lead's name, so the same
    person can report to different leads on different cases. Pass period='YYYY-MM' to count
    only the team working that month (so a past-month-only member doesn't linger)."""
    from .cases import teamlead_case_filter
    q = db.query(models.Case.assigned_fos_id, models.Case.assigned_caller_id).filter(
        teamlead_case_filter(lead))
    if period:
        q = q.filter(models.Case.period == period)
    rows = q.all()
    ids = set()
    for fos_id, caller_id in rows:
        if fos_id:
            ids.add(fos_id)
        if caller_id:
            ids.add(caller_id)
    return list(ids)


def _branch_fos_ids(db: Session, branch: str) -> set[int]:
    """FOS (and callers) assigned to this branch's cases — used so a branch manager can
    monitor field officers who work their branch's cases even though the FOS may be based
    in another location / not tied to any branch."""
    if not branch:
        return set()
    rows = db.query(models.Case.assigned_fos_id, models.Case.assigned_caller_id).filter(
        models.Case.branch == branch, models.Case.removed.isnot(True)).all()
    ids = set()
    for fos_id, caller_id in rows:
        if fos_id:
            ids.add(fos_id)
        if caller_id:
            ids.add(caller_id)
    return ids


def _guard_view(actor: models.User, u: models.User, db: Session = None):
    """Who may open a staff member's profile/performance: the person themselves,
    admin & head office (everyone), a branch manager (their own branch's staff OR any
    field officer working their branch's cases), and a team lead (staff on a case
    carrying the lead's name)."""
    if actor.id == u.id:
        return
    if actor.role in ("admin", "headoffice"):
        return
    if actor.role == "manager":
        if u.branch == actor.branch:
            return
        # FOS are location-independent: allow if they handle any of this branch's cases.
        if db is not None and u.id in _branch_fos_ids(db, actor.branch):
            return
        raise HTTPException(status_code=403, detail="Not in your branch")
    if actor.role == "teamlead":
        if db is None or u.id not in _teamlead_member_ids(db, actor):
            raise HTTPException(status_code=403, detail="Not one of your team members")
        return
    raise HTTPException(status_code=403, detail="Not allowed")


@router.get("/branches")
def branches(db: Session = Depends(get_db), user: models.User = Depends(require_roles("admin", "manager", "headoffice"))):
    """Branch cards: manager, staff counts by role, and case/collection stats.
    Admin sees all branches; a manager sees only their own."""
    users = db.query(models.User).filter(models.User.is_active == True).all()  # noqa: E712

    cards: dict[str, dict] = {}
    for u in users:
        b = u.branch or "Unassigned"
        if user.role == "manager" and b != (user.branch or "Unassigned"):
            continue
        d = cards.setdefault(b, {"branch": b, "manager": None,
                                 "fos": 0, "telecaller": 0, "backend": 0, "staff": 0})
        if u.role == "manager" and d["manager"] is None:
            d["manager"] = {"id": u.id, "name": u.name, "phone": u.phone, "email": u.email}
        if u.role in ("fos", "telecaller", "backend"):
            d[u.role] += 1
            d["staff"] += 1

    paid_enr_col = func.coalesce(func.sum(case((models.Case.paid_status == "PAID", models.Case.enr), else_=0)), 0)
    rows = (db.query(models.Case.branch, func.count(models.Case.id),
                     func.coalesce(func.sum(models.Case.enr), 0),          # total ENR (CC/PL-BL base)
                     paid_enr_col,                                          # recovered ENR
                     func.coalesce(func.sum(models.Case.received_amount), 0),   # cash collected
                     func.coalesce(func.sum(models.Case.funding_amount), 0),
                     func.coalesce(func.sum(models.Case.pending_amount), 0))
            .filter(models.Case.removed.isnot(True))
            .group_by(models.Case.branch).all())
    cstat = {}
    for b, cnt, tenr, penr, cash, fund, pend in rows:
        tenr, penr = _d(tenr), _d(penr)
        if tenr > 0:                       # ENR-based (matches MIS/dashboard) — pending never goes negative
            recovered, pending = penr, round(tenr - penr, 2)
        else:                               # funding-based fallback for older loads
            recovered, pending = _d(cash), _d(pend)
        cstat[b or "Unassigned"] = (cnt, recovered, pending)

    out = []
    for b, d in cards.items():
        c, r, p = cstat.get(b, (0, 0.0, 0.0))
        d.update(cases=c, received=r, pending=p)
        out.append(d)
    out.sort(key=lambda x: x["branch"])
    return out


@router.get("/branch-associates")
def branch_associates(branch: str, db: Session = Depends(get_db),
                      user: models.User = Depends(require_roles("admin", "manager", "headoffice"))):
    """Field officers (and any cross-branch caller) who work THIS branch's cases but are
    based elsewhere / not tied to the branch. Managers can monitor their performance on
    the branch's cases here. Returns per-person stats scoped to this branch only."""
    if user.role == "manager" and branch != (user.branch or "Unassigned"):
        raise HTTPException(status_code=403, detail="Not your branch")

    cases = db.query(models.Case).filter(models.Case.branch == branch,
                                         models.Case.removed.isnot(True)).all()
    # Staff already listed as branch members are excluded (they show in the normal roster).
    branch_member_ids = {r[0] for r in db.query(models.User.id).filter(models.User.branch == branch).all()}

    stats: dict[int, dict] = {}
    for c in cases:
        for uid, role in ((c.assigned_fos_id, "fos"), (c.assigned_caller_id, "telecaller")):
            if not uid or uid in branch_member_ids:
                continue
            s = stats.setdefault(uid, {"id": uid, "role": role, "cases": 0, "paid": 0,
                                       "received": 0.0, "pending": 0.0})
            s["cases"] += 1
            s["paid"] += int((c.paid_status or "").upper() == "PAID")
            s["received"] += _d(c.received_amount)
            s["pending"] += _d(c.pending_amount)

    if not stats:
        return []
    umap = {u.id: u for u in db.query(models.User).filter(models.User.id.in_(list(stats.keys()))).all()}
    out = []
    for uid, s in stats.items():
        u = umap.get(uid)
        if not u:
            continue
        out.append({**s, "name": u.name, "emp_code": u.emp_code, "phone": u.phone,
                    "home_branch": u.branch or "—", "received": round(s["received"], 2),
                    "pending": round(s["pending"], 2)})
    out.sort(key=lambda x: x["received"], reverse=True)
    return out


@router.post("/branches")
def create_branch(body: dict = Body(...), db: Session = Depends(get_db),
                  admin: models.User = Depends(require_roles("admin"))):
    """Create a branch by assigning its manager (with full details)."""
    name = (body.get("branch") or "").strip()
    m = body.get("manager") or {}
    if not name:
        raise HTTPException(status_code=400, detail="Branch name is required")
    if not (m.get("name") and m.get("email") and m.get("password")):
        raise HTTPException(status_code=400, detail="Manager name, email and password are required")
    email = m["email"].strip().lower()
    if db.query(models.User).filter(models.User.email == email).first():
        raise HTTPException(status_code=400, detail="That manager email is already registered")

    mgr = models.User(
        name=m["name"], email=email, phone=m.get("phone"), role="manager",
        branch=name, hashed_password=hash_password(m["password"]),
        employment_type=m.get("employment_type"), address=m.get("address"),
        emergency_contact=m.get("emergency_contact"),
    )
    db.add(mgr)
    db.commit()
    db.refresh(mgr)
    return {"ok": True, "branch": name, "manager_id": mgr.id}


@router.patch("/branches/{name}")
def edit_branch(name: str, body: dict = Body(...), db: Session = Depends(get_db),
                admin: models.User = Depends(require_roles("admin"))):
    """Rename a branch (cascades to its staff and cases) and/or (re)assign its manager."""
    new = (body.get("new_name") or "").strip()
    if new and new != name:
        db.query(models.User).filter(models.User.branch == name).update({models.User.branch: new})
        db.query(models.Case).filter(models.Case.branch == name).update({models.Case.branch: new})
        name = new
    mid = body.get("manager_id")
    if mid:
        m = db.query(models.User).filter(models.User.id == mid).first()
        if m:
            m.role = "manager"
            m.branch = name
    db.commit()
    return {"ok": True, "branch": name}


@router.delete("/branches/{name}")
def delete_branch(name: str, reassign: str | None = None, db: Session = Depends(get_db),
                  admin: models.User = Depends(require_roles("admin"))):
    """Delete a branch. Its staff and cases are moved to `reassign` (another branch) or
    left unassigned. Staff accounts are NOT deleted — use the staff Remove action for that."""
    target = (reassign or "").strip() or None
    n_staff = db.query(models.User).filter(models.User.branch == name).update({models.User.branch: target})
    n_cases = db.query(models.Case).filter(models.Case.branch == name).update({models.Case.branch: target})
    db.commit()
    return {"ok": True, "moved_staff": n_staff, "moved_cases": n_cases, "to": target}


# A "call" is an actual dial the caller logged. PAYMENT / PAID rows are collection events
# (created by caller mark-paid, head-office mark-paid, DPR uploads, live-sheet money edits) and
# must NEVER be counted as calls — that was inflating weekly/monthly counts with random numbers.
_PAY_DISPO = ("PAYMENT", "PAID")


def _window(db: Session, u: models.User, start, case_ids=None, end=None):
    """Activity in a time window [start, end). When case_ids is given, restrict to those cases so
    the daily/weekly/monthly cards honour the selected month (None = all of the person's cases).
    Counts are ACTUAL calls/visits only; collected ₹ still comes from the PAYMENT/PAID events."""
    from sqlalchemy import select
    esc = select(models.Case.id).where(models.Case.escalated.is_(True))   # exclude escalated work
    if u.role == "fos":
        q = db.query(models.Visit).filter(models.Visit.officer_id == u.id,
                                          ~models.Visit.case_id.in_(esc))
        if case_ids is not None:
            q = q.filter(models.Visit.case_id.in_(case_ids or [-1]))
        if start:
            q = q.filter(models.Visit.created_at >= start)
        if end:
            q = q.filter(models.Visit.created_at < end)
        items = q.all()
        return {"label": "visits", "count": len(items),
                "collected": _d(sum(_d(v.amount_collected) for v in items))}
    # telecaller (and any calling role)
    q = db.query(models.CallLog).filter(models.CallLog.caller_id == u.id,
                                        ~models.CallLog.case_id.in_(esc))
    if case_ids is not None:
        q = q.filter(models.CallLog.case_id.in_(case_ids or [-1]))
    if start:
        q = q.filter(models.CallLog.created_at >= start)
    if end:
        q = q.filter(models.CallLog.created_at < end)
    calls = q.all()
    real_calls = [c for c in calls if (c.disposition or "") not in _PAY_DISPO]   # actual dials only
    ptp = sum(1 for c in real_calls if (c.disposition or "") == "PTP")   # RTP = Refuse to Pay, not a promise
    # Collected ₹ still counts every collection event: caller payments, HO mark-paid, DPR
    # (all logged as PAYMENT/PAID; reversals carry a negative amount and net out).
    collected = _d(sum(_d(c.ptp_amount) for c in calls if (c.disposition or "") in _PAY_DISPO))
    return {"label": "calls", "count": len(real_calls), "ptp": ptp, "collected": collected}


def _cal_windows(case_ids=None):
    """Calendar-aligned window bounds (IST) as {name: (start_utc, end_utc)} for the
    performance cards — Today, this calendar Week (Mon→now), this calendar Month (1st→now),
    Overall. By EVENT DATE, so months never bleed into each other."""
    ist_now = datetime.now(IST)
    day = ist_now.replace(hour=0, minute=0, second=0, microsecond=0)
    week = (ist_now - timedelta(days=ist_now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    month = ist_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    to_utc = lambda d: d.astimezone(timezone.utc)
    return {
        "daily": (to_utc(day), None),
        "weekly": (to_utc(week), None),
        "monthly": (to_utc(month), None),
        "overall": (None, None),
    }


def _month_bounds_utc(month_bucket):
    """UTC [start, end) for the selected calendar month (current / last / next). 'all' → (None, None)."""
    ist_now = datetime.now(IST)
    if not month_bucket or month_bucket == "all":
        return (None, None)
    y, m = ist_now.year, ist_now.month
    if month_bucket == "last":
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    elif month_bucket == "next":
        y, m = (y, m + 1) if m < 12 else (y + 1, 1)
    ny, nm = (y, m + 1) if m < 12 else (y + 1, 1)
    start = datetime(y, m, 1, tzinfo=IST).astimezone(timezone.utc)
    end = datetime(ny, nm, 1, tzinfo=IST).astimezone(timezone.utc)
    return (start, end)


def _perf_cards(db: Session, u: models.User, case_ids, month_bucket):
    """Daily / weekly / monthly / overall cards, calendar-aligned by EVENT DATE and scoped to the
    selected month's cases. 'Monthly' follows the chosen calendar month so months never mix; Daily
    and Weekly are today / this calendar week. Counts are actual call-log dials only."""
    w = _cal_windows()
    ms, me = _month_bounds_utc(month_bucket)
    m_start, m_end = (ms, me) if ms else w["monthly"]      # 'all' → current calendar month
    return {
        "daily": _window(db, u, w["daily"][0], case_ids),
        "weekly": _window(db, u, w["weekly"][0], case_ids),
        "monthly": _window(db, u, m_start, case_ids, end=m_end),
        "overall": _window(db, u, None, case_ids),
    }


@router.get("/user/{uid}/performance")
def performance(uid: int, db: Session = Depends(get_db),
                actor: models.User = Depends(get_current_user)):
    """Daily / weekly / monthly / overall performance for a field officer or telecaller.
    Visible to the person themselves, their branch manager, and admins."""
    u = db.query(models.User).filter(models.User.id == uid).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    _guard_view(actor, u, db)

    # Calendar-aligned windows by event date (Today / this Week / this Month / Overall) — no
    # rolling 7/30-day spans, so months never mix. Counts are actual call-log dials only.
    w = _cal_windows()
    return {
        "role": u.role, "name": u.name,
        "daily": _window(db, u, *w["daily"]),
        "weekly": _window(db, u, *w["weekly"]),
        "monthly": _window(db, u, *w["monthly"]),
        "overall": _window(db, u, *w["overall"]),
    }


@router.get("/user/{uid}/dashboard")
def employee_dashboard(uid: int, month_bucket: str | None = "current", db: Session = Depends(get_db),
                       actor: models.User = Depends(get_current_user)):
    """A field officer's / telecaller's full personal analytics — assigned cases, collections,
    trend, dispositions, PTP, activity and recent cases. Visible to self, branch manager, admin.
    Scoped to one month by default (month_bucket=current); pass 'all' for the lifetime view."""
    u = db.query(models.User).filter(models.User.id == uid).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    _guard_view(actor, u, db)

    from sqlalchemy import select
    from .mis import _period_for
    period = _period_for(month_bucket)                                    # None = all months
    esc = select(models.Case.id).where(models.Case.escalated.is_(True))    # escalated → not their perf
    is_caller = u.role == "telecaller"
    cq = db.query(models.Case).filter(models.Case.escalated.isnot(True), models.Case.removed.isnot(True))
    cq = cq.filter(models.Case.assigned_caller_id == uid) if is_caller else cq.filter(models.Case.assigned_fos_id == uid)
    if period:
        cq = cq.filter(models.Case.period == period)
    # A branch manager sees this person's performance ON THEIR BRANCH'S CASES only — so a
    # location-independent FOS shows the manager just their contribution to that branch.
    branch_scoped = actor.role == "manager" and u.branch != actor.branch
    if branch_scoped:
        cq = cq.filter(models.Case.branch == actor.branch)
    cases = cq.all()
    case_ids = {c.id for c in cases}
    calls = db.query(models.CallLog).filter(models.CallLog.caller_id == uid, ~models.CallLog.case_id.in_(esc)).all()
    visits = db.query(models.Visit).filter(models.Visit.officer_id == uid, ~models.Visit.case_id.in_(esc)).all()
    # Tie ALL activity (collections, calls, visits, trend, dispositions, PTP) to the same case set
    # the KPIs use — i.e. the selected month's assigned cases — so the whole profile honours the
    # month toggle instead of showing lifetime call/collection numbers next to 0 assigned cases.
    calls = [cl for cl in calls if cl.case_id in case_ids]
    visits = [v for v in visits if v.case_id in case_ids]
    # Actual dials only for COUNTS (PAYMENT/PAID rows are collection events, not calls).
    real_calls = [cl for cl in calls if (cl.disposition or "") not in ("PAYMENT", "PAID")]

    def paid(c):
        return (c.paid_status or "").upper() == "PAID"

    def pct(a, b):
        return round(a / b * 100.0, 2) if b else 0.0

    def d_ist(dt):
        if not dt:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(IST).date()

    today_d = datetime.now(IST).date()
    total_enr = sum(_d(c.enr) for c in cases)
    recovered = sum(_d(c.received_amount) for c in cases)
    # Joint allocation: a case collected by a JOINT FOS credits its collection to HIM, not the
    # primary. Remove joint-collected-away cash from this (primary) user's recovered; add cash this
    # user collected as a joint FOS on cases allocated to someone else. Allocation/target stay primary.
    recovered -= sum(_d(c.received_amount) for c in cases
                     if getattr(c, "joint_collected_at", None) and getattr(c, "joint_fos_id", None)
                     and c.joint_fos_id != u.id)
    _joint_in = db.query(models.Case).filter(models.Case.joint_fos_id == u.id,
                                             models.Case.joint_collected_at.isnot(None),
                                             models.Case.removed.isnot(True)).all()
    recovered += sum(_d(c.received_amount) for c in _joint_in if c.assigned_fos_id != u.id)
    pending_amt = sum(_d(c.pending_amount) for c in cases)
    resolved = sum(1 for c in cases if paid(c))

    pay_events = [(d_ist(cl.created_at), _d(cl.ptp_amount)) for cl in calls if (cl.disposition or "") in ("PAYMENT", "PAID")]
    pay_events += [(d_ist(v.created_at), _d(v.amount_collected)) for v in visits if _d(v.amount_collected) > 0]
    cash = round(sum(a for d, a in pay_events), 2)
    # What this person actually collected — from THEIR call-log payments + visit-log payments only
    # (credited to them), split so a team lead / manager / HO / admin can judge real collection effort.
    collected_calls = round(sum(_d(cl.ptp_amount) for cl in calls if (cl.disposition or "") in ("PAYMENT", "PAID")), 2)
    collected_visits = round(sum(_d(v.amount_collected) for v in visits if _d(v.amount_collected) > 0), 2)

    trend = []
    for i in range(29, -1, -1):
        dd = today_d - timedelta(days=i)
        trend.append({"date": dd.isoformat(), "collected": round(sum(a for d, a in pay_events if d == dd), 2)})

    disp: dict[str, int] = {}
    for c in cases:
        if c.disposition:
            disp[c.disposition] = disp.get(c.disposition, 0) + 1
    dispositions = sorted(({"label": k, "count": v} for k, v in disp.items()), key=lambda x: x["count"], reverse=True)

    ptp_cases = [c for c in cases if (c.disposition or "").upper() == "PTP"]
    ptp_kept = sum(1 for c in ptp_cases if paid(c))
    ptp_broken = sum(1 for c in ptp_cases if not paid(c) and c.follow_up_date and c.follow_up_date < today_d)

    gfence = float(get_settings().geofence_metres or 300)
    field = {}
    if is_caller:
        field = {"calls": len(real_calls), "calls_today": sum(1 for cl in real_calls if d_ist(cl.created_at) == today_d),
                 "ptp_total": len(ptp_cases), "ptp_kept": ptp_kept, "ptp_broken": ptp_broken}
    else:
        field = {"visits": len(visits), "visits_today": sum(1 for v in visits if d_ist(v.created_at) == today_d),
                 "distance_km": round(sum(_d(v.distance_from_case_m) for v in visits) / 1000.0, 1),
                 "off_location": sum(1 for v in visits if _d(v.distance_from_case_m) > gfence)}

    recent = [{"id": c.id, "customer": c.customer_name, "account": c.account_no,
               "pending": _d(c.pending_amount), "status": c.status, "paid_status": c.paid_status,
               "disposition": c.disposition, "bank": c.bank, "product": c.product}
              for c in sorted(cases, key=lambda x: _d(x.pending_amount), reverse=True)[:25]]

    return {
        "user": {"id": u.id, "name": u.name, "role": u.role, "branch": u.branch,
                 "phone": u.phone, "email": u.email},
        "kpis": {"assigned": len(cases), "resolved": resolved, "pending_count": len(cases) - resolved,
                 "total_enr": round(total_enr, 2), "recovered": round(recovered, 2),
                 "pending_amount": round(pending_amt, 2), "recovery_pct": pct(recovered, total_enr),
                 "cash_collected": cash,
                 "collected_calls": collected_calls, "collected_visits": collected_visits,
                 "collected_logs": round(collected_calls + collected_visits, 2)},
        "performance": _perf_cards(db, u, case_ids, month_bucket),
        "trend": trend,
        "dispositions": dispositions,
        "ptp": {"total": len(ptp_cases), "kept": ptp_kept, "broken": ptp_broken, "kept_pct": pct(ptp_kept, len(ptp_cases))},
        "field": field,
        "recent_cases": recent,
    }


@router.get("/user/{uid}/cases", response_model=list[schemas.CaseOut])
def employee_cases(uid: int, month_bucket: str | None = "current", db: Session = Depends(get_db),
                   actor: models.User = Depends(get_current_user)):
    """Every case assigned to this employee (as FOS or telecaller), tagged with today's
    touch flags & propensity — for the clickable clusters on their dashboard. Scoped to one
    month by default (month_bucket=current) so it matches the dashboard KPIs; 'all' = lifetime."""
    from .cases import _with_score, _mark_today
    from .mis import _period_for
    u = db.query(models.User).filter(models.User.id == uid).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    _guard_view(actor, u, db)
    period = _period_for(month_bucket)
    q = db.query(models.Case).filter(models.Case.removed.isnot(True))
    q = q.filter(models.Case.assigned_caller_id == uid) if u.role == "telecaller" \
        else q.filter(models.Case.assigned_fos_id == uid)
    if period:
        q = q.filter(models.Case.period == period)
    return _mark_today(db, _with_score(q.order_by(models.Case.updated_at.desc()).all()))


@router.post("/transfer-cases")
def transfer_cases(body: dict = Body(...), db: Session = Depends(get_db),
                   actor: models.User = Depends(require_roles("admin", "manager"))):
    """Move ALL of one staff member's assigned cases to another staff member — and, with
    swap=true, exchange both caseloads. Works for FOS (assigned_fos_id), telecaller
    (assigned_caller_id) and team lead (team_lead name). Both must be the same role.
    Managers are limited to their own branch (both staff + the cases)."""
    from_id = body.get("from_user_id")
    to_id = body.get("to_user_id")
    swap = bool(body.get("swap"))
    if not from_id or not to_id or from_id == to_id:
        raise HTTPException(status_code=400, detail="Pick two different staff members")
    a = db.query(models.User).filter(models.User.id == from_id).first()
    b = db.query(models.User).filter(models.User.id == to_id).first()
    if not a or not b:
        raise HTTPException(status_code=404, detail="Staff not found")
    if a.role != b.role:
        raise HTTPException(status_code=400, detail="Both staff must have the same role")
    if actor.role == "manager":
        if a.branch != actor.branch or b.branch != actor.branch:
            raise HTTPException(status_code=403, detail="Both staff must be in your branch")

    role = a.role
    branch_scope = (actor.role == "manager")

    def _cases_for(col, val):
        q = db.query(models.Case).filter(models.Case.removed.isnot(True), col == val)
        if branch_scope:
            q = q.filter(models.Case.branch == actor.branch)
        return q.all()

    moved = 0
    if role == "fos":
        col = models.Case.assigned_fos_id
        attr = "assigned_fos_id"
    elif role == "telecaller":
        col = models.Case.assigned_caller_id
        attr = "assigned_caller_id"
    elif role == "teamlead":
        col = models.Case.team_lead
        attr = "team_lead"
    else:
        raise HTTPException(status_code=400, detail="Only FOS, telecaller or team lead can be transferred")

    a_val, b_val = (a.name, b.name) if role == "teamlead" else (a.id, b.id)
    a_cases = _cases_for(col, a_val)
    b_cases = _cases_for(col, b_val) if swap else []

    for c in a_cases:
        setattr(c, attr, b_val)
        audit.record(db, actor, "transfer", c, field=attr, old=a.name, new=b.name,
                     detail=f"{role} caseload: {a.name} → {b.name}", target_user_id=b.id if role != "teamlead" else None)
        audit.stamp_case(c, actor)
        moved += 1
    for c in b_cases:
        setattr(c, attr, a_val)
        audit.record(db, actor, "transfer", c, field=attr, old=b.name, new=a.name,
                     detail=f"{role} caseload (swap): {b.name} → {a.name}", target_user_id=a.id if role != "teamlead" else None)
        audit.stamp_case(c, actor)
        moved += 1
    db.commit()
    return {"moved": moved, "from": a.name, "to": b.name, "swap": swap, "role": role}


@router.get("/my-team")
def my_team(db: Session = Depends(get_db),
            lead: models.User = Depends(require_roles("teamlead"))):
    """Roster of the FOS/callers reporting to the current team lead, with quick per-member
    stats and phone — powers the member cards (with call button) on the TL dashboard.
    Derived per-case: the staff assigned to cases whose team_lead names this lead."""
    member_ids = _teamlead_member_ids(db, lead)
    members = []
    if member_ids:
        members = db.query(models.User).filter(models.User.id.in_(member_ids),
                                               models.User.is_active == True).all()  # noqa: E712
    out = [{"id": m.id, "name": m.name, "role": m.role, "emp_code": m.emp_code,
            "phone": m.phone, "email": m.email, "branch": m.branch} for m in members]
    out.sort(key=lambda x: (x["role"], x["name"]))
    return out


def _overview_payload(db: Session, lead: models.User, month_bucket: str | None = "current",
                      portfolio: tuple | None = None) -> dict:
    """Team-lead dashboard payload: overall team KPIs, per-member performance cards (with
    phone for calling), a 30-day team collection trend and a member leaderboard. Shared by
    the lead's own /overview and the admin/manager/HO 'view this lead's team' endpoint.
    Scoped to one month by default (month_bucket=current); 'all' = lifetime.

    When `portfolio=(bank, product, branch)` is given (a peer team lead drilling into a shared
    portfolio), the whole payload is confined to that portfolio's cases — team members shown are
    just those handling this portfolio's cases, and every KPI / card / trend counts only it."""
    from .cases import teamlead_case_filter
    from .mis import _period_for
    period = _period_for(month_bucket)
    p_bank = p_product = p_branch = None
    if portfolio:
        p_bank, p_product, p_branch = portfolio

    # The lead's cases are those the upload tagged with their name (not every case the
    # assigned FOS/caller happens to hold), minus escalated/removed — optionally narrowed to
    # one portfolio (bank+product+branch) for the peer drill-down view.
    _cq = db.query(models.Case).filter(
        models.Case.escalated.isnot(True), models.Case.removed.isnot(True),
        teamlead_case_filter(lead))
    if period:
        _cq = _cq.filter(models.Case.period == period)
    if p_bank:
        _cq = _cq.filter(models.Case.bank == p_bank)
    if p_product:
        _cq = _cq.filter(models.Case.product == p_product)
    if p_branch:
        _cq = _cq.filter(models.Case.branch == p_branch)
    cases = _cq.all()

    # Members: within a portfolio view, the staff actually on this portfolio's cases; otherwise
    # the lead's full roster (derived across all their cases).
    if portfolio:
        member_ids = list({i for c in cases for i in (c.assigned_fos_id, c.assigned_caller_id) if i})
    else:
        member_ids = _teamlead_member_ids(db, lead)
    members = []
    if member_ids:
        members = db.query(models.User).filter(models.User.id.in_(member_ids),
                                               models.User.is_active == True).all()  # noqa: E712
    pf_case_ids = [c.id for c in cases] if portfolio else None

    def paid(c):
        return (c.paid_status or "").upper() == "PAID"

    def pct(a, b):
        return round(a / b * 100.0, 2) if b else 0.0

    def d_ist(dt):
        if not dt:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(IST).date()

    today_start = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    cards = []
    for m in members:
        is_caller = m.role == "telecaller"
        mine = [c for c in cases if (c.assigned_caller_id == m.id if is_caller else c.assigned_fos_id == m.id)]
        tenr = sum(_d(c.enr) for c in mine)
        rec = sum(_d(c.received_amount) for c in mine)
        cards.append({
            "id": m.id, "name": m.name, "role": m.role, "emp_code": m.emp_code,
            "phone": m.phone, "email": m.email,
            "assigned": len(mine), "resolved": sum(1 for c in mine if paid(c)),
            "recovered": round(rec, 2), "pending": round(sum(_d(c.pending_amount) for c in mine), 2),
            "recovery_pct": pct(rec, tenr), "today": _window(db, m, today_start, pf_case_ids),
        })

    total_enr = sum(_d(c.enr) for c in cases)
    recovered = sum(_d(c.received_amount) for c in cases)
    kpis = {
        "members": len(members),
        "fos": sum(1 for m in members if m.role == "fos"),
        "callers": sum(1 for m in members if m.role == "telecaller"),
        "cases": len(cases), "resolved": sum(1 for c in cases if paid(c)),
        "total_enr": round(total_enr, 2), "recovered": round(recovered, 2),
        "pending": round(total_enr - recovered, 2) if total_enr else round(sum(_d(c.pending_amount) for c in cases), 2),
        "recovery_pct": pct(recovered, total_enr),
    }

    esc = select(models.Case.id).where(models.Case.escalated.is_(True))
    _cq_calls = db.query(models.CallLog).filter(models.CallLog.caller_id.in_(member_ids),
                                                ~models.CallLog.case_id.in_(esc)) if member_ids else None
    _cq_visits = db.query(models.Visit).filter(models.Visit.officer_id.in_(member_ids),
                                               ~models.Visit.case_id.in_(esc)) if member_ids else None
    if portfolio and member_ids:
        _cq_calls = _cq_calls.filter(models.CallLog.case_id.in_(pf_case_ids or [-1]))
        _cq_visits = _cq_visits.filter(models.Visit.case_id.in_(pf_case_ids or [-1]))
    calls = _cq_calls.all() if _cq_calls is not None else []
    visits = _cq_visits.all() if _cq_visits is not None else []
    pay = [(d_ist(cl.created_at), _d(cl.ptp_amount)) for cl in calls if (cl.disposition or "") in ("PAYMENT", "PAID")]
    pay += [(d_ist(v.created_at), _d(v.amount_collected)) for v in visits if _d(v.amount_collected) > 0]
    today_d = datetime.now(IST).date()
    trend = [{"date": (today_d - timedelta(days=i)).isoformat(),
              "collected": round(sum(a for d, a in pay if d == today_d - timedelta(days=i)), 2)}
             for i in range(29, -1, -1)]

    return {"lead": {"id": lead.id, "name": lead.name, "branch": lead.branch},
            "members": cards, "kpis": kpis, "trend": trend,
            "leaderboard": sorted(cards, key=lambda x: x["recovered"], reverse=True)}


@router.get("/overview")
def team_overview(month_bucket: str | None = "current", db: Session = Depends(get_db),
                  lead: models.User = Depends(require_roles("teamlead"))):
    """The signed-in team lead's own team dashboard."""
    return _overview_payload(db, lead, month_bucket)


@router.get("/lead/{uid}/overview")
def lead_overview(uid: int, month_bucket: str | None = "current", db: Session = Depends(get_db),
                  actor: models.User = Depends(get_current_user)):
    """The SAME team dashboard a team lead sees for their own team — exposed to admin, head
    office and the lead's branch manager (and the lead themselves) so they can review a
    team lead's team and each member's performance from the lead's profile."""
    lead = db.query(models.User).filter(models.User.id == uid).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Team lead not found")
    if not (lead.role == "teamlead" or getattr(lead, "also_team_lead", False)):
        raise HTTPException(status_code=400, detail="That user is not a team lead")
    if actor.id != lead.id and actor.role not in ("admin", "headoffice"):
        if not (actor.role == "manager" and lead.branch == actor.branch):
            raise HTTPException(status_code=403, detail="Not allowed to view this team")
    return _overview_payload(db, lead, month_bucket)


# ── Team-lead portfolio drill-down ──────────────────────────────────────────────
# A team lead can browse the portfolios they work on (bank+product+branch), see every OTHER
# team lead working the same portfolio, and open any of those peer teams READ-ONLY. Access is
# strictly same-portfolio: a lead only ever sees teams inside a portfolio they themselves work.

def _pf_filter(q, bank, product, branch):
    """Apply portfolio filters. Only non-empty values narrow the query (empty/None = any) —
    so a bank+product portfolio with no branch split matches across its locations."""
    if bank:
        q = q.filter(models.Case.bank == bank)
    if product:
        q = q.filter(models.Case.product == product)
    if branch:
        q = q.filter(models.Case.branch == branch)
    return q


def _lead_works_portfolio(db: Session, lead: models.User, bank, product, branch) -> bool:
    """True if this team lead owns at least one live case in the given portfolio."""
    from .cases import teamlead_case_filter
    q = db.query(models.Case.id).filter(models.Case.removed.isnot(True), teamlead_case_filter(lead))
    q = _pf_filter(q, bank, product, branch)
    return db.query(q.exists()).scalar()


def _tl_resolver(db: Session):
    """Return resolve(cell) → team-lead User for a case's team_lead value (name or TL code)."""
    tls = [u for u in db.query(models.User).all()
           if u.role == "teamlead" or getattr(u, "also_team_lead", False)]
    m = {}
    for u in tls:
        if u.name:
            m.setdefault(u.name.strip().upper(), u)
        if u.role == "teamlead" and u.emp_code:
            m[u.emp_code.strip().upper()] = u
        if getattr(u, "tl_emp_code", None):
            m[u.tl_emp_code.strip().upper()] = u

    def resolve(val):
        if not val or not str(val).strip():
            return None
        return m.get(str(val).strip().upper())
    return resolve


@router.get("/portfolios")
def my_portfolios(db: Session = Depends(get_db),
                  lead: models.User = Depends(require_roles("teamlead"))):
    """Portfolios (bank + product + branch) the signed-in team lead works on, with quick totals —
    the entry list for the team lead's Portfolios section."""
    from .cases import teamlead_case_filter
    rows = db.query(
        models.Case.bank, models.Case.product, models.Case.branch,
        models.Case.funding_amount, models.Case.total_outstanding, models.Case.enr,
        models.Case.principal_outstanding, models.Case.received_amount, models.Case.paid_status,
    ).filter(models.Case.removed.isnot(True), teamlead_case_filter(lead)).all()
    agg: dict = {}
    for b, p, br, fund, tos, enr, pos, recv, pstat in rows:
        base = float(fund or 0) or float(tos or 0) or float(enr or 0) or float(pos or 0)
        rc = float(recv or 0)
        key = (b or "—", p or "—", (br or "").strip())
        d = agg.setdefault(key, {"bank": key[0], "product": key[1], "branch": key[2],
                                 "count": 0, "received": 0.0, "pending": 0.0, "paid": 0, "unpaid": 0})
        d["count"] += 1
        d["received"] += rc
        d["pending"] += max(0.0, base - rc)
        d["paid" if (pstat or "").upper() == "PAID" else "unpaid"] += 1
    out = sorted(agg.values(), key=lambda x: (x["bank"], x["product"], x["branch"]))
    for d in out:
        d["received"] = round(d["received"], 2)
        d["pending"] = round(d["pending"], 2)
    return out


@router.get("/portfolio/leads")
def portfolio_leads(bank: str | None = None, product: str | None = None, branch: str | None = None,
                    db: Session = Depends(get_db),
                    lead: models.User = Depends(require_roles("teamlead"))):
    """Every team lead working the given portfolio, with quick per-team totals. Authorized only if
    the requesting lead works this portfolio too (same-portfolio rule)."""
    if not _lead_works_portfolio(db, lead, bank, product, branch):
        raise HTTPException(status_code=403, detail="This portfolio is not in your scope")
    resolve = _tl_resolver(db)
    q = db.query(
        models.Case.team_lead, models.Case.assigned_fos_id, models.Case.assigned_caller_id,
        models.Case.funding_amount, models.Case.total_outstanding, models.Case.enr,
        models.Case.principal_outstanding, models.Case.received_amount, models.Case.paid_status,
    ).filter(models.Case.removed.isnot(True), models.Case.escalated.isnot(True))
    q = _pf_filter(q, bank, product, branch)
    agg: dict = {}
    for tl_val, fos_id, caller_id, fund, tos, enr, pos, recv, pstat in q.all():
        tlu = resolve(tl_val)
        if not tlu:
            continue
        base = float(fund or 0) or float(tos or 0) or float(enr or 0) or float(pos or 0)
        rc = float(recv or 0)
        d = agg.setdefault(tlu.id, {"id": tlu.id, "name": tlu.name, "emp_code": tlu.emp_code,
                                    "branch": tlu.branch, "count": 0, "received": 0.0,
                                    "pending": 0.0, "paid": 0, "unpaid": 0, "_members": set(),
                                    "is_me": tlu.id == lead.id})
        d["count"] += 1
        d["received"] += rc
        d["pending"] += max(0.0, base - rc)
        d["paid" if (pstat or "").upper() == "PAID" else "unpaid"] += 1
        if fos_id:
            d["_members"].add(fos_id)
        if caller_id:
            d["_members"].add(caller_id)
    out = []
    for d in agg.values():
        d["members"] = len(d.pop("_members"))
        d["received"] = round(d["received"], 2)
        d["pending"] = round(d["pending"], 2)
        out.append(d)
    out.sort(key=lambda x: (not x["is_me"], x["name"] or ""))   # the requester first, then A→Z
    return out


@router.get("/portfolio/lead/{uid}/overview")
def portfolio_lead_overview(uid: int, bank: str | None = None, product: str | None = None,
                            branch: str | None = None, month_bucket: str | None = "current",
                            db: Session = Depends(get_db),
                            lead: models.User = Depends(require_roles("teamlead"))):
    """Read-only team dashboard for a PEER team lead, confined to one shared portfolio. Allowed
    only when both the requester and the target lead work that portfolio."""
    if not _lead_works_portfolio(db, lead, bank, product, branch):
        raise HTTPException(status_code=403, detail="This portfolio is not in your scope")
    target = db.query(models.User).filter(models.User.id == uid).first()
    if not target:
        raise HTTPException(status_code=404, detail="Team lead not found")
    if not (target.role == "teamlead" or getattr(target, "also_team_lead", False)):
        raise HTTPException(status_code=400, detail="That user is not a team lead")
    if not _lead_works_portfolio(db, target, bank, product, branch):
        raise HTTPException(status_code=403, detail="That team lead doesn't work this portfolio")
    return _overview_payload(db, target, month_bucket, portfolio=(bank, product, branch))


@router.get("/portfolio/lead/{uid}/cases")
def portfolio_lead_cases(uid: int, bank: str | None = None, product: str | None = None,
                         branch: str | None = None, month_bucket: str | None = "current",
                         db: Session = Depends(get_db),
                         lead: models.User = Depends(require_roles("teamlead"))):
    """Read-only case list (with status) for a PEER team lead inside one shared portfolio —
    powers the 'cases & case status' view of the drill-down. Same-portfolio rule enforced."""
    if not _lead_works_portfolio(db, lead, bank, product, branch):
        raise HTTPException(status_code=403, detail="This portfolio is not in your scope")
    target = db.query(models.User).filter(models.User.id == uid).first()
    if not target or not (target.role == "teamlead" or getattr(target, "also_team_lead", False)):
        raise HTTPException(status_code=404, detail="Team lead not found")
    if not _lead_works_portfolio(db, target, bank, product, branch):
        raise HTTPException(status_code=403, detail="That team lead doesn't work this portfolio")
    from .cases import teamlead_case_filter
    from .mis import _period_for
    period = _period_for(month_bucket)
    q = db.query(models.Case).filter(models.Case.removed.isnot(True),
                                     models.Case.escalated.isnot(True),
                                     teamlead_case_filter(target))
    q = _pf_filter(q, bank, product, branch)
    if period:
        q = q.filter(models.Case.period == period)
    names = {u.id: u.name for u in db.query(models.User).all()}
    out = []
    for c in q.order_by(models.Case.paid_status.desc(), models.Case.id.desc()).limit(2000).all():
        base = _d(c.funding_amount) or _d(c.total_outstanding) or _d(c.enr) or _d(c.principal_outstanding)
        rc = _d(c.received_amount)
        out.append({
            "id": c.id, "account_no": c.account_no,
            "customer": c.customer_name or getattr(c, "name", None),
            "bank": c.bank, "product": c.product, "branch": c.branch,
            "fos": names.get(c.assigned_fos_id), "caller": names.get(c.assigned_caller_id),
            "paid_status": c.paid_status, "disposition": c.disposition,
            "received": round(rc, 2), "pending": round(max(0.0, base - rc), 2),
            "enr": round(_d(c.enr), 2), "period": c.period,
        })
    return {"count": len(out), "cases": out}


# ================================================================ staff coverage Excel (FOS / callers)

@router.get("/staff-report")
def staff_report(kind: str = "fos", month_bucket: str | None = "current", layout: str = "compact",
                 db: Session = Depends(get_db),
                 actor: models.User = Depends(require_roles("admin", "headoffice", "teamlead"))):
    """One styled workbook for ALL FOS (kind=fos) or ALL callers (kind=caller): per person — emp ID,
    name, assigned, visited/unvisited (FOS) or contacted/not contacted (callers), paid/unpaid with %,
    and every portfolio they work — plus a portfolio-wise sheet with the same counts per person.
    Admin/HO see everyone; a team lead sees only cases carrying their name."""
    import io
    from fastapi.responses import StreamingResponse
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.formatting.rule import DataBarRule
    from openpyxl.utils import get_column_letter
    from .mis import _period_for

    is_fos = kind != "caller"
    act_lbl, nact_lbl = ("Visited", "Unvisited") if is_fos else ("Contacted", "Not contacted")
    period = _period_for(month_bucket)
    owner_col = models.Case.assigned_fos_id if is_fos else models.Case.assigned_caller_id

    q = db.query(models.Case).filter(models.Case.removed.isnot(True), owner_col.isnot(None))
    if period:
        q = q.filter(models.Case.period == period)
    if actor.role == "teamlead":
        from .cases import teamlead_case_filter
        q = q.filter(teamlead_case_filter(actor))
    cases = q.all()
    ids = [c.id for c in cases]

    # Activity per case: FOS → a visit logged (or the case's visited flag); caller → a real call logged
    # (PAYMENT/PAID rows are collection events, not calls) or last_contacted_at set.
    touched = set()
    for chunk in [ids[i:i + 5000] for i in range(0, len(ids), 5000)]:
        if is_fos:
            touched |= {cid for (cid,) in db.query(models.Visit.case_id)
                        .filter(models.Visit.case_id.in_(chunk)).distinct()}
        else:
            touched |= {cid for (cid,) in db.query(models.CallLog.case_id)
                        .filter(models.CallLog.case_id.in_(chunk),
                                models.CallLog.disposition.notin_(("PAYMENT", "PAID"))).distinct()}

    def active(c):
        return c.id in touched or (bool(c.visited) if is_fos else c.last_contacted_at is not None)

    def is_paid(c):
        return (c.paid_status or "").upper() == "PAID"

    people = {u.id: u for u in db.query(models.User).filter(
        models.User.id.in_({getattr(c, owner_col.key) for c in cases})).all()} if cases else {}

    per = {}      # uid -> {"tot","act","paid","tos","ptos","ports": {(bank,prod): [tot,act,paid,tos,paid_tos]}}
    for c in cases:
        uid = getattr(c, owner_col.key)
        p = per.setdefault(uid, {"tot": 0, "act": 0, "paid": 0, "tos": 0.0, "ptos": 0.0, "ports": {}})
        a, pd = active(c), is_paid(c)
        tos = _d(c.total_outstanding)
        p["tot"] += 1; p["act"] += a; p["paid"] += pd; p["tos"] += tos; p["ptos"] += tos if pd else 0.0
        k = ((c.bank or "—").strip(), (c.product or "—").strip())
        r = p["ports"].setdefault(k, [0, 0, 0, 0.0, 0.0])
        r[0] += 1; r[1] += a; r[2] += pd; r[3] += tos; r[4] += tos if pd else 0.0

    def pct(a, b):
        return (a / b) if b else 0.0

    order = sorted(per, key=lambda u: ((people.get(u).name if people.get(u) else "") or "").lower())

    # ---------------- styling
    BLUE, LIGHT, ZEBRA = "1D4ED8", "EEF3FF", "F7F9FC"
    HEAD_FILL = PatternFill("solid", fgColor=BLUE)
    HEAD_FONT = Font(bold=True, color="FFFFFF", size=10.5)
    TITLE_FONT = Font(bold=True, size=15, color="0F2747")
    SUB_FONT = Font(size=10, color="5B6B82")
    TOT_FILL = PatternFill("solid", fgColor="DCE6FA")
    GOOD, MID, BAD = PatternFill("solid", fgColor="C6EFCE"), PatternFill("solid", fgColor="FFEB9C"), PatternFill("solid", fgColor="FFC7CE")
    side = Side(style="thin", color="D6DEEA")
    BORDER = Border(left=side, right=side, top=side, bottom=side)
    CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
    LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)

    label_month = period or "All months"
    role_lbl = "FOS" if is_fos else "Callers"
    when = datetime.now(IST).strftime("%d-%b-%Y %H:%M")

    def title(ws, text, ncols):
        ws.append([text]); ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
        ws["A1"].font = TITLE_FONT
        scope = "Your team" if actor.role == "teamlead" else "All branches"
        ws.append([f"Month: {label_month}   ·   Attendance: {_per}   ·   {scope}   ·   Generated {when} by {actor.name or actor.emp_code or ''}"])
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=ncols)
        ws["A2"].font = SUB_FONT
        ws.append([])
        ws.row_dimensions[1].height = 24

    def header(ws, cols):
        ws.append(cols)
        r = ws.max_row
        for c in ws[r]:
            c.fill, c.font, c.alignment, c.border = HEAD_FILL, HEAD_FONT, CENTER, BORDER
        ws.row_dimensions[r].height = 30
        return r

    def tint(cell, v):
        cell.fill = GOOD if v >= 0.6 else MID if v >= 0.3 else BAD

    def style_row(ws, r, pct_cols, zebra, total=False, left_cols=(1, 2), money_cols=()):
        for c in ws[r]:
            c.border = BORDER
            c.alignment = LEFT if c.column in left_cols else CENTER
            if total:
                c.fill = TOT_FILL; c.font = Font(bold=True)
            elif zebra:
                c.fill = PatternFill("solid", fgColor=ZEBRA)
        for col in money_cols:
            ws.cell(row=r, column=col).number_format = '"₹"#,##0'
        for col in pct_cols:
            cell = ws.cell(row=r, column=col)
            cell.number_format = "0.0%"
            if not total:
                tint(cell, cell.value or 0)

    # ---- attendance for the report month (present / absent / leave days per person, up to today)
    from datetime import date as _date
    from ..leave_policy import day_credit
    _today = datetime.now(IST).date()
    _per = period or _today.strftime("%Y-%m")
    _y, _m = int(_per[:4]), int(_per[5:7])
    _first = _date(_y, _m, 1)
    _nxt = _date(_y + (_m == 12), (_m % 12) + 1, 1)
    _days = [_first + timedelta(days=i) for i in range((_nxt - _first).days)]
    _uids = list(per.keys())
    _arows, _lvs = {}, {}
    if _uids:
        for a in db.query(models.Attendance).filter(models.Attendance.user_id.in_(_uids),
                                                    models.Attendance.date >= _first,
                                                    models.Attendance.date < _nxt).all():
            _arows[(a.user_id, a.date)] = a
        for lv in db.query(models.Leave).filter(models.Leave.user_id.in_(_uids), models.Leave.status == "approved",
                                                models.Leave.start_date < _nxt, models.Leave.end_date >= _first).all():
            _lvs.setdefault(lv.user_id, []).append(lv)
    att = {}
    for uid in _uids:
        pr = ab = lvd = 0.0
        for d in _days:
            if d > _today:
                break
            cands = [l for l in _lvs.get(uid, []) if l.start_date <= d <= l.end_date]
            lv = next((l for l in cands if not l.half_day), cands[0] if cands else None)
            cr = day_credit(_arows.get((uid, d)), lv, d, _today)
            pr += cr["present"]; ab += cr["absent"]; lvd += cr["leave"]
        att[uid] = (pr, ab, lvd)

    def _n(v):
        return int(v) if float(v).is_integer() else round(v, 1)

    def att_row(uid):
        pr, ab, lvd = att.get(uid, (0, 0, 0))
        return [_n(pr), _n(ab), _n(lvd)]
    att_tot = [_n(sum(v[i] for v in att.values())) for i in range(3)]

    wb = Workbook()
    ws = wb.active; ws.title = f"{role_lbl} report"
    if layout == "compact":
        # COMPACT: one row per person, but only THEIR portfolios, packed side by side
        # (Portfolio 1, Portfolio 2, …) — no empty blocks for portfolios they don't work.
        maxp = max((len(p["ports"]) for p in per.values()), default=0)
        ID_COLS = ["Emp ID", "Name", "Branch", "No. of portfolios", "Present days", "Absent days", "Leave days"]
        OV_COLS = ["Cases assigned", act_lbl, nact_lbl, f"{act_lbl} %", "Paid", "Unpaid",
                   "Total TOS", "Paid TOS", "Paid % (TOS)"]
        PF_COLS = ["Portfolio", "Assigned", act_lbl, nact_lbl, f"{act_lbl} %", "Paid", "Unpaid", "Paid % (TOS)"]
        ncols = len(ID_COLS) + len(OV_COLS) + len(PF_COLS) * maxp
        title(ws, f"{role_lbl} coverage report — {label_month}", min(ncols, 18))
        BANDS = ["0F766E", "7C3AED", "B45309", "BE185D", "0369A1", "4D7C0F", "9F1239"]
        g = ws.max_row + 1; h = g + 1
        def band(col0, names, text, color):
            ws.merge_cells(start_row=g, start_column=col0, end_row=g, end_column=col0 + len(names) - 1)
            c = ws.cell(row=g, column=col0, value=text)
            c.fill = PatternFill("solid", fgColor=color); c.font = HEAD_FONT; c.alignment = CENTER
            for j, name in enumerate(names, start=col0):
                hc = ws.cell(row=h, column=j, value=name)
                hc.fill = PatternFill("solid", fgColor=color); hc.font = HEAD_FONT; hc.alignment = CENTER; hc.border = BORDER
        band(1, ID_COLS, "Employee", "0F2747")
        band(len(ID_COLS) + 1, OV_COLS, "Overall", BLUE)
        base = len(ID_COLS) + len(OV_COLS) + 1
        for i in range(maxp):
            band(base + i * len(PF_COLS), PF_COLS, f"Portfolio {i + 1}", BANDS[i % len(BANDS)])
        ws.row_dimensions[g].height = 20; ws.row_dimensions[h].height = 30
        pct_cols = [len(ID_COLS) + 4, len(ID_COLS) + 9] + \
                   [base + i * len(PF_COLS) + o for i in range(maxp) for o in (4, 7)]
        money_cols = [len(ID_COLS) + 7, len(ID_COLS) + 8]
        T = [0, 0, 0, 0.0, 0.0]
        first = h + 1
        for i, uid in enumerate(order):
            u, p = people.get(uid), per[uid]
            row = [(u.emp_code if u else "") or "", (u.name if u else f"#{uid}") or "", (u.branch if u else "") or "",
                   len(p["ports"]), *att_row(uid),
                   p["tot"], p["act"], p["tot"] - p["act"], pct(p["act"], p["tot"]),
                   p["paid"], p["tot"] - p["paid"], round(p["tos"]), round(p["ptos"]), pct(p["ptos"], p["tos"])]
            for (bk, pr), (n, a, pd, tt, pt) in sorted(p["ports"].items(), key=lambda kv: -kv[1][0]):
                row += [f"{bk} · {pr}", n, a, n - a, pct(a, n), pd, n - pd, pct(pt, tt)]
            ws.append(row)
            r = ws.max_row
            style_row(ws, r, (), i % 2 == 1, left_cols=(1, 2, 3), money_cols=money_cols)
            for k2 in range(len(p["ports"])):                     # portfolio name cells: bold, left
                c = ws.cell(row=r, column=base + k2 * len(PF_COLS))
                c.font = Font(bold=True, color="0F2747"); c.alignment = LEFT
            for c in pct_cols:
                cell = ws.cell(row=r, column=c)
                if isinstance(cell.value, (int, float)):
                    cell.number_format = "0.0%"; tint(cell, cell.value)
            T[0] += p["tot"]; T[1] += p["act"]; T[2] += p["paid"]; T[3] += p["tos"]; T[4] += p["ptos"]
        last = ws.max_row
        ws.append(["", f"TOTAL ({len(order)} {role_lbl})", "", "", *att_tot,
                   T[0], T[1], T[0] - T[1], pct(T[1], T[0]), T[2], T[0] - T[2], round(T[3]), round(T[4]), pct(T[4], T[3])])
        style_row(ws, ws.max_row, (), False, total=True, left_cols=(1, 2, 3), money_cols=money_cols)
        for c in (len(ID_COLS) + 4, len(ID_COLS) + 9):
            ws.cell(row=ws.max_row, column=c).number_format = "0.0%"
        if last >= first:
            ws.conditional_formatting.add(f"{get_column_letter(len(ID_COLS) + 1)}{first}:{get_column_letter(len(ID_COLS) + 1)}{last}", DataBarRule(start_type="min", end_type="max", color="7DA2F0"))
        for i, w in enumerate([11, 24, 14, 10, 9, 9, 9] + [11, 10, 11, 10, 8, 8, 14, 14, 11], 1):
            ws.column_dimensions[get_column_letter(i)].width = w
        for i in range(maxp):
            for j, w in enumerate([18, 9, 9, 10, 9, 7, 8, 10]):
                ws.column_dimensions[get_column_letter(base + i * len(PF_COLS) + j)].width = w
        ws.freeze_panes = ws.cell(row=first, column=3)
        ws.auto_filter.ref = f"A{h}:{get_column_letter(max(ncols, 13))}{max(last, h)}"
    else:

        # One sheet, ONE ROW PER PERSON. Columns: identity + overall block, then one column block per
        # portfolio (bank · product) with the same metrics; a person's blank block = not working it.
        ports_all = {}
        for p in per.values():
            for k, v in p["ports"].items():
                ports_all[k] = ports_all.get(k, 0) + v[0]
        port_keys = [k for k, _ in sorted(ports_all.items(), key=lambda kv: -kv[1])]

        ID_COLS = ["Emp ID", "Name", "Branch", "No. of portfolios", "Present days", "Absent days", "Leave days"]
        OV_COLS = ["Cases assigned", act_lbl, nact_lbl, f"{act_lbl} %", "Paid", "Unpaid",
                   "Total TOS", "Paid TOS", "Paid % (TOS)"]
        PF_COLS = ["Assigned", act_lbl, nact_lbl, f"{act_lbl} %", "Paid", "Unpaid", "Paid % (TOS)"]
        ncols = len(ID_COLS) + len(OV_COLS) + len(PF_COLS) * len(port_keys)
        title(ws, f"{role_lbl} coverage report — {label_month}", min(ncols, 18))

        # Two header rows: group band (Overall / each portfolio) + metric names.
        BANDS = ["1D4ED8", "0F766E", "7C3AED", "B45309", "BE185D", "0369A1", "4D7C0F", "9F1239"]
        g = ws.max_row + 1; h = g + 1
        def band(col0, width, text, color):
            ws.merge_cells(start_row=g, start_column=col0, end_row=g, end_column=col0 + width - 1)
            c = ws.cell(row=g, column=col0, value=text)
            c.fill = PatternFill("solid", fgColor=color); c.font = HEAD_FONT; c.alignment = CENTER
            for j in range(col0, col0 + width):
                ws.cell(row=g, column=j).border = BORDER; ws.cell(row=g, column=j).fill = PatternFill("solid", fgColor=color)
            for j, name in enumerate(cols_for[text], start=col0):
                hc = ws.cell(row=h, column=j, value=name)
                hc.fill = PatternFill("solid", fgColor=color); hc.font = HEAD_FONT; hc.alignment = CENTER; hc.border = BORDER
        cols_for = {"Employee": ID_COLS, "Overall": OV_COLS}
        band(1, len(ID_COLS), "Employee", "0F2747")
        band(len(ID_COLS) + 1, len(OV_COLS), "Overall", BLUE)
        starts = {}
        col = len(ID_COLS) + len(OV_COLS) + 1
        for i, k in enumerate(port_keys):
            lbl = f"{k[0]} · {k[1]}"
            cols_for[lbl] = PF_COLS
            band(col, len(PF_COLS), lbl, BANDS[(i + 1) % len(BANDS)])
            starts[k] = col; col += len(PF_COLS)
        ws.row_dimensions[g].height = 20; ws.row_dimensions[h].height = 30

        pct_cols = [len(ID_COLS) + 4, len(ID_COLS) + 9] + [starts[k] + 3 for k in port_keys] + [starts[k] + 6 for k in port_keys]
        money_cols = [len(ID_COLS) + 7, len(ID_COLS) + 8]
        T = [0, 0, 0, 0.0, 0.0]
        PT = {k: [0, 0, 0, 0.0, 0.0] for k in port_keys}
        first = h + 1
        for i, uid in enumerate(order):
            u, p = people.get(uid), per[uid]
            row = [(u.emp_code if u else "") or "", (u.name if u else f"#{uid}") or "", (u.branch if u else "") or "",
                   len(p["ports"]), *att_row(uid),
                   p["tot"], p["act"], p["tot"] - p["act"], pct(p["act"], p["tot"]),
                   p["paid"], p["tot"] - p["paid"], round(p["tos"]), round(p["ptos"]), pct(p["ptos"], p["tos"])]
            for k in port_keys:
                v = p["ports"].get(k)
                if v:
                    n, a, pd, tt, pt = v
                    row += [n, a, n - a, pct(a, n), pd, n - pd, pct(pt, tt)]
                    for j in range(5): PT[k][j] += v[j]
                else:
                    row += [None] * len(PF_COLS)
            ws.append(row)
            style_row(ws, ws.max_row, (), i % 2 == 1, left_cols=(1, 2, 3), money_cols=money_cols)
            for c in pct_cols:
                cell = ws.cell(row=ws.max_row, column=c)
                if cell.value is not None:
                    cell.number_format = "0.0%"; tint(cell, cell.value)
            T[0] += p["tot"]; T[1] += p["act"]; T[2] += p["paid"]; T[3] += p["tos"]; T[4] += p["ptos"]
        last = ws.max_row
        tot = ["", f"TOTAL ({len(order)} {role_lbl})", "", len(port_keys), *att_tot,
               T[0], T[1], T[0] - T[1], pct(T[1], T[0]), T[2], T[0] - T[2], round(T[3]), round(T[4]), pct(T[4], T[3])]
        for k in port_keys:
            n, a, pd, tt, pt = PT[k]
            tot += [n, a, n - a, pct(a, n), pd, n - pd, pct(pt, tt)]
        ws.append(tot)
        style_row(ws, ws.max_row, (), False, total=True, left_cols=(1, 2, 3), money_cols=money_cols)
        for c in pct_cols:
            ws.cell(row=ws.max_row, column=c).number_format = "0.0%"

        if last >= first:
            ws.conditional_formatting.add(f"{get_column_letter(len(ID_COLS) + 1)}{first}:{get_column_letter(len(ID_COLS) + 1)}{last}", DataBarRule(start_type="min", end_type="max", color="7DA2F0"))
        for i, w in enumerate([11, 24, 14, 10, 9, 9, 9] + [11, 10, 11, 10, 8, 8, 14, 14, 11], 1):
            ws.column_dimensions[get_column_letter(i)].width = w
        for k in port_keys:
            for j, w in enumerate([9, 9, 10, 9, 7, 8, 10]):
                ws.column_dimensions[get_column_letter(starts[k] + j)].width = w
        ws.freeze_panes = ws.cell(row=first, column=3)          # names + headers stay visible while scrolling
        ws.auto_filter.ref = f"A{h}:{get_column_letter(ncols)}{max(last, h)}"

    # Legend
    ws.append([]); ws.append([])
    note = (f"{act_lbl}: a {'visit was logged' if is_fos else 'call was logged'} on the case. "
            "Paid = case marked PAID; Unpaid includes partial. Paid % (TOS) = TOS of paid cases ÷ total TOS. "
            "Portfolio 1, 2, … = that person's own portfolios, largest first. Colours: green ≥ 60%, amber 30–59%, red < 30%.")
    ws.append([note]); ws.merge_cells(start_row=ws.max_row, start_column=1, end_row=ws.max_row, end_column=min(ncols, 18))
    ws.cell(row=ws.max_row, column=1).font = SUB_FONT

    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    audit.record(db, actor, "download", None, entity_type="download",
                 detail=f"Downloaded {role_lbl} coverage report ({label_month})")
    db.commit()
    fname = f"{role_lbl}_coverage_{(period or 'all').replace('-', '_')}.xlsx"
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'})
