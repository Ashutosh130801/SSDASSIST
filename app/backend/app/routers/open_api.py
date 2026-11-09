"""🔌 Open API & webhooks add-on.

Admin creates API keys (shown ONCE; stored as SHA-256) with scopes and an optional bank limit, and webhooks
(https only, public hosts only, HMAC-signed). External systems call /api/open/v1/* with header
   Authorization: Bearer riq_<key>

Scopes
   cases:read      GET  /api/open/v1/cases?bank=&updated_since=&page=   GET /api/open/v1/cases/{account_no}
   payments:write  POST /api/open/v1/payments  {account_no, amount, mode, reference}   (idempotent by reference)
   events:read     GET  /api/open/v1/events?since_id=   (the same events the webhooks carry)
Phone numbers are masked in API output unless the key has the "pii" scope.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, Header, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import audit, models, webhooks_out
from ..addons_common import D, mask_phone, need, outstanding, post_payment
from ..database import get_db
from ..deps import get_current_user

admin_router = APIRouter(prefix="/api/apikeys", tags=["apikeys"])
router = APIRouter(prefix="/api/open/v1", tags=["open-api"])
SCOPES = ("cases:read", "payments:write", "events:read", "pii")


def _h(k: str) -> str:
    return hashlib.sha256(k.encode()).hexdigest()


@admin_router.get("")
def list_keys(db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, ("admin",), "API keys")
    keys = [{"id": k.id, "name": k.name, "prefix": k.prefix, "scopes": k.scopes, "banks": k.banks, "revoked": k.revoked,
             "last_used_at": k.last_used_at, "created_at": k.created_at} for k in db.query(models.ApiKey).order_by(models.ApiKey.id).all()]
    hooks = [{"id": w.id, "url": w.url, "events": w.events, "banks": w.banks, "active": w.active, "created_at": w.created_at,
              "recent": [{"id": d.id, "event": d.event, "status": d.status, "attempts": d.attempts, "code": d.response_code,
                          "error": d.error, "at": d.created_at}
                         for d in db.query(models.WebhookDelivery).filter(models.WebhookDelivery.webhook_id == w.id)
                         .order_by(models.WebhookDelivery.id.desc()).limit(10)]}
             for w in db.query(models.Webhook).order_by(models.Webhook.id).all()]
    return {"keys": keys, "webhooks": hooks, "scopes": SCOPES, "events": webhooks_out.EVENTS}


@admin_router.post("")
def create_key(body: dict = Body(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, ("admin",), "API keys")
    scopes = [s for s in body.get("scopes") or [] if s in SCOPES]
    if not scopes:
        raise HTTPException(400, "Pick at least one scope")
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Name is required")
    raw = "riq_" + secrets.token_urlsafe(30)
    k = models.ApiKey(name=name[:120], prefix=raw[:12], key_hash=_h(raw), scopes=scopes,
                      banks=[b.strip().upper() for b in body.get("banks") or [] if b.strip()], created_by=user.id)
    db.add(k); db.flush()
    audit.record(db, user, "apikey.create", entity_type="settings", detail=f"API key {name} {scopes}")
    db.commit()
    return {"id": k.id, "key": raw, "note": "Copy this key now — it is shown only once."}


@admin_router.post("/{kid}/revoke")
def revoke(kid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, ("admin",), "API keys")
    k = db.get(models.ApiKey, kid)
    if not k:
        raise HTTPException(404, "Key not found")
    k.revoked = True
    audit.record(db, user, "apikey.revoke", entity_type="settings", detail=k.name)
    db.commit()
    return {"ok": True}


@admin_router.post("/webhooks")
def add_webhook(body: dict = Body(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, ("admin",), "webhooks")
    try:
        url = webhooks_out.check_url((body.get("url") or "").strip())
    except ValueError as e:
        raise HTTPException(400, str(e))
    ev = [e for e in body.get("events") or [] if e in webhooks_out.EVENTS]
    secret = "whsec_" + secrets.token_urlsafe(24)
    w = models.Webhook(url=url[:400], events=ev, secret=secret, banks=[b.strip().upper() for b in body.get("banks") or [] if b.strip()],
                       created_by=user.id)
    db.add(w); db.flush()
    audit.record(db, user, "webhook.create", entity_type="settings", detail=url)
    db.commit()
    return {"id": w.id, "secret": secret, "note": "Use this secret to verify X-RecoverIQ-Signature. Shown only once."}


@admin_router.post("/webhooks/{wid}")
def toggle_webhook(wid: int, body: dict = Body(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, ("admin",), "webhooks")
    w = db.get(models.Webhook, wid)
    if not w:
        raise HTTPException(404, "Webhook not found")
    if body.get("delete"):
        db.delete(w)
    else:
        w.active = bool(body.get("active"))
    audit.record(db, user, "webhook.update", entity_type="settings", detail=f"{w.url} {'deleted' if body.get('delete') else w.active}")
    db.commit()
    return {"ok": True}


@admin_router.post("/webhooks/{wid}/test")
def test_webhook(wid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, ("admin",), "webhooks")
    w = db.get(models.Webhook, wid)
    if not w:
        raise HTTPException(404, "Webhook not found")
    db.add(models.WebhookDelivery(webhook_id=w.id, event="test", payload={"event": "test", "at": datetime.now(timezone.utc).isoformat(), "data": {}}))
    db.commit()
    webhooks_out.deliver_pending(db)
    d = db.query(models.WebhookDelivery).filter(models.WebhookDelivery.webhook_id == w.id).order_by(models.WebhookDelivery.id.desc()).first()
    return {"status": d.status, "code": d.response_code, "error": d.error}


# ───────────────────────── external API ─────────────────────────
def api_key(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> models.ApiKey:
    raw = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    if not raw.startswith("riq_"):
        raise HTTPException(401, "Missing API key")
    k = db.query(models.ApiKey).filter(models.ApiKey.key_hash == _h(raw), models.ApiKey.revoked.is_(False)).first()
    if not k:
        raise HTTPException(401, "Invalid API key")
    k.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return k


def _need(k, scope):
    if scope not in (k.scopes or []):
        raise HTTPException(403, f"This key lacks the {scope} scope")


def _cq(db, k):
    q = db.query(models.Case).filter(models.Case.removed.isnot(True))
    if k.banks:
        q = q.filter(func.upper(models.Case.bank).in_(k.banks))
    return q


def _case(c, pii):
    return {"account_no": c.account_no, "bank": c.bank, "product": c.product, "bucket": c.bucket, "period": c.period,
            "customer_name": c.customer_name, "phone": c.phone if pii else mask_phone(c.phone),
            "outstanding": float(outstanding(c)), "received": float(D(c.received_amount)), "paid_status": c.paid_status,
            "disposition": c.disposition, "follow_up_date": c.follow_up_date, "updated_at": c.updated_at}


@router.get("/cases")
def ext_cases(bank: str = "", updated_since: str = "", page: int = 1, db: Session = Depends(get_db), k=Depends(api_key)):
    _need(k, "cases:read")
    q = _cq(db, k)
    if bank:
        q = q.filter(func.upper(models.Case.bank) == bank.upper())
    if updated_since:
        try:
            q = q.filter(models.Case.updated_at >= datetime.fromisoformat(updated_since))
        except ValueError:
            raise HTTPException(400, "updated_since must be ISO date/time")
    page = max(page, 1)
    rows = q.order_by(models.Case.id).offset((page - 1) * 200).limit(200).all()
    return {"page": page, "count": len(rows), "cases": [_case(c, "pii" in (k.scopes or [])) for c in rows]}


@router.get("/cases/{account_no}")
def ext_case(account_no: str, db: Session = Depends(get_db), k=Depends(api_key)):
    _need(k, "cases:read")
    rows = _cq(db, k).filter(models.Case.account_no == account_no).order_by(models.Case.period.desc()).all()
    if not rows:
        raise HTTPException(404, "Not found")
    return [_case(c, "pii" in (k.scopes or [])) for c in rows]


@router.post("/payments")
def ext_payment(body: dict = Body(...), db: Session = Depends(get_db), k=Depends(api_key)):
    _need(k, "payments:write")
    ref = str(body.get("reference") or "").strip()
    if not ref:
        raise HTTPException(400, "reference is required (makes the call safe to retry)")
    amt = D(body.get("amount"))
    if amt <= 0:
        raise HTTPException(400, "amount must be more than zero")
    key = f"api:{k.id}:{ref}"[:120]
    if db.query(models.PaymentEvent).filter(models.PaymentEvent.ref == key).first():
        return {"duplicate": True}
    from .cases import _current_period
    c = _cq(db, k).filter(models.Case.account_no == str(body.get("account_no") or "")) \
        .order_by((models.Case.period == _current_period()).desc(), models.Case.period.desc()).first()
    if not c:
        raise HTTPException(404, "Account not found")
    db.add(models.PaymentEvent(ref=key, case_id=c.id, amount=amt, source="api"))
    post_payment(db, c, amt, f"API ({k.name}) {body.get('mode') or ''}".strip(), f"ref {ref}"[:120])
    db.commit()
    return {"ok": True, "paid_status": c.paid_status, "outstanding": float(outstanding(c))}


@router.get("/events")
def ext_events(since_id: int = 0, db: Session = Depends(get_db), k=Depends(api_key)):
    _need(k, "events:read")
    q = db.query(models.WebhookDelivery).filter(models.WebhookDelivery.id > since_id).order_by(models.WebhookDelivery.id).limit(500)
    seen, out = set(), []
    for d in q:
        p = d.payload or {}
        sig = (p.get("event"), p.get("at"))
        if sig in seen:
            continue
        if k.banks and str((p.get("data") or {}).get("bank") or "").upper() not in k.banks:
            continue
        seen.add(sig); out.append({"id": d.id, **p})
    return {"events": out, "next_since_id": out[-1]["id"] if out else since_id}
