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


def _hr_ids(db):
    return {i for (i,) in db.query(models.User.id).filter(
        models.User.role == "hr", models.User.is_active == True).all()}  # noqa: E712


def _ho_ids(db):
    return {i for (i,) in db.query(models.User.id).filter(
        models.User.role == "headoffice", models.User.is_active == True).all()}  # noqa: E712


def _direct_ids(db, user):
    """User ids this user may chat with DIRECTLY (no request needed). EVERYONE can reach HR.
    Within-team scoping still applies to FOS / callers / team leads / managers. Head Office is
    NOT here for lower tiers — reaching HO is request-based (see _approved_ho)."""
    role = user.role
    active = models.User.is_active == True  # noqa: E712
    ids = set()
    if role in ("admin", "headoffice", "backend", "hr"):
        ids = {i for (i,) in db.query(models.User.id).filter(active).all()}   # reach everyone
    elif role == "manager":
        ids = {i for (i,) in db.query(models.User.id).filter(active, models.User.branch == user.branch).all()}
    elif role == "teamlead":
        ids = set(_scope_user_ids(db, user))
    else:  # fos / telecaller → case partner(s) + their team lead
        col = models.Case.assigned_fos_id if role == "fos" else models.Case.assigned_caller_id
        other = models.Case.assigned_caller_id if role == "fos" else models.Case.assigned_fos_id
        ids = {i for (i,) in _scope(db.query(other), user).filter(col == user.id).distinct().all() if i}
        if user.team_lead_id:
            ids.add(user.team_lead_id)
    ids |= _hr_ids(db)          # EVERYONE can contact HR directly
    ids.discard(user.id)
    return ids


def _approved_ho(db, user):
    """HO members this user has an APPROVED chat request with."""
    return {r.to_id for r in db.query(models.ChatRequest).filter(
        models.ChatRequest.from_id == user.id, models.ChatRequest.status == "approved").all()}


def _pending_ho(db, user):
    return {r.to_id for r in db.query(models.ChatRequest).filter(
        models.ChatRequest.from_id == user.id, models.ChatRequest.status == "pending").all()}


def _thread_partners(db, user):
    """Everyone this user has exchanged a 1:1 message with — so a reply is ALWAYS possible even
    if the sender is outside the user's normal directory (fixes 'HO messaged me but I can't reply')."""
    ids = set()
    for a, b in db.query(models.ChatMessage.from_id, models.ChatMessage.to_id).filter(
            or_(models.ChatMessage.from_id == user.id, models.ChatMessage.to_id == user.id)).all():
        if a and a != user.id:
            ids.add(a)
        if b and b != user.id:
            ids.add(b)
    return ids


def _can_chat(db, user, target_id):
    if not target_id or target_id == user.id:
        return False
    return (target_id in _direct_ids(db, user)
            or target_id in _approved_ho(db, user)
            or target_id in _thread_partners(db, user))   # reply-back


@router.get("/chat/contacts")
def chat_contacts(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """WhatsApp-style chat list. Directory = team scope + HR (direct) + every Head Office member
    (locked until an approved request) + anyone who has already messaged you (reply-back). Each
    contact carries its last-message preview, time, unread count, and lock/pending state."""
    direct = _direct_ids(db, user)
    ho = _ho_ids(db)
    approved = _approved_ho(db, user)
    pending = _pending_ho(db, user)
    threads = _thread_partners(db, user)
    dir_ids = (direct | ho | threads)
    dir_ids.discard(user.id)
    users = {u.id: u for u in db.query(models.User).filter(
        models.User.id.in_(dir_ids or {-1})).all()}

    # last message + unread across ALL of my 1:1 threads (not just directory) → replies show up.
    convo = (db.query(models.ChatMessage)
             .filter(models.ChatMessage.to_id.isnot(None),
                     or_(models.ChatMessage.from_id == user.id, models.ChatMessage.to_id == user.id))
             .order_by(models.ChatMessage.created_at.desc()).all())
    last_by, unread_by = {}, {}
    for m in convo:
        partner = m.to_id if m.from_id == user.id else m.from_id
        if partner not in last_by:
            last_by[partner] = (m.body, m.created_at, m.from_id == user.id)
        if m.to_id == user.id and not m.read:
            unread_by[partner] = unread_by.get(partner, 0) + 1

    contacts = []
    for uid, u in users.items():
        allowed = (uid in direct) or (uid in approved) or (uid in threads)
        body, at, mine = last_by.get(uid, (None, None, False))
        contacts.append({
            "id": uid, "name": u.name, "role": u.role, "emp_code": u.emp_code,
            "locked": (u.role == "headoffice") and not allowed,   # needs an approved request
            "pending": uid in pending,
            "last": (("You: " if mine else "") + body) if body else None,
            "last_at": at.isoformat() if at else None,
            "unread": unread_by.get(uid, 0),
        })
    messaged = sorted([c for c in contacts if c["last_at"]], key=lambda x: x["last_at"], reverse=True)
    fresh = sorted([c for c in contacts if not c["last_at"]], key=lambda x: (x["name"] or "").lower())
    contacts = messaged + fresh

    om = (db.query(models.ChatMessage).filter(models.ChatMessage.to_id.is_(None))
          .order_by(models.ChatMessage.created_at.desc()).first())
    uname = {i: n for (i, n) in db.query(models.User.id, models.User.name).all()}
    office = {"last": (f"{uname.get(om.from_id, '—')}: {om.body}" if om else None),
              "last_at": om.created_at.isoformat() if om and om.created_at else None}
    roles = sorted({c["role"] for c in contacts if c.get("role")})
    # people this user may broadcast to (direct contacts + approved HO), for the broadcast composer
    can_broadcast = user.role in ("admin", "manager", "headoffice", "teamlead", "backend", "hr")
    return {"office": office, "contacts": contacts, "roles": roles,
            "pending_requests": len(pending), "can_broadcast": can_broadcast}


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
    now_read = [m for m in msgs if m.to_id == user.id and not m.read]
    for m in now_read:
        m.read = True
    if now_read:
        db.commit()
    uname = {i: n for (i, n) in db.query(models.User.id, models.User.name).all()}
    return {"messages": [{"id": m.id, "from_id": m.from_id, "from": uname.get(m.from_id, "—"),
                          "to_id": m.to_id, "mine": m.from_id == user.id, "body": m.body,
                          "kind": m.kind, "case_id": m.case_id, "read": bool(m.read),
                          "at": m.created_at.isoformat() if m.created_at else None} for m in msgs]}


@router.post("/chat/send")
def chat_send(body: dict = Body(...), db: Session = Depends(get_db),
              user: models.User = Depends(get_current_user)):
    text = (body.get("body") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message is empty")
    to_id = body.get("to_id")
    office = bool(body.get("office"))
    if not office:
        if not to_id:
            raise HTTPException(status_code=400, detail="No recipient")
        if not _can_chat(db, user, int(to_id)):
            raise HTTPException(status_code=403,
                                detail="You need Head Office to approve your chat request first.")
    m = models.ChatMessage(from_id=user.id, to_id=(None if office else int(to_id)),
                           case_id=body.get("case_id"), body=text[:2000], kind="chat")
    db.add(m)
    if office:
        for (uid,) in db.query(models.User.id).filter(models.User.role.in_(_OFFICE_ROLES),
                                                      models.User.is_active == True).all():  # noqa: E712
            if uid != user.id:
                push(db, uid, f"💬 {user.name} (office)", text[:120], ntype="chat", by_name=user.name)
    else:
        push(db, int(to_id), f"💬 {user.name}", text[:120], case_id=body.get("case_id"),
             ntype="chat", by_name=user.name)
    db.commit()
    return {"ok": True, "id": m.id}


# ---- Request-to-chat with Head Office ----

@router.post("/chat/request")
def chat_request(body: dict = Body(...), db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)):
    """A lower-tier user asks a Head Office member for permission to chat. HO must approve."""
    to_id = body.get("to_id")
    target = db.query(models.User).get(int(to_id)) if to_id else None
    if not target or target.role != "headoffice":
        raise HTTPException(status_code=400, detail="Chat requests are only for Head Office.")
    if target.id in _direct_ids(db, user) or target.id in _approved_ho(db, user):
        return {"ok": True, "already": True}
    if db.query(models.ChatRequest).filter(models.ChatRequest.from_id == user.id,
                                           models.ChatRequest.to_id == target.id,
                                           models.ChatRequest.status == "pending").first():
        return {"ok": True, "pending": True}
    r = models.ChatRequest(from_id=user.id, to_id=target.id, note=(body.get("note") or "")[:300])
    db.add(r)
    db.commit()
    push(db, target.id, f"🔓 Chat request — {user.name}",
         (body.get("note") or "Wants permission to chat with you."), ntype="chat_request", by_name=user.name)
    from .realtime import notify_user
    notify_user(target.id, {"type": "chat_request", "from": user.name})
    return {"ok": True}


@router.get("/chat/requests")
def chat_requests(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Head office / admin: pending chat requests awaiting my approval."""
    if user.role not in ("headoffice", "admin"):
        return {"requests": []}
    q = db.query(models.ChatRequest).filter(models.ChatRequest.status == "pending")
    if user.role == "headoffice":
        q = q.filter(models.ChatRequest.to_id == user.id)
    rows = q.order_by(models.ChatRequest.created_at.desc()).all()
    umap = {i: (n, c) for (i, n, c) in db.query(models.User.id, models.User.name, models.User.emp_code).all()}
    return {"requests": [{
        "id": r.id, "from_id": r.from_id,
        "from": umap.get(r.from_id, ("—", None))[0], "emp_code": umap.get(r.from_id, ("", None))[1],
        "note": r.note, "at": r.created_at.isoformat() if r.created_at else None} for r in rows]}


@router.post("/chat/request/{rid}/decide")
def chat_request_decide(rid: int, body: dict = Body(default={}), db: Session = Depends(get_db),
                        user: models.User = Depends(get_current_user)):
    r = db.query(models.ChatRequest).get(rid)
    if not r:
        raise HTTPException(status_code=404, detail="Request not found")
    if user.role not in ("headoffice", "admin") or (user.role == "headoffice" and r.to_id != user.id):
        raise HTTPException(status_code=403, detail="Not allowed")
    approve = bool(body.get("approve"))
    r.status = "approved" if approve else "declined"
    r.decided_at = datetime.now(timezone.utc)
    db.commit()
    push(db, r.from_id, "✅ Chat approved" if approve else "Chat request declined",
         (f"You can now message {user.name}." if approve else "Head office declined your chat request."),
         ntype="chat", by_name=user.name)
    from .realtime import notify_user
    notify_user(r.from_id, {"type": "chat_request_decided", "approved": approve})
    return {"ok": True}


# ---- Broadcast to selected people ----

@router.post("/chat/broadcast")
def chat_broadcast(body: dict = Body(...), db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)):
    """Send one message to several selected people at once. Each recipient gets it as a 1:1
    'broadcast' message + a pop-up on their working screen (via the realtime channel) + bell."""
    if user.role not in ("admin", "manager", "headoffice", "teamlead", "backend", "hr"):
        raise HTTPException(status_code=403, detail="You're not allowed to broadcast.")
    text = (body.get("body") or "").strip()
    ids = [int(x) for x in (body.get("to_ids") or []) if x]
    if not text:
        raise HTTPException(status_code=400, detail="Message is empty")
    if not ids:
        raise HTTPException(status_code=400, detail="Pick at least one recipient")
    from .realtime import notify_user
    sent = 0
    for uid in set(ids):
        if uid == user.id:
            continue
        db.add(models.ChatMessage(from_id=user.id, to_id=uid, body=text[:2000], kind="broadcast"))
        push(db, uid, f"📢 Broadcast — {user.name}", text[:120], ntype="broadcast", by_name=user.name)
        notify_user(uid, {"type": "broadcast", "from": user.name, "body": text[:500]})
        sent += 1
    db.commit()
    return {"ok": True, "sent": sent}


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
