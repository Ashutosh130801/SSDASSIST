"""Collaboration & ops features built on data we already hold:
  - /todo        : per-user daily work queue (PTPs due, broken PTPs, pending calls/visits,
                   paid-but-not-updated, callbacks due) — read only.
  - /monitor     : real-time ops feed + running counters for admin / manager / team lead.
  - /cases/liner : one-page allocation sheet (beat-sheet) of a FOS's accounts.
  - /chat        : in-app messaging (FOS <-> caller <-> office) + FOS 'request callback'.
"""
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy import or_, and_, func
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from .. import models
from .cases import _scope, _IST_TZ, _scope_user_ids
from .notifications import push

router = APIRouter(prefix="/api", tags=["collab"])

IST = _IST_TZ
PAY_DISP = ("PAYMENT", "PAID")


def _today():
    return datetime.now(IST).date()


def _d_ist(dt):
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST).date()


def _case_brief(c):
    return {"id": c.id, "customer": c.customer_name, "account": c.account_no or c.card_no,
            "bank": c.bank, "product": c.product, "phone": c.phone,
            "pending": float(c.pending_amount or 0), "disposition": c.disposition,
            "paid_status": c.paid_status, "follow_up": c.follow_up_date.isoformat() if c.follow_up_date else None}


def _paid(c):
    return (c.paid_status or "").upper() == "PAID"


# ============================================================ TO-DO / WORK QUEUE

def _todo_for(db: Session, u: models.User, viewer: models.User) -> dict:
    """Build one person's actionable queue from their live (current-period) cases."""
    today = _today()
    is_fos = u.role == "fos"
    q = _scope(db.query(models.Case), u) if u.id == viewer.id else db.query(models.Case).filter(
        models.Case.removed.isnot(True),
        (models.Case.assigned_fos_id == u.id) if is_fos else (models.Case.assigned_caller_id == u.id))
    cases = [c for c in q.all() if not c.escalated]

    ptp = [c for c in cases if (c.disposition or "").upper() == "PTP" and not _paid(c)]
    ptp_today = [c for c in ptp if c.follow_up_date == today]
    ptp_broken = [c for c in ptp if c.follow_up_date and c.follow_up_date < today]
    # money is in but the status wasn't flipped to PAID (needs confirming / DPR)
    paid_not_updated = [c for c in cases if float(c.received_amount or 0) > 0 and not _paid(c)]

    out = {"user": {"id": u.id, "name": u.name, "role": u.role},
           "ptp_today": [_case_brief(c) for c in ptp_today],
           "ptp_broken": [_case_brief(c) for c in ptp_broken],
           "paid_not_updated": [_case_brief(c) for c in paid_not_updated]}

    if is_fos:
        pending_visits = [c for c in cases if not c.visited and not _paid(c)]
        out["visits_pending"] = [_case_brief(c) for c in pending_visits]
    else:
        pending_calls = [c for c in cases if not c.last_contacted_at and not _paid(c)]
        out["calls_pending"] = [_case_brief(c) for c in pending_calls]

    # callbacks the customer/FOS asked this person to handle (unread callback pings TO them)
    cb = (db.query(models.ChatMessage)
          .filter(models.ChatMessage.kind == "callback", models.ChatMessage.to_id == u.id,
                  models.ChatMessage.read.is_(False))
          .order_by(models.ChatMessage.created_at.desc()).limit(50).all())
    out["callbacks"] = [{"id": m.id, "case_id": m.case_id, "body": m.body,
                         "from": (db.query(models.User.name).filter(models.User.id == m.from_id).scalar()),
                         "at": m.created_at.isoformat() if m.created_at else None} for m in cb]
    out["counts"] = {k: len(v) for k, v in out.items() if isinstance(v, list)}
    return out


@router.get("/todo/me")
def my_todo(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return _todo_for(db, user, user)


@router.get("/todo/user/{uid}")
def user_todo(uid: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    if user.role not in ("admin", "manager", "headoffice", "teamlead", "hr", "backend") and user.id != uid:
        raise HTTPException(status_code=403, detail="Not allowed")
    u = db.query(models.User).get(uid)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    return _todo_for(db, u, user)


# ============================================================ LIVE MONITOR

@router.get("/monitor/live")
def monitor_live(db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)):
    """War-room feed + running counters for today, scoped to what the viewer oversees."""
    if user.role not in ("admin", "manager", "headoffice", "teamlead", "backend"):
        raise HTTPException(status_code=403, detail="Not allowed")
    now = datetime.now(timezone.utc)
    day_start = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)

    # which staff ids are in scope (None = everyone, for admin/HO/backend)
    ids = None
    if user.role == "manager":
        ids = [i for (i,) in db.query(models.User.id).filter(models.User.branch == user.branch).all()]
    elif user.role == "teamlead":
        from .cases import _scope_user_ids
        ids = _scope_user_ids(db, user)

    def _f(q, col):
        return q if ids is None else q.filter(col.in_(ids))

    calls_q = _f(db.query(models.CallLog).filter(models.CallLog.created_at >= day_start), models.CallLog.caller_id)
    visits_q = _f(db.query(models.Visit).filter(models.Visit.created_at >= day_start), models.Visit.officer_id)
    calls = calls_q.order_by(models.CallLog.created_at.desc()).limit(200).all()
    visits = visits_q.order_by(models.Visit.created_at.desc()).limit(200).all()

    uname = {i: n for (i, n) in db.query(models.User.id, models.User.name).all()}
    feed = []
    for cl in calls:
        amt = float(cl.ptp_amount or 0)
        feed.append({"at": cl.created_at.isoformat() if cl.created_at else None, "type": "call",
                     "who": uname.get(cl.caller_id, "—"), "detail": cl.disposition or "call",
                     "amount": amt if (cl.disposition or "") in PAY_DISP else 0, "case_id": cl.case_id})
    for v in visits:
        feed.append({"at": v.created_at.isoformat() if v.created_at else None, "type": "visit",
                     "who": uname.get(v.officer_id, "—"), "detail": v.disposition or "visit",
                     "amount": float(v.amount_collected or 0), "case_id": v.case_id})
    feed.sort(key=lambda x: x["at"] or "", reverse=True)
    feed = feed[:120]

    coll_calls = sum(float(c.ptp_amount or 0) for c in calls if (c.disposition or "") in PAY_DISP)
    coll_visits = sum(float(v.amount_collected or 0) for v in visits if float(v.amount_collected or 0) > 0)
    paid_count = sum(1 for c in calls if (c.disposition or "") in PAY_DISP) + \
                 sum(1 for v in visits if float(v.amount_collected or 0) > 0)

    # who's online now (in scope)
    online = db.query(func.count(models.User.id)).filter(
        models.User.last_seen.isnot(None),
        models.User.last_seen >= now - timedelta(seconds=75))
    if ids is not None:
        online = online.filter(models.User.id.in_(ids))
    online_now = online.scalar() or 0

    return {"counters": {"calls": len(calls), "visits": len(visits), "paid_count": paid_count,
                         "collected": round(coll_calls + coll_visits, 2), "online_now": int(online_now)},
            "feed": feed, "server_time": now.isoformat()}


# ============================================================ PRINTABLE LINER

@router.get("/liner")
def liner(fos_id: int | None = None, db: Session = Depends(get_db),
          user: models.User = Depends(get_current_user)):
    """One-page beat-sheet: a FOS's assigned accounts with the field essentials."""
    target_id = fos_id or user.id
    if target_id != user.id and user.role not in ("admin", "manager", "headoffice", "teamlead", "backend"):
        raise HTTPException(status_code=403, detail="Not allowed")
    tgt = db.query(models.User).get(target_id)
    if not tgt:
        raise HTTPException(status_code=404, detail="Field officer not found")
    q = _scope(db.query(models.Case), user).filter(models.Case.assigned_fos_id == target_id) \
        if user.id != target_id else _scope(db.query(models.Case), user).filter(models.Case.assigned_fos_id == user.id)
    rows = [c for c in q.all() if not c.escalated and not _paid(c)]
    rows.sort(key=lambda c: (c.bank or "", c.bucket or "", -(float(c.pending_amount or 0))))
    out = [{"account": c.account_no or c.card_no, "customer": c.customer_name,
            "phone": c.phone or c.alt_phone, "address": c.address_clean or c.address,
            "bank": c.bank, "product": c.product, "bucket": c.bucket,
            "pending": float(c.pending_amount or 0), "pincode": c.pincode} for c in rows]
    return {"fos": {"id": tgt.id, "name": tgt.name, "emp_code": tgt.emp_code, "branch": tgt.branch},
            "date": _today().isoformat(), "count": len(out), "cases": out}


# ============================================================ CHAT + CALLBACK

_OFFICE_ROLES = ("admin", "manager", "headoffice", "teamlead", "backend", "hr")


def _contacts_for(db, user):
    """People this user can message. Scoped by role so the directory matches who they oversee:
      • admin / head office / back office / HR  → everyone (whole org)
      • manager                                 → everyone in their branch (all roles)
      • team lead                               → their team (callers + FOS on their cases)
      • FOS / caller                            → their case partner(s) + their team lead
    Everyone can also reach the shared 'Office' desk."""
    role = user.role
    active = models.User.is_active == True  # noqa: E712
    people = {}

    if role in ("admin", "headoffice", "backend", "hr"):
        # Full directory — every active staff member.
        for u in db.query(models.User).filter(active).all():
            people[u.id] = u

    elif role == "manager":
        # Everyone in the manager's branch, regardless of role (callers, FOS, team leads…).
        for u in db.query(models.User).filter(active, models.User.branch == user.branch).all():
            people[u.id] = u

    elif role == "teamlead":
        # The team lead's own team — callers + FOS assigned to cases carrying their name.
        ids = _scope_user_ids(db, user)
        for u in db.query(models.User).filter(models.User.id.in_(ids or [-1]), active).all():
            people[u.id] = u

    else:  # fos / telecaller
        col = models.Case.assigned_fos_id if role == "fos" else models.Case.assigned_caller_id
        other = models.Case.assigned_caller_id if role == "fos" else models.Case.assigned_fos_id
        ids = [i for (i,) in _scope(db.query(other), user).filter(col == user.id).distinct().all() if i]
        for u in db.query(models.User).filter(models.User.id.in_(ids or [-1]), active).all():
            people[u.id] = u
        if user.team_lead_id:  # their own team lead, even if not sharing a live case right now
            tl = db.query(models.User).get(user.team_lead_id)
            if tl and tl.is_active:
                people[tl.id] = tl

    out = [{"id": u.id, "name": u.name, "role": u.role, "emp_code": u.emp_code}
           for u in people.values() if u.id != user.id]
    out.sort(key=lambda x: (x["role"] or "", x["name"] or ""))
    return out


@router.get("/chat/contacts")
def chat_contacts(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """WhatsApp-style chat list: every person in scope + the shared Office desk, each carrying
    its last-message preview, time, and unread count. Threads with recent activity float to the
    top; the rest follow alphabetically so a fresh chat can still be started."""
    contacts = _contacts_for(db, user)
    ids = [c["id"] for c in contacts]

    # All 1:1 messages between me and any scoped contact, newest first.
    convo = (db.query(models.ChatMessage)
             .filter(or_(
                 and_(models.ChatMessage.from_id == user.id, models.ChatMessage.to_id.in_(ids or [-1])),
                 and_(models.ChatMessage.from_id.in_(ids or [-1]), models.ChatMessage.to_id == user.id)))
             .order_by(models.ChatMessage.created_at.desc()).all())
    last_by = {}      # partner_id -> (body, at, mine)
    unread_by = {}    # partner_id -> count of their unread msgs to me
    for m in convo:
        partner = m.to_id if m.from_id == user.id else m.from_id
        if partner not in last_by:
            last_by[partner] = (m.body, m.created_at, m.from_id == user.id)
        if m.to_id == user.id and not m.read:
            unread_by[partner] = unread_by.get(partner, 0) + 1

    for c in contacts:
        body, at, mine = last_by.get(c["id"], (None, None, False))
        c["last"] = (("You: " if mine else "") + body) if body else None
        c["last_at"] = at.isoformat() if at else None
        c["unread"] = unread_by.get(c["id"], 0)
    # Recent conversations first (newest at top); never-messaged contacts after, alphabetically.
    messaged = sorted([c for c in contacts if c["last_at"]], key=lambda x: x["last_at"], reverse=True)
    fresh = sorted([c for c in contacts if not c["last_at"]], key=lambda x: (x["name"] or "").lower())
    contacts = messaged + fresh

    # Office desk summary (shared broadcast channel — no per-user read state).
    om = (db.query(models.ChatMessage).filter(models.ChatMessage.to_id.is_(None))
          .order_by(models.ChatMessage.created_at.desc()).first())
    uname = {i: n for (i, n) in db.query(models.User.id, models.User.name).all()}
    office = {"last": (f"{uname.get(om.from_id, '—')}: {om.body}" if om else None),
              "last_at": om.created_at.isoformat() if om and om.created_at else None}

    roles = sorted({c["role"] for c in contacts if c.get("role")})
    return {"office": office, "contacts": contacts, "roles": roles}


@router.get("/chat/thread")
def chat_thread(with_id: int | None = None, office: bool = False,
                db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Messages between me and one person, or the shared office desk (to_id NULL)."""
    q = db.query(models.ChatMessage)
    if office:
        q = q.filter(models.ChatMessage.to_id.is_(None))
    elif with_id:
        q = q.filter(or_(
            and_(models.ChatMessage.from_id == user.id, models.ChatMessage.to_id == with_id),
            and_(models.ChatMessage.from_id == with_id, models.ChatMessage.to_id == user.id)))
    else:
        raise HTTPException(status_code=400, detail="with_id or office required")
    msgs = q.order_by(models.ChatMessage.created_at.asc()).limit(300).all()
    # mark messages TO me as read
    now_read = [m for m in msgs if m.to_id == user.id and not m.read]
    for m in now_read:
        m.read = True
    if now_read:
        db.commit()
    uname = {i: n for (i, n) in db.query(models.User.id, models.User.name).all()}
    return {"messages": [{"id": m.id, "from_id": m.from_id, "from": uname.get(m.from_id, "—"),
                          "to_id": m.to_id, "mine": m.from_id == user.id, "body": m.body,
                          "kind": m.kind, "case_id": m.case_id,
                          "at": m.created_at.isoformat() if m.created_at else None} for m in msgs]}


@router.post("/chat/send")
def chat_send(body: dict = Body(...), db: Session = Depends(get_db),
              user: models.User = Depends(get_current_user)):
    text = (body.get("body") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message is empty")
    to_id = body.get("to_id")
    office = bool(body.get("office"))
    m = models.ChatMessage(from_id=user.id, to_id=(None if office else int(to_id) if to_id else None),
                           case_id=body.get("case_id"), body=text[:2000], kind="chat")
    db.add(m)
    # ping the recipient's notification bell (office message → all office roles)
    if office:
        for (uid,) in db.query(models.User.id).filter(models.User.role.in_(_OFFICE_ROLES),
                                                      models.User.is_active == True).all():  # noqa: E712
            if uid != user.id:
                push(db, uid, f"💬 {user.name} (office)", text[:120], ntype="chat", by_name=user.name)
    elif to_id:
        push(db, int(to_id), f"💬 {user.name}", text[:120], case_id=body.get("case_id"),
             ntype="chat", by_name=user.name)
    db.commit()
    return {"ok": True, "id": m.id}


@router.post("/chat/callback")
def chat_callback(body: dict = Body(...), db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    """A FOS taps 'Request callback' on a case → pings the assigned telecaller in real time."""
    case_id = body.get("case_id")
    case = db.query(models.Case).get(case_id) if case_id else None
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    target = case.assigned_caller_id
    if not target:
        raise HTTPException(status_code=400, detail="No telecaller is assigned to this case yet.")
    note = (body.get("note") or "").strip()
    who = case.customer_name or case.account_no or f"case #{case.id}"
    text = f"📞 Callback requested on {who}" + (f" — {note}" if note else "")
    db.add(models.ChatMessage(from_id=user.id, to_id=target, case_id=case.id, body=text, kind="callback"))
    push(db, target, "📞 Callback requested", f"{user.name}: {who}" + (f" — {note}" if note else ""),
         case_id=case.id, ntype="callback", by_name=user.name)
    db.commit()
    return {"ok": True}


@router.get("/chat/unread")
def chat_unread(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    n = db.query(func.count(models.ChatMessage.id)).filter(
        models.ChatMessage.to_id == user.id, models.ChatMessage.read.is_(False)).scalar() or 0
    return {"unread": int(n)}
