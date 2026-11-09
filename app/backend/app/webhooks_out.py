"""Outgoing webhooks (🔌 Open API add-on).

emit() only QUEUES a delivery row inside the caller's transaction (so nothing is sent for a change that
rolls back). A background sweeper (main.py) posts pending deliveries, signed with HMAC-SHA256:
    X-RecoverIQ-Event: payment.received
    X-RecoverIQ-Signature: sha256=<hex hmac of the raw body with the webhook secret>
Retries up to 6 times with growing gaps.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import socket
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from . import models
from . import services as svc

EVENTS = ("payment.received", "ptp.created", "call.logged", "visit.logged", "settlement.approved", "paylink.paid")
MAX_ATTEMPTS = 6


def emit(db, event: str, payload: dict):
    if event not in EVENTS or not svc.is_on(db, "open_api"):
        return 0
    n = 0
    for w in db.query(models.Webhook).filter(models.Webhook.active.is_(True)).all():
        if w.events and event not in w.events:
            continue
        if w.banks and (payload.get("bank") or "").upper() not in [b.upper() for b in w.banks]:
            continue
        db.add(models.WebhookDelivery(webhook_id=w.id, event=event,
                                      payload={"event": event, "at": datetime.now(timezone.utc).isoformat(), "data": payload}))
        n += 1
    return n


def check_url(url: str) -> str:
    """Only public https endpoints (no SSRF into the office network)."""
    u = urlparse(url or "")
    if u.scheme != "https" or not u.hostname:
        raise ValueError("Webhook URL must start with https://")
    try:
        infos = socket.getaddrinfo(u.hostname, None)
    except OSError:
        raise ValueError("Webhook host can't be resolved")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError("Webhook URL must be a public internet address")
    return url


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new((secret or "").encode(), body, hashlib.sha256).hexdigest()


_transport = None   # tests inject a fake: fn(url, body, headers) -> status code


def _post(url, body, headers):
    if _transport:
        return _transport(url, body, headers)
    import httpx
    check_url(url)
    r = httpx.post(url, content=body, headers=headers, timeout=10, follow_redirects=False)
    return r.status_code


def deliver_pending(db, limit: int = 50) -> int:
    now = datetime.now(timezone.utc)
    rows = (db.query(models.WebhookDelivery).filter(models.WebhookDelivery.status == "pending")
            .order_by(models.WebhookDelivery.id).limit(limit).all())
    sent = 0
    for d in rows:
        if d.attempts and d.delivered_at and now < _aware(d.delivered_at) + timedelta(minutes=2 ** d.attempts):
            continue          # back-off (delivered_at holds the last attempt time while pending)
        w = db.get(models.Webhook, d.webhook_id)
        if not w or not w.active:
            d.status, d.error = "failed", "webhook removed / paused"
            continue
        body = json.dumps(d.payload, default=str, separators=(",", ":")).encode()
        headers = {"Content-Type": "application/json", "X-RecoverIQ-Event": d.event,
                   "X-RecoverIQ-Delivery": str(d.id), "X-RecoverIQ-Signature": sign(w.secret, body)}
        d.attempts = (d.attempts or 0) + 1
        try:
            code = _post(w.url, body, headers)
            d.response_code = code
            if 200 <= int(code) < 300:
                d.status, d.error = "ok", None
                sent += 1
            else:
                d.error = f"HTTP {code}"
        except Exception as e:
            d.error = str(e)[:300]
        d.delivered_at = datetime.now(timezone.utc)
        if d.status == "pending" and d.attempts >= MAX_ATTEMPTS:
            d.status = "failed"
    db.commit()
    return sent


def _aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
