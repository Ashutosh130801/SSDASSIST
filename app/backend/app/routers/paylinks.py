"""💳 Payment links & auto-reconciliation add-on.

Flow
 1. Staff create a link for a case (amount defaults to the outstanding).  Provider:
      • razorpay  → a Razorpay Payment Link (test keys unless RAZORPAY_ALLOW_LIVE); paid links reconcile
                    automatically through the signed webhook POST /api/paylinks/webhook.
      • manual_upi → a plain UPI link/QR to your collection VPA; reconcile by uploading the bank statement.
 2. The customer opens /pay/<token> (self-service page): sees what is due, pays, or reports a UTR.
 3. Reconciliation posts the payment into the case exactly like a manual payment (paymath + history),
    once only (PaymentEvent dedupe), and notifies the owner.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import html
import io
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
from fastapi import APIRouter, Body, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from .. import audit, models
from .. import services as svc
from ..addons_common import CASE_WORKERS, D, OFFICE, case_or_404, need, outstanding, post_payment, scoped_cases
from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/api/paylinks", tags=["paylinks"])
public = APIRouter(tags=["pay"])
KEY = "payments"
RZP = "https://api.razorpay.com/v1"
_transport = None          # tests: fn(method, url, json) -> dict


def _rzp_keys():
    s = get_settings()
    if not (s.razorpay_key_id and s.razorpay_key_secret):
        raise HTTPException(400, "Razorpay keys are not set — add RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET to the server .env")
    if s.razorpay_key_id.startswith("rzp_live_") and not s.razorpay_allow_live:
        raise HTTPException(400, "Live Razorpay keys are blocked until RAZORPAY_ALLOW_LIVE=true is set (test first with rzp_test_ keys)")
    return s.razorpay_key_id, s.razorpay_key_secret


def _rzp(method, path, body=None):
    if _transport:
        return _transport(method, path, body)
    kid, sec = _rzp_keys()
    r = httpx.request(method, RZP + path, json=body, auth=(kid, sec), timeout=20)
    if r.status_code >= 300:
        try:
            msg = r.json().get("error", {}).get("description")
        except ValueError:
            msg = r.text[:200]
        raise HTTPException(502, f"Razorpay: {msg}")
    return r.json()


def _base_url(request: Request | None) -> str:
    s = get_settings()
    if s.public_base_url:
        return s.public_base_url.rstrip("/")
    return str(request.base_url).rstrip("/") if request else ""


def _out(l: models.PaymentLink, case=None, base=""):
    return {"id": l.id, "token": l.token, "case_id": l.case_id, "customer": getattr(case, "customer_name", None),
            "account_no": getattr(case, "account_no", None), "bank": getattr(case, "bank", None),
            "amount": float(l.amount or 0), "paid_amount": float(l.paid_amount or 0), "status": l.status,
            "provider": l.provider, "short_url": l.short_url, "page_url": f"{base}/pay/{l.token}", "utr": l.utr,
            "expires_at": l.expires_at, "paid_at": l.paid_at, "created_at": l.created_at}


def _expire(db, rows):
    now = datetime.now(timezone.utc)
    for l in rows:
        ex = l.expires_at if (l.expires_at is None or l.expires_at.tzinfo) else l.expires_at.replace(tzinfo=timezone.utc)
        if l.status == "created" and ex and ex < now:
            l.status = "expired"


@router.get("")
def list_links(status: str = "", case_id: int | None = None, request: Request = None,
               db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, CASE_WORKERS, "payment links")
    ids = [c.id for c in scoped_cases(db, user).with_entities(models.Case.id)] if user.role != "admin" else None
    q = db.query(models.PaymentLink)
    if ids is not None:
        q = q.filter(models.PaymentLink.case_id.in_(ids or [-1]))
    if case_id:
        q = q.filter(models.PaymentLink.case_id == case_id)
    rows = q.order_by(models.PaymentLink.created_at.desc()).limit(500).all()
    _expire(db, rows); db.commit()
    if status:
        rows = [r for r in rows if r.status == status]
    cases = {c.id: c for c in db.query(models.Case).filter(models.Case.id.in_([r.case_id for r in rows] or [-1]))}
    base = _base_url(request)
    tot = {"links": len(rows), "paid": sum(1 for r in rows if r.status in ("paid", "partial")),
           "collected": float(sum(D(r.paid_amount) for r in rows))}
    return {"summary": tot, "links": [_out(r, cases.get(r.case_id), base) for r in rows]}


@router.post("")
def create_link(body: dict = Body(...), request: Request = None, db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, CASE_WORKERS, "payment links")
    c = svc.settings_of(db, KEY)
    case = case_or_404(db, user, int(body.get("case_id") or 0))
    due = outstanding(case)
    amt = D(body.get("amount")) if body.get("amount") not in (None, "") else due
    if amt <= 0:
        raise HTTPException(400, "Nothing is due on this case — enter an amount")
    if amt < D(c.get("min_amount") or 1):
        raise HTTPException(400, f"Amount must be at least ₹{c.get('min_amount')}")
    if amt > Decimal("10000000"):
        raise HTTPException(400, "Amount too large for a link")
    if not (case.phone or "").strip() and body.get("send"):
        raise HTTPException(400, "This case has no phone number")
    prov = c.get("provider") or "razorpay"
    days = max(1, min(int(c.get("expiry_days") or 7), 90))
    partial = bool(c.get("allow_partial", True))
    tok = secrets.token_urlsafe(18)
    link = models.PaymentLink(token=tok, case_id=case.id, amount=amt, allow_partial=partial, provider=prov,
                              expires_at=datetime.now(timezone.utc) + timedelta(days=days), created_by=user.id)
    if prov == "razorpay":
        phone = "".join(ch for ch in str(case.phone or "") if ch.isdigit())[-10:]
        req = {"amount": int(amt * 100), "currency": "INR", "accept_partial": partial,
               "expire_by": int(link.expires_at.timestamp()), "reference_id": tok[:40],
               "description": f"{case.bank or ''} loan a/c ending {str(case.account_no or '')[-4:]}"[:2048],
               "customer": {"name": (case.customer_name or "")[:100], **({"contact": "+91" + phone} if len(phone) == 10 else {})},
               "notify": {"sms": bool(body.get("send")), "email": False}, "reminder_enable": False,
               "notes": {"case_id": str(case.id), "token": tok},
               "callback_url": f"{_base_url(request)}/pay/{tok}", "callback_method": "get"}
        if partial:
            req["first_min_partial_amount"] = int(D(c.get("min_amount") or 100) * 100)
        r = _rzp("POST", "/payment_links", req)
        link.provider_id, link.short_url = r.get("id"), r.get("short_url")
    else:
        s = get_settings()
        if not s.upi_vpa:
            raise HTTPException(400, "Set UPI_VPA (your collection UPI id) in the server .env for UPI links")
        link.short_url = None
    db.add(link); db.flush()
    audit.record(db, user, "paylink.create", case, new=str(amt), detail=f"Payment link ₹{amt} ({prov})")
    db.commit()
    return _out(link, case, _base_url(request))


@router.post("/{lid}/cancel")
def cancel_link(lid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, CASE_WORKERS, "payment links")
    l = db.get(models.PaymentLink, lid)
    if not l:
        raise HTTPException(404, "Link not found")
    case = case_or_404(db, user, l.case_id)
    if l.status != "created":
        raise HTTPException(400, f"Link is already {l.status}")
    if l.provider == "razorpay" and l.provider_id:
        try:
            _rzp("POST", f"/payment_links/{l.provider_id}/cancel")
        except HTTPException:
            pass
    l.status = "cancelled"
    audit.record(db, user, "paylink.cancel", case, detail=f"Link #{l.id} cancelled")
    db.commit()
    return {"ok": True}


def _apply(db, link: models.PaymentLink, amount: Decimal, ref: str, source: str, utr: str = "") -> bool:
    """Post a confirmed payment to the case once. Returns False if this ref was already applied."""
    if amount <= 0 or db.query(models.PaymentEvent).filter(models.PaymentEvent.ref == ref).first():
        return False
    case = db.get(models.Case, link.case_id)
    if not case:
        return False
    db.add(models.PaymentEvent(ref=ref, link_id=link.id, case_id=case.id, amount=amount, source=source))
    link.paid_amount = D(link.paid_amount) + amount
    link.status = "paid" if link.paid_amount >= D(link.amount) else "partial"
    link.paid_at = datetime.now(timezone.utc)
    link.utr = (utr or link.utr or "")[:80]
    link.applied = True
    post_payment(db, case, amount, "Payment link" if source == "webhook" else "UPI (statement)", f"ref {utr or ref}"[:120],
                 actor_id=link.created_by)
    from . import notifications
    try:
        from types import SimpleNamespace
        notifications.notify_case_change(db, case, SimpleNamespace(id=None, name="Customer (online)"), f"💳 Customer paid ₹{amount} online → {case.paid_status}", ntype="payment")
    except Exception:
        pass
    try:
        from .. import webhooks_out
        webhooks_out.emit(db, "paylink.paid", {"case_id": case.id, "account_no": case.account_no, "bank": case.bank,
                                               "amount": float(amount), "utr": utr})
    except Exception:
        pass
    return True


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    """Razorpay → us. Verified with RAZORPAY_WEBHOOK_SECRET (X-Razorpay-Signature, HMAC-SHA256 of the raw body)."""
    raw = await request.body()
    secret = get_settings().razorpay_webhook_secret
    sig = request.headers.get("X-Razorpay-Signature", "")
    if not secret or not hmac.compare_digest(hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest(), sig):
        raise HTTPException(400, "Bad signature")
    ev = json.loads(raw or b"{}")
    if ev.get("event") not in ("payment_link.paid", "payment_link.partially_paid"):
        return {"ignored": ev.get("event")}
    pl = (ev.get("payload", {}).get("payment_link", {}) or {}).get("entity", {})
    pay = (ev.get("payload", {}).get("payment", {}) or {}).get("entity", {})
    link = db.query(models.PaymentLink).filter(models.PaymentLink.provider_id == pl.get("id")).first()
    if not link:
        return {"ignored": "unknown link"}
    amt = D(pay.get("amount") or 0) / 100
    utr = ((pay.get("acquirer_data") or {}).get("rrn") or (pay.get("acquirer_data") or {}).get("upi_transaction_id") or pay.get("id") or "")
    done = _apply(db, link, amt, "rzp:" + str(pay.get("id") or pl.get("id")), "webhook", str(utr))
    db.commit()
    return {"applied": done}


# ───────────── statement reconciliation (UPI / NEFT credits) ─────────────
def _read_rows(name: str, data: bytes) -> list[list]:
    if name.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        ws = load_workbook(io.BytesIO(data), read_only=True, data_only=True).active
        return [list(r) for r in ws.iter_rows(values_only=True)]
    txt = data.decode("utf-8-sig", errors="replace")
    return [r for r in csv.reader(io.StringIO(txt))]


def _find_header(rows):
    for i, r in enumerate(rows[:30]):
        cells = [str(c or "").strip().lower() for c in r]
        if any("narration" in c or "description" in c or "remarks" in c or "particulars" in c for c in cells) and \
           any("credit" in c or "deposit" in c or c == "amount" or "cr amount" in c for c in cells):
            return i, cells
    raise HTTPException(400, "Couldn't find the header row — need a Narration/Description column and a Credit/Amount column")


def _col(cells, *words):
    for w in words:
        for j, c in enumerate(cells):
            if w in c:
                return j
    return None


def parse_statement(name: str, data: bytes) -> list[dict]:
    rows = _read_rows(name, data)
    h, cells = _find_header(rows)
    jn = _col(cells, "narration", "description", "particulars", "remarks")
    jc = _col(cells, "credit", "deposit", "cr amount", "amount")
    jr = _col(cells, "utr", "ref", "cheque", "chq")
    jd = _col(cells, "value date", "txn date", "date")
    out = []
    for r in rows[h + 1:]:
        if jc is None or jc >= len(r):
            continue
        try:
            amt = D(str(r[jc] or "0").replace(",", "").replace("₹", "").strip() or 0)
        except Exception:
            continue
        if amt <= 0:
            continue
        narr = str(r[jn] or "") if jn is not None and jn < len(r) else ""
        ref = str(r[jr] or "") if jr is not None and jr < len(r) else ""
        if not ref:
            m = re.search(r"\b(\d{12})\b", narr)        # UPI RRN is 12 digits
            ref = m.group(1) if m else ""
        out.append({"date": str(r[jd]) if jd is not None and jd < len(r) else "", "amount": amt, "narration": narr, "ref": ref})
    return out


def match_lines(db, lines: list[dict]) -> list[dict]:
    open_links = db.query(models.PaymentLink).filter(models.PaymentLink.status.in_(("created", "partial", "expired"))).all()
    cases = {c.id: c for c in db.query(models.Case).filter(models.Case.id.in_([l.case_id for l in open_links] or [-1]))}
    res = []
    for ln in lines:
        narr = (ln["narration"] or "").upper()
        cand = None; why = ""
        for l in open_links:
            if l.token[:10].upper() in narr or (l.utr and l.utr == ln["ref"]):
                cand, why = l, "reference" if l.token[:10].upper() in narr else "UTR reported by customer"
                break
        if not cand:
            for l in open_links:
                acc = re.sub(r"\D", "", str(getattr(cases.get(l.case_id), "account_no", "") or ""))
                if len(acc) >= 6 and acc[-6:] in re.sub(r"\D", "", narr) and abs(D(l.amount) - D(l.paid_amount) - ln["amount"]) < 1:
                    cand, why = l, "account no + amount"
                    break
        ref = "stmt:" + (ln["ref"] or hashlib.sha1(f"{ln['date']}|{ln['amount']}|{ln['narration']}".encode()).hexdigest()[:20])
        dup = db.query(models.PaymentEvent).filter(models.PaymentEvent.ref == ref).first() is not None
        c = cases.get(cand.case_id) if cand else None
        res.append({**ln, "amount": float(ln["amount"]), "key": ref, "link_id": cand.id if cand else None, "match": why,
                    "case_id": c.id if c else None, "customer": c.customer_name if c else None, "duplicate": dup})
    return res


@router.post("/reconcile/preview")
async def reconcile_preview(file: UploadFile = File(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, OFFICE + ("backend",), "reconciliation")
    data = await file.read()
    if len(data) > 8_000_000:
        raise HTTPException(400, "File too large")
    lines = match_lines(db, parse_statement(file.filename or "x.csv", data))
    return {"lines": lines, "matched": sum(1 for l in lines if l["link_id"] and not l["duplicate"]), "total": len(lines)}


@router.post("/reconcile/apply")
def reconcile_apply(body: dict = Body(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, OFFICE + ("backend",), "reconciliation")
    n = 0
    for ln in body.get("lines") or []:
        if not ln.get("link_id") or not str(ln.get("key", "")).startswith("stmt:"):
            continue
        link = db.get(models.PaymentLink, int(ln["link_id"]))
        if link and _apply(db, link, D(ln.get("amount")), ln["key"], "statement", str(ln.get("ref") or "")):
            n += 1
    audit.record(db, user, "paylink.reconcile", entity_type="settings", detail=f"{n} statement credits applied")
    db.commit()
    return {"applied": n}


# ───────────── customer self-service page (public, token only) ─────────────
def _page(title: str, body: str) -> HTMLResponse:
    brand = html.escape(get_settings().brand_name or "RecoverIQ")
    return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>{html.escape(title)}</title>
<style>body{{font-family:system-ui,Segoe UI,Roboto,sans-serif;background:#eef4ff;margin:0;color:#0f172a}}
.w{{max-width:440px;margin:24px auto;background:#fff;border-radius:16px;box-shadow:0 8px 30px rgba(15,23,42,.12);overflow:hidden}}
.h{{background:#1e3a8a;color:#fff;padding:16px 20px;font-weight:700}} .b{{padding:20px}} .k{{color:#64748b;font-size:13px}}
.v{{font-size:16px;font-weight:600;margin-bottom:10px}} .amt{{font-size:30px;font-weight:800;color:#1e3a8a}}
a.btn,button{{display:block;width:100%;text-align:center;background:#2563eb;color:#fff;border:0;border-radius:10px;padding:14px;font-size:16px;font-weight:700;text-decoration:none;margin-top:12px;cursor:pointer}}
input{{width:100%;box-sizing:border-box;padding:12px;border:1px solid #cbd5e1;border-radius:10px;font-size:15px;margin-top:6px}}
.ok{{background:#dcfce7;color:#166534;padding:12px;border-radius:10px}} .muted{{color:#64748b;font-size:12px;margin-top:14px}}</style></head>
<body><div class="w"><div class="h">{brand} · Secure payment</div><div class="b">{body}</div></div></body></html>""",
                        headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})


def _mask_name(n: str) -> str:
    parts = (n or "").split()
    return " ".join(p[0] + "*" * max(len(p) - 1, 1) if i else p for i, p in enumerate(parts)) if parts else "Customer"


@public.get("/pay/{token}", response_class=HTMLResponse)
def pay_page(token: str, db: Session = Depends(get_db)):
    l = db.query(models.PaymentLink).filter(models.PaymentLink.token == token).first()
    if not l:
        return _page("Link not found", "<p>This payment link is not valid. Please contact your recovery officer.</p>")
    _expire(db, [l]); db.commit()
    case = db.get(models.Case, l.case_id)
    acc = str(getattr(case, "account_no", "") or "")
    due = D(l.amount) - D(l.paid_amount)
    head = (f'<div class="k">Name</div><div class="v">{html.escape(_mask_name(getattr(case, "customer_name", "")))}</div>'
            f'<div class="k">Loan / card account</div><div class="v">{html.escape(getattr(case, "bank", "") or "")} · ending {html.escape(acc[-4:])}</div>')
    if l.status == "paid":
        return _page("Paid", head + f'<div class="ok">✅ Payment of ₹{D(l.paid_amount):,.2f} received. Thank you!</div>')
    if l.status in ("cancelled", "expired"):
        return _page("Link closed", head + f"<p>This link has {l.status}. Please ask your recovery officer for a new one.</p>")
    pay = ""
    if l.provider == "razorpay" and l.short_url:
        pay = f'<a class="btn" href="{html.escape(l.short_url)}">Pay ₹{due:,.2f} securely</a>'
    else:
        s = get_settings()
        upi = (f"upi://pay?pa={html.escape(s.upi_vpa)}&pn={html.escape(s.upi_payee_name or '')}&am={due:.2f}&cu=INR"
               f"&tn={html.escape(l.token[:10])}")
        pay = (f'<a class="btn" href="{upi}">Pay ₹{due:,.2f} with any UPI app</a>'
               f'<div class="muted">UPI id: <b>{html.escape(s.upi_vpa)}</b> · keep the note <b>{html.escape(l.token[:10])}</b> so we can match your payment.</div>')
    utr_form = (f'<form method="post" action="/pay/{html.escape(token)}/utr" style="margin-top:18px">'
                '<div class="k">Already paid? Enter the UTR / reference number</div>'
                '<input name="utr" maxlength="40" pattern="[A-Za-z0-9]{6,40}" required placeholder="e.g. 412345678901">'
                '<button type="submit" style="background:#0f766e">Submit reference</button></form>')
    return _page("Pay", head + f'<div class="k">Amount due</div><div class="amt">₹{due:,.2f}</div>{pay}{utr_form}'
                 '<div class="muted">This page shows only what is needed to pay. Never share your UPI PIN or OTP with anyone.</div>')


@public.post("/pay/{token}/utr", response_class=HTMLResponse)
async def pay_utr(token: str, request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    utr = re.sub(r"[^A-Za-z0-9]", "", str(form.get("utr") or ""))[:40]
    l = db.query(models.PaymentLink).filter(models.PaymentLink.token == token).first()
    if not l or len(utr) < 6:
        return _page("Error", "<p>Please enter a valid reference number.</p>")
    if l.status in ("created", "partial", "expired"):
        l.utr = utr
        case = db.get(models.Case, l.case_id)
        audit.record(db, None, "paylink.utr", case, detail=f"Customer reported UTR {utr} on link #{l.id}")
        try:
            from . import notifications
            from types import SimpleNamespace
            notifications.notify_case_change(db, case, SimpleNamespace(id=None, name="Customer"), f"💳 Customer reported payment, UTR {utr} — verify in reconciliation", ntype="payment")
        except Exception:
            pass
        db.commit()
    return _page("Thank you", '<div class="ok">Thank you — we\'ve noted your reference and will confirm once it reaches us.</div>')
