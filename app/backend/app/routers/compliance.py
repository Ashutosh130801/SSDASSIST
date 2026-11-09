"""🛡️ Compliance guardrails add-on.

• Contact hours (RBI fair-practice: no recovery calls/visits outside 08:00–19:00 by default).
• Attempt caps per customer (calls / day, visits / week).
• Agent certification register (e.g. IIBF DRA) with expiry; optionally block uncertified agents.
• DPDP Act data requests (access / correction / erasure / grievance) with due dates.
• Data retention: erase personal details of old, closed cases.

Dialling (click-to-call) is BLOCKED when a rule is broken. Calls / visits that are *logged* outside
the rules are never rejected (the record must exist) but are flagged as violations for review.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import audit, models
from .. import services as svc
from ..addons_common import IST, LEADS, OFFICE, case_or_404, need, now_ist
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/api/compliance", tags=["compliance"])
KEY = "compliance"
REQ_KINDS = ("access", "correction", "erasure", "grievance")
PII_FIELDS = ("phone", "alt_phone", "new_phone", "address", "address2", "address3", "new_address", "address_clean")


def _hm(s, dflt):
    try:
        h, m = str(s or dflt).split(":")[:2]
        return time(int(h), int(m))
    except Exception:
        h, m = dflt.split(":")
        return time(int(h), int(m))


def _day_bounds_utc(d: date):
    s = datetime.combine(d, time.min, IST)
    return s.astimezone(timezone.utc), (s + timedelta(days=1)).astimezone(timezone.utc)


def _cert_ok(db, user_id: int, on: date) -> bool:
    return db.query(models.AgentCertification).filter(models.AgentCertification.user_id == user_id,
                                                      models.AgentCertification.valid_until >= on).first() is not None


def evaluate(db, user, case, kind: str, at: datetime | None = None) -> list[str]:
    """Reasons this contact breaks a rule ([] = fine). kind: call / visit."""
    if not svc.is_on(db, KEY):
        return []
    c = svc.settings_of(db, KEY)
    at = (at or now_ist()).astimezone(IST)
    out = []
    if c.get("enforce_hours", True):
        a, b = _hm(c.get("hours_from"), "08:00"), _hm(c.get("hours_to"), "19:00")
        if not (a <= at.time() < b):
            out.append(f"Outside allowed contact hours ({a:%H:%M}–{b:%H:%M})")
    if kind == "call":
        cap = int(c.get("max_calls_per_day") or 0)
        if cap:
            s, e = _day_bounds_utc(at.date())
            n = db.query(models.CallLog).filter(models.CallLog.case_id == case.id, models.CallLog.created_at >= s,
                                                models.CallLog.created_at < e,
                                                models.CallLog.disposition.notin_(("PAYMENT", "PAID"))).count()
            if n >= cap:
                out.append(f"Already {n} call attempts today (limit {cap})")
    if kind == "visit":
        cap = int(c.get("max_visits_per_week") or 0)
        if cap:
            s, _ = _day_bounds_utc(at.date() - timedelta(days=6))
            n = db.query(models.Visit).filter(models.Visit.case_id == case.id, models.Visit.created_at >= s).count()
            if n >= cap:
                out.append(f"Already {n} visits in the last 7 days (limit {cap})")
    if c.get("block_uncertified") and user is not None and user.role in ("fos", "telecaller"):
        if not _cert_ok(db, user.id, at.date()):
            out.append("Agent has no valid recovery-agent certificate")
    return out


def guard_dial(db, user, case):
    """Called before click-to-call: blocks the dial if any rule is broken."""
    why = evaluate(db, user, case, "call")
    if why:
        audit.record(db, user, "compliance.blocked", case, detail="Dial blocked: " + "; ".join(why))
        db.commit()
        raise HTTPException(403, "Compliance: " + "; ".join(why))


def flag(db, user, case, kind: str, at: datetime | None = None):
    """Called after a call / visit is logged: records a violation (never blocks the record)."""
    try:
        why = evaluate(db, user, case, kind, at)
        # the just-logged record itself counts in the cap — only flag when strictly over
        why = [w for w in why if not w.startswith("Already") or _over(w)]
        if why:
            audit.record(db, user, "compliance.violation", case, detail=f"{kind.title()} logged: " + "; ".join(why))
    except Exception:
        pass


def _over(w: str) -> bool:
    try:
        n = int(w.split()[1]); cap = int(w.rsplit("limit ", 1)[1].rstrip(")"))
        return n > cap
    except Exception:
        return False


# ───────────────────────── endpoints ─────────────────────────
@router.get("/check/{case_id}")
def check(case_id: int, kind: str = "call", db: Session = Depends(get_db), user=Depends(get_current_user)):
    case = case_or_404(db, user, case_id)
    why = evaluate(db, user, case, "visit" if kind == "visit" else "call")
    return {"ok": not why, "reasons": why}


@router.get("/summary")
def summary(days: int = 30, db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, LEADS + ("hr",), "compliance reports")
    since = datetime.now(timezone.utc) - timedelta(days=max(1, min(days, 365)))
    q = db.query(models.AuditLog).filter(models.AuditLog.action.in_(("compliance.violation", "compliance.blocked")),
                                         models.AuditLog.at >= since)
    if user.role in ("manager", "teamlead"):
        from ..ai_tools import visible_staff
        ids = visible_staff(db, user)
        if ids is not None:
            q = q.filter(models.AuditLog.actor_id.in_(ids or [-1]))
    rows = q.order_by(models.AuditLog.at.desc()).limit(500).all()
    by_agent = {}
    for r in rows:
        k = r.actor_name or "—"
        by_agent.setdefault(k, {"agent": k, "violations": 0, "blocked": 0})
        by_agent[k]["blocked" if r.action == "compliance.blocked" else "violations"] += 1
    today = now_ist().date()
    certs = db.query(models.AgentCertification).all()
    staff = db.query(models.User).filter(models.User.is_active.is_(True), models.User.role.in_(("fos", "telecaller"))).all()
    valid = {c.user_id for c in certs if c.valid_until and c.valid_until >= today}
    soon = {c.user_id for c in certs if c.valid_until and today <= c.valid_until <= today + timedelta(days=30)}
    reqs = db.query(models.DataRequest).filter(models.DataRequest.status == "open").all()
    return {
        "events": [{"at": r.at, "agent": r.actor_name, "action": r.action, "case_id": r.case_id, "detail": r.detail} for r in rows[:200]],
        "by_agent": sorted(by_agent.values(), key=lambda x: -(x["violations"] + x["blocked"])),
        "certs": {"agents": len(staff), "certified": len([u for u in staff if u.id in valid]),
                  "expiring_30d": len([u for u in staff if u.id in soon])},
        "open_requests": len(reqs), "overdue_requests": len([r for r in reqs if r.due_date and r.due_date < today]),
        "settings": svc.settings_of(db, KEY),
    }


# ---- certifications
@router.get("/certifications")
def certs(db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, OFFICE + ("hr",), "certifications")
    today = now_ist().date()
    users = db.query(models.User).filter(models.User.is_active.is_(True), models.User.role.in_(("fos", "telecaller", "teamlead"))).all()
    by = {}
    for c in db.query(models.AgentCertification).all():
        by.setdefault(c.user_id, []).append(c)
    out = []
    for u in sorted(users, key=lambda x: (x.role, x.name or "")):
        cs = sorted(by.get(u.id, []), key=lambda c: c.valid_until or date.min, reverse=True)
        best = cs[0] if cs else None
        st = "missing" if not best else ("expired" if not best.valid_until or best.valid_until < today else
                                         "expiring" if best.valid_until <= today + timedelta(days=30) else "valid")
        out.append({"user_id": u.id, "name": u.name, "emp_code": u.emp_code, "role": u.role, "branch": u.branch, "status": st,
                    "certs": [{"id": c.id, "name": c.name, "number": c.number, "valid_until": c.valid_until} for c in cs]})
    return out


@router.post("/certifications")
def add_cert(body: dict = Body(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, OFFICE + ("hr",), "certifications")
    try:
        vu = date.fromisoformat(str(body.get("valid_until")))
    except ValueError:
        raise HTTPException(400, "Valid-until date is required (YYYY-MM-DD)")
    u = db.get(models.User, int(body.get("user_id") or 0))
    if not u:
        raise HTTPException(404, "Employee not found")
    c = models.AgentCertification(user_id=u.id, name=(body.get("name") or "IIBF Debt Recovery Agent")[:120],
                                  number=(body.get("number") or "")[:60], valid_until=vu)
    db.add(c)
    audit.record(db, user, "compliance.cert_add", entity_type="user", target_user_id=u.id, detail=f"{c.name} valid till {vu}")
    db.commit()
    return {"id": c.id}


@router.delete("/certifications/{cid}")
def del_cert(cid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, OFFICE + ("hr",), "certifications")
    c = db.get(models.AgentCertification, cid)
    if not c:
        raise HTTPException(404, "Not found")
    audit.record(db, user, "compliance.cert_delete", entity_type="user", target_user_id=c.user_id, detail=c.name)
    db.delete(c); db.commit()
    return {"ok": True}


# ---- DPDP data requests
@router.get("/requests")
def requests(status: str = "open", db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, OFFICE, "data requests")
    q = db.query(models.DataRequest)
    if status != "all":
        q = q.filter(models.DataRequest.status == status)
    rows = q.order_by(models.DataRequest.created_at.desc()).limit(500).all()
    names = {c.id: c.customer_name for c in db.query(models.Case).filter(models.Case.id.in_([r.case_id for r in rows if r.case_id] or [-1]))}
    return [{"id": r.id, "case_id": r.case_id, "customer": names.get(r.case_id), "kind": r.kind, "requester": r.requester,
             "contact": r.contact, "details": r.details, "status": r.status, "resolution": r.resolution, "due_date": r.due_date,
             "created_at": r.created_at, "closed_at": r.closed_at} for r in rows]


@router.post("/requests")
def new_request(body: dict = Body(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, OFFICE, "data requests")
    kind = body.get("kind")
    if kind not in REQ_KINDS:
        raise HTTPException(400, "Kind must be access, correction, erasure or grievance")
    if not (body.get("requester") or "").strip():
        raise HTTPException(400, "Requester name is required")
    cid = body.get("case_id")
    if cid:
        case_or_404(db, user, int(cid), all_periods=True)
    r = models.DataRequest(case_id=int(cid) if cid else None, kind=kind, requester=body["requester"][:160],
                           contact=(body.get("contact") or "")[:80], details=(body.get("details") or "")[:4000],
                           due_date=now_ist().date() + timedelta(days=int(body.get("due_days") or 30)), created_by=user.id)
    db.add(r); db.flush()
    audit.record(db, user, "compliance.request", entity_type="settings", detail=f"#{r.id} {kind} by {r.requester}")
    db.commit()
    return {"id": r.id}


def _erase(case):
    for f in PII_FIELDS:
        if getattr(case, f, None):
            setattr(case, f, None if f != "phone" else "")
    case.customer_name = "[erased]"
    for f in ("latitude", "longitude", "geo_lat", "geo_lng", "latitude2", "longitude2", "latitude3", "longitude3"):
        setattr(case, f, None)


@router.post("/requests/{rid}/close")
def close_request(rid: int, body: dict = Body(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, OFFICE, "data requests")
    r = db.get(models.DataRequest, rid)
    if not r or r.status != "open":
        raise HTTPException(404, "Open request not found")
    st = body.get("status") or "done"
    if st not in ("done", "rejected"):
        raise HTTPException(400, "Status must be done or rejected")
    r.status, r.resolution, r.closed_by, r.closed_at = st, (body.get("resolution") or "")[:4000], user.id, datetime.now(timezone.utc)
    if st == "done" and r.kind == "erasure" and r.case_id and body.get("erase"):
        if user.role != "admin":
            raise HTTPException(403, "Only Admin can erase customer data")
        if (body.get("confirm") or "").strip().upper() != "ERASE":
            raise HTTPException(400, "Type ERASE to confirm")
        case = db.get(models.Case, r.case_id)
        if case:
            if (case.paid_status or "").upper() != "PAID" and not case.closed:
                raise HTTPException(400, "This account is still open — the lender's record must be kept until it closes.")
            _erase(case)
            audit.record(db, user, "compliance.erase", case, detail=f"Personal data erased (request #{r.id})")
    audit.record(db, user, "compliance.request_close", entity_type="settings", detail=f"#{r.id} {st}")
    db.commit()
    return {"ok": True}


# ---- retention
def _retention_query(db, months: int):
    cutoff = now_ist().date().replace(day=1)
    y, m = cutoff.year, cutoff.month - months
    while m <= 0:
        y, m = y - 1, m + 12
    per = f"{y:04d}-{m:02d}"
    return db.query(models.Case).filter(models.Case.period.isnot(None), models.Case.period < per,
                                         models.Case.customer_name != "[erased]"), per


@router.get("/retention")
def retention_preview(db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, ("admin",), "data retention")
    months = int(svc.settings_of(db, KEY).get("retention_months") or 0)
    if not months:
        return {"months": 0, "count": 0, "before": None}
    q, per = _retention_query(db, months)
    return {"months": months, "count": q.count(), "before": per}


@router.post("/retention/purge")
def retention_purge(body: dict = Body(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, ("admin",), "data retention")
    months = int(svc.settings_of(db, KEY).get("retention_months") or 0)
    if not months:
        raise HTTPException(400, "Set 'Keep closed-case personal data for (months)' in ⚙️ Services first")
    if (body.get("confirm") or "").strip().upper() != "ERASE":
        raise HTTPException(400, "Type ERASE to confirm")
    q, per = _retention_query(db, months)
    n = 0
    for c in q.limit(20000).all():
        _erase(c); n += 1
    audit.record(db, user, "compliance.retention", entity_type="settings", detail=f"Erased personal data of {n} cases from before {per}")
    db.commit()
    return {"erased": n, "before": per}
