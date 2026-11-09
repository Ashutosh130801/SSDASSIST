"""📣 Digital outreach journeys add-on.

A journey = filters (bank / product / bucket / branch) + a trigger + steps:
  trigger "close"  : step offset = days BEFORE the case's close date (7, 3, 1 …)
  trigger "ptp"    : step offset = days relative to the latest PTP date (-1 = day before, 0 = on the day, 1 = day after)
  trigger "monthly": step offset = day of the month (e.g. 5 and 20)
Each step sends one SMS or WhatsApp text with placeholders:
  {name} {amount} {bank} {account_last4} {ptp_date} {ptp_amount} {close_date} {pay_link} {company}
Running a journey creates one message per (journey, case, step) at most once, respects the per-customer daily cap
and the compliance contact hours. Without a connected provider the messages are "manual": the team sends them
with one click (WhatsApp) or exports the list.
"""
from __future__ import annotations

import csv
import io
import secrets
from datetime import date, datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import audit, models
from .. import services as svc
from ..addons_common import IST, OFFICE, D, need, now_ist, outstanding
from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/api/outreach", tags=["outreach"])
KEY = "outreach"
TRIGGERS = ("close", "ptp", "monthly")
CHANNELS = ("sms", "whatsapp")
_transport = None    # tests: fn(channel, to, text, conf) -> (ok, error)


def _validate(body: dict) -> dict:
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Journey name is required")
    trig = body.get("trigger") or "close"
    if trig not in TRIGGERS:
        raise HTTPException(400, "Trigger must be close, ptp or monthly")
    steps = []
    for i, st in enumerate(body.get("steps") or []):
        try:
            off = int(st.get("offset"))
        except (TypeError, ValueError):
            raise HTTPException(400, f"Step {i + 1}: offset must be a whole number")
        if trig == "monthly" and not 1 <= off <= 28:
            raise HTTPException(400, f"Step {i + 1}: day of month must be 1–28")
        if st.get("channel") not in CHANNELS:
            raise HTTPException(400, f"Step {i + 1}: channel must be sms or whatsapp")
        txt = (st.get("text") or "").strip()
        if not txt:
            raise HTTPException(400, f"Step {i + 1}: message text is required")
        steps.append({"offset": off, "channel": st["channel"], "text": txt[:900]})
    if not steps:
        raise HTTPException(400, "Add at least one step")
    f = body.get("filters") or {}
    filters = {k: str(f.get(k) or "").strip() for k in ("bank", "product", "bucket", "branch") if f.get(k)}
    return {"name": name[:120], "trigger": trig, "steps": steps, "filters": filters, "active": bool(body.get("active", True))}


def _j(j: models.OutreachJourney, db=None):
    out = {"id": j.id, "name": j.name, "trigger": j.trigger, "filters": j.filters or {}, "steps": j.steps or [], "active": j.active}
    if db is not None:
        rows = db.query(models.OutreachMessage.status, func.count()).filter(models.OutreachMessage.journey_id == j.id) \
            .group_by(models.OutreachMessage.status).all()
        out["stats"] = {s: n for s, n in rows}
    return out


@router.get("/journeys")
def journeys(db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, OFFICE, "outreach")
    return [_j(j, db) for j in db.query(models.OutreachJourney).order_by(models.OutreachJourney.id).all()]


@router.post("/journeys")
def create_journey(body: dict = Body(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, OFFICE, "outreach")
    v = _validate(body)
    j = models.OutreachJourney(**v, created_by=user.id)
    db.add(j); db.flush()
    audit.record(db, user, "outreach.journey", entity_type="settings", detail=f"Created journey {j.name}")
    db.commit()
    return _j(j)


@router.put("/journeys/{jid}")
def update_journey(jid: int, body: dict = Body(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, OFFICE, "outreach")
    j = db.get(models.OutreachJourney, jid)
    if not j:
        raise HTTPException(404, "Journey not found")
    for k, v in _validate(body).items():
        setattr(j, k, v)
    audit.record(db, user, "outreach.journey", entity_type="settings", detail=f"Updated journey {j.name}")
    db.commit()
    return _j(j)


@router.delete("/journeys/{jid}")
def delete_journey(jid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, OFFICE, "outreach")
    j = db.get(models.OutreachJourney, jid)
    if not j:
        raise HTTPException(404, "Journey not found")
    j.active = False
    audit.record(db, user, "outreach.journey", entity_type="settings", detail=f"Paused journey {j.name}")
    db.commit()
    return {"ok": True}


def _latest_ptp(db, case_ids):
    if not case_ids:
        return {}
    rows = db.query(models.CallLog.case_id, models.CallLog.ptp_date, models.CallLog.ptp_amount, models.CallLog.created_at) \
        .filter(models.CallLog.case_id.in_(case_ids), models.CallLog.disposition == "PTP", models.CallLog.ptp_date.isnot(None)) \
        .order_by(models.CallLog.created_at).all()
    out = {}
    for cid, pd, pa, _ in rows:
        out[cid] = (pd.astimezone(IST).date() if pd.tzinfo else pd.date(), pa)
    return out


def _cases_for(db, j: models.OutreachJourney):
    from .cases import _current_period
    q = db.query(models.Case).filter(models.Case.removed.isnot(True), models.Case.period == _current_period(),
                                     func.upper(func.coalesce(models.Case.paid_status, "UNPAID")) != "PAID")
    f = j.filters or {}
    if f.get("bank"):
        q = q.filter(func.upper(models.Case.bank) == f["bank"].upper())
    if f.get("product"):
        q = q.filter(models.Case.product == f["product"])
    if f.get("bucket"):
        q = q.filter(models.Case.bucket == f["bucket"])
    if f.get("branch"):
        q = q.filter(func.upper(models.Case.branch) == f["branch"].upper())
    return q.all()


def render(text: str, case, ptp=None, link_url: str = "") -> str:
    s = get_settings()
    vals = {"name": (case.customer_name or "Customer").split()[0].title(), "amount": f"{outstanding(case):,.0f}",
            "bank": case.bank or "", "account_last4": str(case.account_no or "")[-4:],
            "ptp_date": ptp[0].strftime("%d-%b") if ptp else "", "ptp_amount": f"{D(ptp[1]):,.0f}" if ptp else "",
            "close_date": case.close_date.strftime("%d-%b") if case.close_date else "", "pay_link": link_url,
            "company": s.brand_name or ""}
    out = text
    for k, v in vals.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def _pay_link(db, case, base: str) -> str:
    if not svc.is_on(db, "payments"):
        return ""
    l = db.query(models.PaymentLink).filter(models.PaymentLink.case_id == case.id, models.PaymentLink.status == "created").first()
    if not l:
        amt = outstanding(case)
        if amt <= 0:
            return ""
        pc = svc.settings_of(db, "payments")
        if pc.get("provider") == "razorpay":
            return ""         # razorpay links are created by staff (needs API call); manual UPI pages are free to make
        l = models.PaymentLink(token=secrets.token_urlsafe(18), case_id=case.id, amount=amt, provider="manual_upi",
                               allow_partial=bool(pc.get("allow_partial", True)),
                               expires_at=datetime.now(timezone.utc) + timedelta(days=int(pc.get("expiry_days") or 7)))
        db.add(l); db.flush()
    return f"{base}/pay/{l.token}"


def run(db, on: date | None = None, base: str = "") -> dict:
    """Create today's messages for every active journey, then try to send queued ones."""
    on = on or now_ist().date()
    c = svc.settings_of(db, KEY)
    cap = int(c.get("daily_cap") or 0)
    made = 0
    sent_today = dict(db.query(models.OutreachMessage.case_id, func.count()).filter(models.OutreachMessage.run_date == on)
                      .group_by(models.OutreachMessage.case_id).all())
    for j in db.query(models.OutreachJourney).filter(models.OutreachJourney.active.is_(True)).all():
        cases = _cases_for(db, j)
        ptps = _latest_ptp(db, [x.id for x in cases]) if j.trigger == "ptp" else {}
        for case in cases:
            phone = "".join(ch for ch in str(case.new_phone or case.phone or "") if ch.isdigit())[-10:]
            if len(phone) != 10:
                continue
            for i, st in enumerate(j.steps or []):
                off = int(st["offset"])
                if j.trigger == "close":
                    hit = bool(case.close_date) and (case.close_date - on).days == off
                elif j.trigger == "ptp":
                    p = ptps.get(case.id)
                    hit = bool(p) and (on - p[0]).days == off
                else:
                    hit = on.day == off
                if not hit:
                    continue
                if db.query(models.OutreachMessage.id).filter(models.OutreachMessage.journey_id == j.id,
                                                              models.OutreachMessage.case_id == case.id,
                                                              models.OutreachMessage.step == i,
                                                              models.OutreachMessage.run_date == on).first():
                    continue
                status = "queued"
                if cap and sent_today.get(case.id, 0) >= cap:
                    status = "skipped"
                url = _pay_link(db, case, base) if "{pay_link}" in st["text"] else ""
                db.add(models.OutreachMessage(journey_id=j.id, case_id=case.id, step=i, channel=st["channel"], to=phone,
                                              text=render(st["text"], case, ptps.get(case.id), url)[:1000],
                                              status=status, run_date=on, error="daily cap reached" if status == "skipped" else None))
                if status == "queued":
                    sent_today[case.id] = sent_today.get(case.id, 0) + 1
                made += 1
    db.flush()
    res = send_queued(db)
    db.commit()
    return {"created": made, **res}


def _in_hours(db) -> bool:
    if not svc.is_on(db, "compliance"):
        return True
    from .compliance import _hm
    cc = svc.settings_of(db, "compliance")
    if not cc.get("enforce_hours", True):
        return True
    t = now_ist().time()
    return _hm(cc.get("hours_from"), "08:00") <= t < _hm(cc.get("hours_to"), "19:00")


def _send(channel, to, text, c):
    if _transport:
        return _transport(channel, to, text, c)
    from types import SimpleNamespace
    s = SimpleNamespace(whatsapp_token=c.get("whatsapp_token"), whatsapp_phone_id=c.get("whatsapp_phone_id"),
                        msg91_auth_key=c.get("msg91_auth_key"))
    if channel == "whatsapp":
        if c.get("whatsapp_provider") != "meta" or not (s.whatsapp_token and s.whatsapp_phone_id and c.get("wa_template")):
            return None, None
        body = {"messaging_product": "whatsapp", "to": "91" + to, "type": "template",
                "template": {"name": c["wa_template"], "language": {"code": c.get("wa_lang") or "en"},
                             "components": [{"type": "body", "parameters": [{"type": "text", "text": text[:1000]}]}]}}
        r = httpx.post(f"https://graph.facebook.com/v19.0/{s.whatsapp_phone_id}/messages", json=body,
                       headers={"Authorization": f"Bearer {s.whatsapp_token}"}, timeout=20)
        return (r.status_code < 300), (None if r.status_code < 300 else r.text[:280])
    if c.get("sms_provider") != "msg91" or not (s.msg91_auth_key and c.get("msg91_template_id")):
        return None, None
    body = {"template_id": c["msg91_template_id"], "short_url": "0", "recipients": [{"mobiles": "91" + to, "message": text[:600]}]}
    r = httpx.post("https://control.msg91.com/api/v5/flow/", json=body, headers={"authkey": s.msg91_auth_key}, timeout=20)
    return (r.status_code < 300), (None if r.status_code < 300 else r.text[:280])


def send_queued(db, limit: int = 2000) -> dict:
    c = {**svc.settings_of(db, KEY), **svc.secrets_of(db, KEY)}     # keys: ⚙️ Services first, .env fallback
    if not _in_hours(db):
        return {"sent": 0, "manual": 0, "failed": 0, "waiting": "outside contact hours"}
    sent = manual = failed = 0
    for m in db.query(models.OutreachMessage).filter(models.OutreachMessage.status == "queued").limit(limit).all():
        try:
            ok, err = _send(m.channel, m.to, m.text, c)
        except Exception as e:
            ok, err = False, str(e)[:280]
        if ok is None:
            m.status = "manual"; manual += 1
        elif ok:
            m.status, m.sent_at = "sent", datetime.now(timezone.utc); sent += 1
        else:
            m.status, m.error = "failed", err; failed += 1
    return {"sent": sent, "manual": manual, "failed": failed}


@router.post("/run")
def run_now(body: dict = Body(default={}), db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, OFFICE, "outreach")
    on = date.fromisoformat(body["date"]) if body.get("date") else None
    base = get_settings().public_base_url.rstrip("/") if get_settings().public_base_url else ""
    res = run(db, on, base)
    audit.record(db, user, "outreach.run", entity_type="settings", detail=f"Outreach run: {res}")
    db.commit()
    return res


@router.post("/preview")
def preview(body: dict = Body(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    """How many cases a draft journey would reach, plus a rendered sample message."""
    need(user, OFFICE, "outreach")
    v = _validate(body)
    j = models.OutreachJourney(**v)
    cases = _cases_for(db, j)
    sample = render(v["steps"][0]["text"], cases[0], None, "https://…/pay/xxxx") if cases else ""
    return {"cases": len(cases), "sample": sample}


@router.get("/messages")
def messages(status: str = "", day: str = "", db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, OFFICE, "outreach")
    q = db.query(models.OutreachMessage)
    if status:
        q = q.filter(models.OutreachMessage.status == status)
    if day:
        q = q.filter(models.OutreachMessage.run_date == date.fromisoformat(day))
    rows = q.order_by(models.OutreachMessage.id.desc()).limit(1000).all()
    cases = {c.id: c for c in db.query(models.Case).filter(models.Case.id.in_([m.case_id for m in rows] or [-1]))}
    js = {j.id: j.name for j in db.query(models.OutreachJourney).all()}
    return [{"id": m.id, "journey": js.get(m.journey_id), "case_id": m.case_id, "customer": getattr(cases.get(m.case_id), "customer_name", ""),
             "channel": m.channel, "to": m.to, "text": m.text, "status": m.status, "error": m.error,
             "run_date": m.run_date, "sent_at": m.sent_at} for m in rows]


@router.post("/messages/{mid}/done")
def mark_done(mid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """A manual message the team sent themselves (click-to-WhatsApp)."""
    need(user, OFFICE, "outreach")
    m = db.get(models.OutreachMessage, mid)
    if not m or m.status not in ("manual", "failed"):
        raise HTTPException(404, "Message not found")
    m.status, m.sent_at = "sent", datetime.now(timezone.utc)
    case = db.get(models.Case, m.case_id)
    audit.record(db, user, "outreach.sent", case, detail=f"{m.channel.upper()} sent: {m.text[:120]}")
    db.commit()
    return {"ok": True}


@router.get("/messages.csv")
def export_csv(status: str = "manual", db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, OFFICE, "outreach")
    rows = db.query(models.OutreachMessage).filter(models.OutreachMessage.status == status).limit(20000).all()
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["mobile", "channel", "message", "case_id", "date"])
    for m in rows:
        w.writerow(["91" + (m.to or ""), m.channel, m.text, m.case_id, m.run_date])
    audit.record(db, user, "download", entity_type="settings", detail=f"Outreach list ({status}) {len(rows)} rows")
    db.commit()
    return StreamingResponse(io.BytesIO(buf.getvalue().encode("utf-8-sig")), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="outreach_{status}.csv"'})
