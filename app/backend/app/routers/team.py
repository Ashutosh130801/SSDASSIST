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


def _teamlead_member_ids(db: Session, lead: models.User) -> list[int]:
    """FOS/caller ids a team lead oversees — derived per-case from the upload sheet:
    the distinct staff assigned to cases whose team_lead field names this lead. A FOS
    or caller only counts here for the cases that carry the lead's name, so the same
    person can report to different leads on different cases."""
    from .cases import teamlead_case_filter
    rows = db.query(models.Case.assigned_fos_id, models.Case.assigned_caller_id).filter(
        teamlead_case_filter(lead)).all()
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


def _window(db: Session, u: models.User, start, case_ids=None):
    """Activity in a time window. When case_ids is given, restrict to those cases so the
    daily/weekly/monthly/overall cards honour the profile's month filter (None = all cases)."""
    from sqlalchemy import select
    esc = select(models.Case.id).where(models.Case.escalated.is_(True))   # exclude escalated work
    if u.role == "fos":
        q = db.query(models.Visit).filter(models.Visit.officer_id == u.id,
                                          ~models.Visit.case_id.in_(esc))
        if case_ids is not None:
            q = q.filter(models.Visit.case_id.in_(case_ids or [-1]))
        if start:
            q = q.filter(models.Visit.created_at >= start)
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
    calls = q.all()
    ptp = sum(1 for c in calls if (c.disposition or "") == "PTP")   # RTP = Refuse to Pay, not a promise
    # Every collection event counts: caller payments, head-office mark-paid, DPR (all logged as
    # PAYMENT or PAID; reversals carry a negative amount and net out).
    collected = _d(sum(_d(c.ptp_amount) for c in calls if (c.disposition or "") in ("PAYMENT", "PAID")))
    return {"label": "calls", "count": len(calls), "ptp": ptp, "collected": collected}


@router.get("/user/{uid}/performance")
def performance(uid: int, db: Session = Depends(get_db),
                actor: models.User = Depends(get_current_user)):
    """Daily / weekly / monthly / overall performance for a field officer or telecaller.
    Visible to the person themselves, their branch manager, and admins."""
    u = db.query(models.User).filter(models.User.id == uid).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    _guard_view(actor, u, db)

    now = datetime.now(timezone.utc)
    today = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    return {
        "role": u.role, "name": u.name,
        "daily": _window(db, u, today),
        "weekly": _window(db, u, now - timedelta(days=7)),
        "monthly": _window(db, u, now - timedelta(days=30)),
        "overall": _window(db, u, None),
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
        field = {"calls": len(calls), "calls_today": sum(1 for cl in calls if d_ist(cl.created_at) == today_d),
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
        "performance": {"daily": _window(db, u, datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc), case_ids),
                        "weekly": _window(db, u, datetime.now(timezone.utc) - timedelta(days=7), case_ids),
                        "monthly": _window(db, u, datetime.now(timezone.utc) - timedelta(days=30), case_ids),
                        "overall": _window(db, u, None, case_ids)},
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


def _overview_payload(db: Session, lead: models.User, month_bucket: str | None = "current") -> dict:
    """Team-lead dashboard payload: overall team KPIs, per-member performance cards (with
    phone for calling), a 30-day team collection trend and a member leaderboard. Shared by
    the lead's own /overview and the admin/manager/HO 'view this lead's team' endpoint.
    Scoped to one month by default (month_bucket=current); 'all' = lifetime."""
    from .cases import teamlead_case_filter
    from .mis import _period_for
    period = _period_for(month_bucket)
    member_ids = _teamlead_member_ids(db, lead)
    members = []
    if member_ids:
        members = db.query(models.User).filter(models.User.id.in_(member_ids),
                                               models.User.is_active == True).all()  # noqa: E712

    # The lead's cases are those the upload tagged with their name (not every case the
    # assigned FOS/caller happens to hold), minus escalated/removed.
    _cq = db.query(models.Case).filter(
        models.Case.escalated.isnot(True), models.Case.removed.isnot(True),
        teamlead_case_filter(lead))
    if period:
        _cq = _cq.filter(models.Case.period == period)
    cases = _cq.all()

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
            "recovery_pct": pct(rec, tenr), "today": _window(db, m, today_start),
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
    calls = db.query(models.CallLog).filter(models.CallLog.caller_id.in_(member_ids),
                                            ~models.CallLog.case_id.in_(esc)).all() if member_ids else []
    visits = db.query(models.Visit).filter(models.Visit.officer_id.in_(member_ids),
                                           ~models.Visit.case_id.in_(esc)).all() if member_ids else []
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
