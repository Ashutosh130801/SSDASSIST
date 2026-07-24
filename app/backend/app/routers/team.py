"""Branch-oriented team management (web admin/manager).

No Branch table: a "branch" is the set of users/cases sharing a branch name, and its
manager is the manager-role user on that branch. Admin creating a branch = creating its
manager. Also serves per-staff performance windows (daily / weekly / monthly / overall).
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user, require_roles
from ..security import hash_password

router = APIRouter(prefix="/api/team", tags=["team"])

IST = timezone(timedelta(hours=5, minutes=30))


def _d(x) -> float:
    return float(x or 0)


@router.get("/branches")
def branches(db: Session = Depends(get_db), user: models.User = Depends(require_roles("admin", "manager"))):
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

    rows = (db.query(models.Case.branch, func.count(models.Case.id),
                     func.coalesce(func.sum(models.Case.received_amount), 0),
                     func.coalesce(func.sum(models.Case.pending_amount), 0))
            .group_by(models.Case.branch).all())
    cstat = {(b or "Unassigned"): (c, _d(r), _d(p)) for b, c, r, p in rows}

    out = []
    for b, d in cards.items():
        c, r, p = cstat.get(b, (0, 0.0, 0.0))
        d.update(cases=c, received=r, pending=p)
        out.append(d)
    out.sort(key=lambda x: x["branch"])
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


def _window(db: Session, u: models.User, start):
    if u.role == "fos":
        q = db.query(models.Visit).filter(models.Visit.officer_id == u.id)
        if start:
            q = q.filter(models.Visit.created_at >= start)
        items = q.all()
        return {"label": "visits", "count": len(items),
                "collected": _d(sum(_d(v.amount_collected) for v in items))}
    # telecaller (and any calling role)
    q = db.query(models.CallLog).filter(models.CallLog.caller_id == u.id)
    if start:
        q = q.filter(models.CallLog.created_at >= start)
    calls = q.all()
    ptp = sum(1 for c in calls if (c.disposition or "") in ("PTP", "RTP"))
    collected = _d(sum(_d(c.ptp_amount) for c in calls if (c.disposition or "") == "PAID"))
    return {"label": "calls", "count": len(calls), "ptp": ptp, "collected": collected}


@router.get("/user/{uid}/performance")
def performance(uid: int, db: Session = Depends(get_db),
                actor: models.User = Depends(get_current_user)):
    """Daily / weekly / monthly / overall performance for a field officer or telecaller.
    Visible to the person themselves, their branch manager, and admins."""
    u = db.query(models.User).filter(models.User.id == uid).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    if actor.role == "manager" and u.branch != actor.branch:
        raise HTTPException(status_code=403, detail="Not in your branch")
    if actor.role in ("fos", "telecaller", "backend") and actor.id != u.id:
        raise HTTPException(status_code=403, detail="Not allowed")

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
def employee_dashboard(uid: int, db: Session = Depends(get_db),
                       actor: models.User = Depends(get_current_user)):
    """A field officer's / telecaller's full personal analytics — assigned cases, collections,
    trend, dispositions, PTP, activity and recent cases. Visible to self, branch manager, admin."""
    u = db.query(models.User).filter(models.User.id == uid).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    if actor.role == "manager" and u.branch != actor.branch:
        raise HTTPException(status_code=403, detail="Not in your branch")
    if actor.role in ("fos", "telecaller", "backend") and actor.id != u.id:
        raise HTTPException(status_code=403, detail="Not allowed")

    is_caller = u.role == "telecaller"
    cq = db.query(models.Case)
    cq = cq.filter(models.Case.assigned_caller_id == uid) if is_caller else cq.filter(models.Case.assigned_fos_id == uid)
    cases = cq.all()
    calls = db.query(models.CallLog).filter(models.CallLog.caller_id == uid).all()
    visits = db.query(models.Visit).filter(models.Visit.officer_id == uid).all()

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

    pay_events = [(d_ist(cl.created_at), _d(cl.ptp_amount)) for cl in calls if (cl.disposition or "") == "PAYMENT"]
    pay_events += [(d_ist(v.created_at), _d(v.amount_collected)) for v in visits if _d(v.amount_collected) > 0]
    cash = round(sum(a for d, a in pay_events), 2)

    trend = []
    for i in range(29, -1, -1):
        dd = today_d - timedelta(days=i)
        trend.append({"date": dd.isoformat(), "collected": round(sum(a for d, a in pay_events if d == dd), 2)})

    disp: dict[str, int] = {}
    for c in cases:
        if c.disposition:
            disp[c.disposition] = disp.get(c.disposition, 0) + 1
    dispositions = sorted(({"label": k, "count": v} for k, v in disp.items()), key=lambda x: x["count"], reverse=True)

    ptp_cases = [c for c in cases if (c.disposition or "").upper() in ("PTP", "RTP")]
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
                 "cash_collected": cash},
        "performance": {"daily": _window(db, u, datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)),
                        "weekly": _window(db, u, datetime.now(timezone.utc) - timedelta(days=7)),
                        "monthly": _window(db, u, datetime.now(timezone.utc) - timedelta(days=30)),
                        "overall": _window(db, u, None)},
        "trend": trend,
        "dispositions": dispositions,
        "ptp": {"total": len(ptp_cases), "kept": ptp_kept, "broken": ptp_broken, "kept_pct": pct(ptp_kept, len(ptp_cases))},
        "field": field,
        "recent_cases": recent,
    }
