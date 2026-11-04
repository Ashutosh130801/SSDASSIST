"""Salary payouts through RazorpayX (test mode first).

Flow:  draft batch → Admin approves (password + 2FA code + types the exact total) → items frozen
       → Admin sends → each payout created with its own idempotency key → status/UTR come back by
       signed webhook (or the Refresh button) → batch completed / partial / failed.

Double-payment guards:
  1. Only an APPROVED batch can be sent; approval freezes amount + bank-account fingerprint per item.
  2. Each item stores its idempotency key BEFORE the gateway call; resending the same attempt can
     only ever return the same payout (RazorpayX keeps the key 7 days).
  3. Items already sent (any non-failed status) are never sent again by "Send".
  4. Retrying a failed item needs Admin password + reason, opens a NEW attempt only once the old
     one is terminally failed/reversed/rejected/cancelled.
  5. One salary per employee per period: an employee can't sit in two live batches for the same period.
  6. If an employee's bank details change after approval, that item is BLOCKED at send time.
  7. Per-item and per-batch rupee caps from .env; live keys refused unless explicitly allowed.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import audit, models
from .. import razorpayx as rx
from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user
from ..security import verify_password

router = APIRouter(prefix="/api/payouts", tags=["payouts"])

IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
ACCT_RE = re.compile(r"^[0-9]{9,18}$")
DEAD = {"failed", "reversed", "rejected", "cancelled", "blocked"}       # money did NOT reach the employee
IN_FLIGHT = {"queued", "processing", "pending_approval"}
MODES = {"NEFT", "IMPS", "RTGS"}


# 🔒 SECTION LOCKED by the owner until further notice. While True every payout endpoint (including the
# webhook) refuses with 423 "Section locked" — no batch can be created, approved or sent, whatever the
# .env says. Unlock only when the owner asks: set to False here AND SALARY_LOCKED in app.jsx.
SECTION_LOCKED = True
LOCKED_MSG = "🔒 Salary & Payslips section is locked. It will be enabled by the administrator."


def _locked():
    if SECTION_LOCKED:
        raise HTTPException(423, LOCKED_MSG)


def admin_only(user: models.User = Depends(get_current_user)) -> models.User:
    _locked()
    # Deliberately stricter than require_roles(): no techsupport / read-only super-roles here.
    if user.role != "admin" or not user.is_active:
        raise HTTPException(403, "Salary payouts are Admin-only.")
    return user


def _now():
    return datetime.now(timezone.utc)


def _paise(v) -> int:
    try:
        d = Decimal(str(v).replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        raise HTTPException(400, f"Invalid amount: {v!r}")
    if d != d.quantize(Decimal("0.01")):
        raise HTTPException(400, f"Amount {v} has more than 2 decimals")
    p = int(d * 100)
    if p <= 0:
        raise HTTPException(400, "Amount must be more than ₹0")
    return p


def _rs(p: int | None) -> float:
    return round((p or 0) / 100, 2)


def _bank_of(u: models.User) -> tuple[str, str, str]:
    acct = re.sub(r"\s", "", u.bank_account or "")
    ifsc = (u.ifsc_code or "").strip().upper()
    holder = (u.bank_holder or u.name or "").strip()
    return acct, ifsc, holder


def _bank_issues(u: models.User) -> list[str]:
    acct, ifsc, holder = _bank_of(u)
    out = []
    if not acct:
        out.append("No bank account")
    elif not ACCT_RE.match(acct):
        out.append("Account number must be 9–18 digits")
    if not ifsc:
        out.append("No IFSC")
    elif not IFSC_RE.match(ifsc):
        out.append("IFSC format invalid")
    if not holder:
        out.append("No account holder name")
    if not u.is_active:
        out.append("Employee inactive / blocked")
    return out


def _narration(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9 ]", "", s or "")[:30].strip() or "Salary"


def _item_out(i: models.PayoutItem) -> dict:
    return dict(id=i.id, user_id=i.user_id, emp_code=i.emp_code, name=i.name, account=("XXXX" + (i.account_last4 or "")),
                ifsc=i.ifsc, amount=_rs(i.amount_paise), mode=i.pay_mode, status=i.status, utr=i.utr,
                payout_id=i.payout_id, attempt=i.attempt, reference_id=i.reference_id,
                fees=_rs(i.fees_paise) if i.fees_paise is not None else None,
                tax=_rs(i.tax_paise) if i.tax_paise is not None else None,
                failure_reason=i.failure_reason, updated_at=i.updated_at.isoformat() if i.updated_at else None)


def _batch_out(db: Session, b: models.PayoutBatch, items=True) -> dict:
    rows = db.query(models.PayoutItem).filter(models.PayoutItem.batch_id == b.id).order_by(models.PayoutItem.id).all()
    names = {u.id: u.name for u in db.query(models.User).filter(
        models.User.id.in_([x for x in (b.created_by, b.approved_by, b.sent_by) if x])).all()}
    cnt = {}
    for r in rows:
        cnt[r.status] = cnt.get(r.status, 0) + 1
    out = dict(id=b.id, ref=b.ref, provider=b.provider, mode=b.mode, title=b.title, period=b.period, purpose=b.purpose,
               status=b.status, total=_rs(b.total_paise), count=b.item_count, counts=cnt,
               paid_total=_rs(sum(r.amount_paise for r in rows if r.status == "processed")),
               created_by=names.get(b.created_by), created_at=b.created_at.isoformat() if b.created_at else None,
               approved_by=names.get(b.approved_by), approved_at=b.approved_at.isoformat() if b.approved_at else None,
               sent_by=names.get(b.sent_by), sent_at=b.sent_at.isoformat() if b.sent_at else None, note=b.note)
    if items:
        out["items"] = [_item_out(r) for r in rows]
    return out


def _recompute(db: Session, b: models.PayoutBatch):
    if b.status in ("draft", "cancelled", "approved"):
        return
    st = [r.status for r in db.query(models.PayoutItem.status).filter(models.PayoutItem.batch_id == b.id)]
    if any(s in IN_FLIGHT or s == "pending" for s in st):
        b.status = "sending"
    elif st and all(s == "processed" for s in st):
        b.status = "completed"
    elif any(s == "processed" for s in st):
        b.status = "partial"
    else:
        b.status = "failed"


def _approval_hash(items) -> str:
    blob = json.dumps(sorted((i.user_id, i.amount_paise, i.account_fp, i.pay_mode) for i in items))
    return hashlib.sha256(blob.encode()).hexdigest()


def _get_batch(db, bid, lock=False) -> models.PayoutBatch:
    q = db.query(models.PayoutBatch).filter(models.PayoutBatch.id == bid)
    if lock and db.bind.dialect.name == "postgresql":
        q = q.with_for_update()
    b = q.first()
    if not b:
        raise HTTPException(404, "Batch not found")
    return b


def _check_secret(user: models.User, password: str | None, otp: str | None):
    if not password or not verify_password(password, user.hashed_password or ""):
        raise HTTPException(401, "Password is incorrect.")
    if user.twofa_enabled:
        import pyotp
        if not otp or not user.totp_secret or not pyotp.TOTP(user.totp_secret).verify(str(otp).strip(), valid_window=1):
            raise HTTPException(401, "2FA code is incorrect.")


# ───────────────────────────────────────── gateway status
@router.get("/gateway")
def gateway(request: Request, user: models.User = Depends(admin_only)):
    st = rx.config_state()
    st["webhook_url"] = str(request.base_url).rstrip("/") + "/api/payouts/webhook/razorpayx"
    s = get_settings()
    st["caps"] = {"per_item": s.payout_max_item_rupees, "per_batch": s.payout_max_batch_rupees}
    return st


@router.post("/gateway/test")
def gateway_test(db: Session = Depends(get_db), user: models.User = Depends(admin_only)):
    try:
        st = rx.ping()
    except rx.GatewayError as e:
        raise HTTPException(502, str(e))
    audit.record(db, user, "payout.gateway_test", entity_type="payout", detail=f"RazorpayX {st.get('mode')} OK")
    db.commit()
    return {"ok": True, **st}


@router.get("/eligible")
def eligible(db: Session = Depends(get_db), user: models.User = Depends(admin_only)):
    out = []
    for u in db.query(models.User).filter(models.User.is_active == True).order_by(models.User.name):  # noqa: E712
        if u.role in ("techsupport", "it_support_view"):
            continue
        acct, ifsc, holder = _bank_of(u)
        out.append(dict(id=u.id, name=u.name, emp_code=u.emp_code or u.hr_ref, role=u.role, designation=u.designation,
                        bank=u.bank_name, account=("XXXX" + acct[-4:]) if acct else "", ifsc=ifsc, holder=holder,
                        issues=_bank_issues(u)))
    return out


# ───────────────────────────────────────── batches
@router.get("/batches")
def list_batches(db: Session = Depends(get_db), user: models.User = Depends(admin_only)):
    return [_batch_out(db, b, items=False) for b in
            db.query(models.PayoutBatch).order_by(models.PayoutBatch.id.desc()).limit(100)]


@router.get("/batches/{bid}")
def get_batch(bid: int, db: Session = Depends(get_db), user: models.User = Depends(admin_only)):
    return _batch_out(db, _get_batch(db, bid))


@router.post("/batches")
def create_batch(body: dict = Body(...), db: Session = Depends(get_db), user: models.User = Depends(admin_only)):
    st = rx.config_state()
    if not st["configured"]:
        raise HTTPException(400, "Gateway not configured: " + "; ".join(st["problems"]))
    s = get_settings()
    period = str(body.get("period") or "").strip()[:20]
    if not re.match(r"^\d{4}-\d{2}$", period):
        raise HTTPException(400, "Period must be YYYY-MM (the salary month).")
    purpose = "salary" if (body.get("purpose") or "salary") == "salary" else "payout"
    raw = body.get("items") or []
    if not raw:
        raise HTTPException(400, "Add at least one employee.")
    if len(raw) > 500:
        raise HTTPException(400, "At most 500 employees per batch.")
    seen, items, total, errors = set(), [], 0, []
    users = {u.id: u for u in db.query(models.User).filter(models.User.id.in_([int(r.get("user_id") or 0) for r in raw]))}
    # employees already being paid for this period in another live batch
    busy = {uid for (uid,) in db.query(models.PayoutItem.user_id)
            .join(models.PayoutBatch, models.PayoutBatch.id == models.PayoutItem.batch_id)
            .filter(models.PayoutBatch.period == period, models.PayoutBatch.purpose == purpose,
                    models.PayoutBatch.status != "cancelled", ~models.PayoutItem.status.in_(DEAD))}
    for r in raw:
        uid = int(r.get("user_id") or 0)
        u = users.get(uid)
        if not u:
            errors.append(f"Unknown employee id {uid}"); continue
        if uid in seen:
            errors.append(f"{u.name}: listed twice"); continue
        seen.add(uid)
        if purpose == "salary" and uid in busy:
            errors.append(f"{u.name}: already in another {period} salary batch"); continue
        iss = _bank_issues(u)
        if iss:
            errors.append(f"{u.name}: " + ", ".join(iss)); continue
        p = _paise(r.get("amount"))
        if p > s.payout_max_item_rupees * 100:
            errors.append(f"{u.name}: ₹{_rs(p):,.2f} is above the per-employee cap ₹{s.payout_max_item_rupees:,}"); continue
        mode = str(r.get("mode") or "NEFT").upper()
        if mode not in MODES:
            errors.append(f"{u.name}: mode must be NEFT / IMPS / RTGS"); continue
        if mode == "RTGS" and p < 200000 * 100:
            errors.append(f"{u.name}: RTGS needs ₹2,00,000 or more"); continue
        if mode == "IMPS" and p > 500000 * 100:
            errors.append(f"{u.name}: IMPS max is ₹5,00,000"); continue
        acct, ifsc, _h = _bank_of(u)
        items.append(dict(u=u, p=p, mode=mode, acct=acct, ifsc=ifsc))
        total += p
    if errors:
        raise HTTPException(400, {"message": "Fix these before creating the batch", "errors": errors})
    if total > s.payout_max_batch_rupees * 100:
        raise HTTPException(400, f"Batch total ₹{_rs(total):,.2f} is above the cap ₹{s.payout_max_batch_rupees:,}")
    day = _now().strftime("%Y%m%d")
    n = db.query(models.PayoutBatch).filter(models.PayoutBatch.ref.like(f"PB-{day}-%")).count() + 1
    b = models.PayoutBatch(ref=f"PB-{day}-{n:04d}", provider="razorpayx", mode=st["mode"],
                           title=(body.get("title") or f"Salary {period}")[:160], purpose=purpose, period=period,
                           source=(body.get("source") or "manual")[:30], source_id=body.get("source_id"),
                           status="draft", total_paise=total, item_count=len(items), created_by=user.id,
                           note=(body.get("note") or "")[:1000])
    db.add(b)
    db.flush()
    narr = _narration(body.get("narration") or f"SSD SALARY {period}")
    for it in items:
        u = it["u"]
        db.add(models.PayoutItem(batch_id=b.id, user_id=u.id, emp_code=u.emp_code or u.hr_ref, name=u.name,
                                 account_last4=it["acct"][-4:], ifsc=it["ifsc"], amount_paise=it["p"],
                                 pay_mode=it["mode"], narration=narr, status="pending"))
    audit.record(db, user, "payout.batch_create", entity_type="payout",
                 detail=f"{b.ref} {b.mode} {len(items)} employees ₹{_rs(total):,.2f}", meta={"batch_id": b.id})
    db.commit()
    return _batch_out(db, b)


@router.post("/batches/{bid}/cancel")
def cancel_batch(bid: int, body: dict = Body(default={}), db: Session = Depends(get_db), user: models.User = Depends(admin_only)):
    b = _get_batch(db, bid, lock=True)
    if b.status not in ("draft", "approved"):
        raise HTTPException(400, "Only a draft or approved (not yet sent) batch can be cancelled.")
    if db.query(models.PayoutItem).filter(models.PayoutItem.batch_id == b.id, models.PayoutItem.payout_id.isnot(None)).count():
        raise HTTPException(400, "Some payouts were already created — cannot cancel.")
    b.status = "cancelled"
    db.query(models.PayoutItem).filter(models.PayoutItem.batch_id == b.id).update({"status": "cancelled"})
    audit.record(db, user, "payout.batch_cancel", entity_type="payout", detail=f"{b.ref}: {body.get('reason') or ''}"[:300])
    db.commit()
    return _batch_out(db, b)


@router.post("/batches/{bid}/approve")
def approve_batch(bid: int, body: dict = Body(...), db: Session = Depends(get_db), user: models.User = Depends(admin_only)):
    b = _get_batch(db, bid, lock=True)
    if b.status != "draft":
        raise HTTPException(400, f"Batch is {b.status}; only a draft can be approved.")
    _check_secret(user, body.get("password"), body.get("otp"))
    if _paise(body.get("confirm_total")) != b.total_paise:
        raise HTTPException(400, f"Typed total does not match the batch total ₹{_rs(b.total_paise):,.2f}")
    items = db.query(models.PayoutItem).filter(models.PayoutItem.batch_id == b.id).all()
    for i in items:
        u = db.get(models.User, i.user_id)
        iss = _bank_issues(u) if u else ["employee missing"]
        if iss:
            raise HTTPException(400, f"{i.name}: " + ", ".join(iss))
        acct, ifsc, _h = _bank_of(u)
        i.account_fp = rx.fingerprint(acct, ifsc)
        i.account_last4, i.ifsc = acct[-4:], ifsc
        i.idempotency_key = str(uuid.uuid4())
        i.reference_id = f"{b.ref}-{i.id}-A{i.attempt}"
    b.approval_hash = _approval_hash(items)
    b.status, b.approved_by, b.approved_at = "approved", user.id, _now()
    audit.record(db, user, "payout.batch_approve", entity_type="payout",
                 detail=f"{b.ref} approved {len(items)} employees ₹{_rs(b.total_paise):,.2f} ({b.mode})",
                 meta={"batch_id": b.id, "hash": b.approval_hash})
    db.commit()
    return _batch_out(db, b)


def _fund_account(db: Session, b: models.PayoutBatch, i: models.PayoutItem, u: models.User) -> str:
    fa = (db.query(models.PayoutFundAccount)
          .filter_by(provider=b.provider, mode=b.mode, user_id=u.id, account_fp=i.account_fp).first())
    if fa and fa.fund_account_id:
        return fa.fund_account_id
    acct, ifsc, holder = _bank_of(u)
    cid = (fa.contact_id if fa else None) or rx.create_contact(u.name, f"EMP-{u.id}", u.email, u.phone)
    if not fa:
        fa = models.PayoutFundAccount(provider=b.provider, mode=b.mode, user_id=u.id, account_fp=i.account_fp, contact_id=cid)
        db.add(fa)
        db.flush()
    fa.fund_account_id = rx.create_fund_account(cid, holder, ifsc, acct)
    db.commit()
    return fa.fund_account_id


def _apply_payout(i: models.PayoutItem, p: dict):
    st = rx.STATUS_MAP.get(str(p.get("status") or "").lower())
    if not st:
        return
    if i.status in ("reversed", "failed", "rejected", "cancelled"):
        return                                   # terminal — ignore late / out-of-order events
    if i.status == "processed" and st != "reversed":
        return                                   # only a reversal may follow processed
    i.status = st
    i.payout_id = p.get("id") or i.payout_id
    i.utr = p.get("utr") or i.utr
    if p.get("fees") is not None:
        i.fees_paise = int(p.get("fees") or 0)
    if p.get("tax") is not None:
        i.tax_paise = int(p.get("tax") or 0)
    sd = p.get("status_details") or {}
    if st in DEAD:
        i.failure_reason = (sd.get("description") or p.get("failure_reason") or i.failure_reason or st)[:300]


@router.post("/batches/{bid}/send")
def send_batch(bid: int, body: dict = Body(default={}), db: Session = Depends(get_db), user: models.User = Depends(admin_only)):
    b = _get_batch(db, bid, lock=True)
    if b.status not in ("approved", "sending", "partial", "failed"):
        raise HTTPException(400, f"Batch is {b.status}; it must be approved by Admin first.")
    st = rx.config_state()
    if not st["configured"]:
        raise HTTPException(400, "Gateway not configured: " + "; ".join(st["problems"]))
    if st["mode"] != b.mode:
        raise HTTPException(400, f"Batch was approved in {b.mode} mode but the server keys are {st['mode']} — create a new batch.")
    items = db.query(models.PayoutItem).filter(models.PayoutItem.batch_id == b.id).order_by(models.PayoutItem.id).all()
    if _approval_hash(items) != b.approval_hash:
        raise HTTPException(409, "Batch contents changed after approval — refusing to send.")
    if b.status == "approved":
        b.status, b.sent_by, b.sent_at = "sending", user.id, _now()
        db.commit()
    sent = errs = 0
    for i in items:
        if i.status != "pending" or not i.idempotency_key:
            continue                                  # already sent / in flight / done — never send twice
        u = db.get(models.User, i.user_id)
        acct, ifsc, _h = _bank_of(u) if u else ("", "", "")
        if not u or rx.fingerprint(acct, ifsc) != i.account_fp:
            i.status, i.failure_reason = "blocked", "Bank details changed after approval — re-verify, then Retry"
            db.commit(); errs += 1; continue
        try:
            fa = _fund_account(db, b, i, u)
            i.fund_account_id = fa
            p = rx.create_payout(fa, i.amount_paise, i.pay_mode, b.purpose, i.reference_id, i.narration or "Salary",
                                 i.idempotency_key, notes={"batch": b.ref, "emp": i.emp_code or str(i.user_id)})
            _apply_payout(i, p)
            if i.status == "pending":
                i.status = "processing"
            sent += 1
        except rx.GatewayError as e:
            errs += 1
            if e.retriable:     # outcome unknown: keep status pending + SAME key → pressing Send again is safe
                i.failure_reason = f"{e} — press Send again (same idempotency key, cannot double-pay)"[:300]
            else:
                i.status, i.failure_reason = "failed", str(e)[:300]
        db.commit()
    _recompute(db, b)
    audit.record(db, user, "payout.batch_send", entity_type="payout", detail=f"{b.ref}: sent {sent}, issues {errs}",
                 meta={"batch_id": b.id})
    db.commit()
    return _batch_out(db, b)


@router.post("/batches/{bid}/refresh")
def refresh_batch(bid: int, db: Session = Depends(get_db), user: models.User = Depends(admin_only)):
    b = _get_batch(db, bid)
    n = 0
    for i in db.query(models.PayoutItem).filter(models.PayoutItem.batch_id == b.id,
                                                models.PayoutItem.payout_id.isnot(None)):
        if i.status in IN_FLIGHT or (i.status == "processed" and not i.utr):
            try:
                _apply_payout(i, rx.fetch_payout(i.payout_id)); n += 1
            except rx.GatewayError as e:
                i.failure_reason = str(e)[:300]
    _recompute(db, b)
    db.commit()
    return _batch_out(db, b)


@router.post("/items/{iid}/retry")
def retry_item(iid: int, body: dict = Body(...), db: Session = Depends(get_db), user: models.User = Depends(admin_only)):
    i = db.get(models.PayoutItem, iid)
    if not i:
        raise HTTPException(404, "Item not found")
    if i.status not in DEAD - {"cancelled"}:
        raise HTTPException(400, f"Only failed / reversed / rejected / blocked payouts can be retried (this one is {i.status}).")
    reason = (body.get("reason") or "").strip()
    if len(reason) < 5:
        raise HTTPException(400, "Give a reason for the retry.")
    _check_secret(user, body.get("password"), body.get("otp"))
    b = _get_batch(db, i.batch_id, lock=True)
    u = db.get(models.User, i.user_id)
    iss = _bank_issues(u) if u else ["employee missing"]
    if iss:
        raise HTTPException(400, ", ".join(iss))
    acct, ifsc, _h = _bank_of(u)
    old = f"attempt {i.attempt} {i.status} {i.payout_id or ''}"
    i.attempt += 1
    i.account_fp, i.account_last4, i.ifsc = rx.fingerprint(acct, ifsc), acct[-4:], ifsc
    i.idempotency_key = str(uuid.uuid4())
    i.reference_id = f"{b.ref}-{i.id}-A{i.attempt}"
    i.payout_id = i.utr = i.fund_account_id = None
    i.status, i.failure_reason = "pending", None
    items = db.query(models.PayoutItem).filter(models.PayoutItem.batch_id == b.id).all()
    b.approval_hash = _approval_hash(items)
    b.status = "sending"
    audit.record(db, user, "payout.item_retry", entity_type="payout", target_user_id=i.user_id,
                 old=old, new=f"attempt {i.attempt}", detail=f"{b.ref} {i.name}: {reason}"[:300])
    db.commit()
    return _batch_out(db, b)


# ───────────────────────────────────────── webhook (no login — HMAC-signed by RazorpayX)
@router.post("/webhook/razorpayx")
async def webhook(request: Request, db: Session = Depends(get_db)):
    _locked()
    raw = await request.body()
    if not rx.verify_webhook(raw, request.headers.get("X-Razorpay-Signature")):
        raise HTTPException(401, "Bad signature")
    try:
        data = json.loads(raw)
    except ValueError:
        raise HTTPException(400, "Bad JSON")
    event = str(data.get("event") or "")
    ent = ((data.get("payload") or {}).get("payout") or {}).get("entity") or {}
    eid = request.headers.get("X-Razorpay-Event-Id") or hashlib.sha256(raw).hexdigest()
    if db.query(models.PayoutWebhookEvent).filter_by(event_id=eid).first():
        return {"ok": True, "duplicate": True}
    ev = models.PayoutWebhookEvent(event_id=eid[:80], event=event[:40], payout_id=(ent.get("id") or "")[:40],
                                   status=(ent.get("status") or "")[:20])
    db.add(ev)
    if event.startswith("payout.") and ent:
        q = db.query(models.PayoutItem)
        i = (q.filter(models.PayoutItem.payout_id == ent.get("id")).first() if ent.get("id") else None) \
            or (q.filter(models.PayoutItem.reference_id == ent.get("reference_id")).first() if ent.get("reference_id") else None)
        if i and (int(ent.get("amount") or 0) == i.amount_paise):
            before = i.status
            _apply_payout(i, ent)
            ev.applied = i.status != before
            b = db.get(models.PayoutBatch, i.batch_id)
            if b:
                _recompute(db, b)
    db.commit()
    return {"ok": True}
