"""🧾 Agency billing & invoices add-on (Admin / Head Office).

Commission rates per bank (optionally per product and bucket):
   percent  — % of the amount collected in the month
   per_case — fixed ₹ per case that ended the month PAID
   fixed    — fixed ₹ per month (retainer)
The most specific rate wins (bank+product+bucket > bank+product > bank).
An invoice for a bank + month is drafted from that month's cases, can be edited, then issued (number locked)
and marked paid. GST is added at the rate set in ⚙️ Services (CGST+SGST split shown when the place of supply
is the same state — set "same_state" on the invoice).
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import audit, models
from .. import services as svc
from ..addons_common import D, company_cfg, need
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/api/billing", tags=["billing"])
KEY = "billing"
WHO = ("admin", "headoffice")
BASES = ("percent", "per_case", "fixed")
Q = Decimal("0.01")


def _r(x) -> Decimal:
    return D(x).quantize(Q, ROUND_HALF_UP)


@router.get("/rates")
def rates(db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, WHO, "billing")
    return [{"id": r.id, "bank": r.bank, "product": r.product, "bucket": r.bucket, "basis": r.basis, "rate": float(r.rate or 0),
             "note": r.note} for r in db.query(models.BillingRate).order_by(models.BillingRate.bank, models.BillingRate.product).all()]


@router.post("/rates")
def save_rate(body: dict = Body(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, WHO, "billing")
    bank = (body.get("bank") or "").strip().upper()
    if not bank:
        raise HTTPException(400, "Bank is required")
    if body.get("basis") not in BASES:
        raise HTTPException(400, "Basis must be percent, per_case or fixed")
    rate = D(body.get("rate"))
    if rate < 0 or (body["basis"] == "percent" and rate > 100):
        raise HTTPException(400, "Rate is out of range")
    r = db.get(models.BillingRate, int(body["id"])) if body.get("id") else models.BillingRate()
    if r is None:
        raise HTTPException(404, "Rate not found")
    r.bank, r.product, r.bucket = bank, (body.get("product") or "").strip() or None, (body.get("bucket") or "").strip() or None
    r.basis, r.rate, r.note = body["basis"], rate, (body.get("note") or "")[:200]
    db.add(r)
    audit.record(db, user, "billing.rate", entity_type="settings", detail=f"{bank} {r.product or 'all'} {r.bucket or ''} {r.basis} {rate}")
    db.commit()
    return {"id": r.id}


@router.delete("/rates/{rid}")
def del_rate(rid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, WHO, "billing")
    r = db.get(models.BillingRate, rid)
    if not r:
        raise HTTPException(404, "Rate not found")
    db.delete(r); db.commit()
    return {"ok": True}


def _pick(rates, prod, bkt):
    best, score = None, -1
    for r in rates:
        if r.basis == "fixed":
            continue
        if r.product and r.product != prod:
            continue
        if r.bucket and r.bucket != bkt:
            continue
        s = (2 if r.product else 0) + (1 if r.bucket else 0)
        if s > score:
            best, score = r, s
    return best


def compute_lines(db, bank: str, period: str) -> list[dict]:
    rates = db.query(models.BillingRate).filter(func.upper(models.BillingRate.bank) == bank.upper()).all()
    if not rates:
        raise HTTPException(400, f"No commission rates set for {bank}")
    cases = db.query(models.Case).filter(func.upper(models.Case.bank) == bank.upper(), models.Case.period == period,
                                         models.Case.removed.isnot(True)).all()
    groups = {}
    for c in cases:
        r = _pick(rates, c.product, c.bucket)
        if not r:
            continue
        k = (r.id, c.product or "—", c.bucket or "—")
        g = groups.setdefault(k, {"rate": r, "product": c.product or "—", "bucket": c.bucket or "—", "cases": 0, "paid": 0, "collected": D(0)})
        g["cases"] += 1
        g["paid"] += (c.paid_status or "").upper() == "PAID"
        g["collected"] += D(c.received_amount)
    lines = []
    for g in groups.values():
        r = g["rate"]
        if r.basis == "percent":
            base, amt, desc = g["collected"], _r(g["collected"] * D(r.rate) / 100), f"{D(r.rate)}% of collection"
        else:
            base, amt, desc = Decimal(g["paid"]), _r(D(g["paid"]) * D(r.rate)), f"₹{D(r.rate)} per paid case"
        if amt <= 0:
            continue
        lines.append({"description": f"{bank} {g['product']} {g['bucket']} — {desc}", "cases": g["cases"], "paid_cases": g["paid"],
                      "collected": float(g["collected"]), "basis": r.basis, "rate": float(r.rate), "base": float(base), "amount": float(amt)})
    for r in rates:
        if r.basis == "fixed" and D(r.rate) > 0:
            lines.append({"description": f"{bank} {r.product or ''} monthly fee".replace("  ", " "), "cases": 0, "paid_cases": 0,
                          "collected": 0, "basis": "fixed", "rate": float(r.rate), "base": 1, "amount": float(_r(r.rate))})
    return lines


def _totals(inv: models.Invoice):
    sub = sum((D(l["amount"]) for l in inv.lines or []), Decimal(0))
    inv.subtotal = _r(sub)
    inv.gst = _r(sub * D(inv.gst_rate) / 100)
    inv.total = _r(inv.subtotal + inv.gst)


def _inv(i: models.Invoice):
    return {"id": i.id, "number": i.number, "bank": i.bank, "period": i.period, "lines": i.lines or [], "subtotal": float(i.subtotal or 0),
            "gst_rate": float(i.gst_rate or 0), "gst": float(i.gst or 0), "total": float(i.total or 0), "status": i.status,
            "bill_to": i.bill_to, "issued_at": i.issued_at, "paid_at": i.paid_at, "created_at": i.created_at}


@router.get("/invoices")
def invoices(db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, WHO, "billing")
    rows = db.query(models.Invoice).order_by(models.Invoice.id.desc()).limit(300).all()
    return [_inv(i) for i in rows]


@router.post("/invoices/preview")
def preview(body: dict = Body(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, WHO, "billing")
    lines = compute_lines(db, body.get("bank") or "", body.get("period") or "")
    sub = sum(D(l["amount"]) for l in lines)
    g = D(svc.settings_of(db, KEY).get("gst_rate") or 18)
    return {"lines": lines, "subtotal": float(_r(sub)), "gst": float(_r(sub * g / 100)), "total": float(_r(sub + sub * g / 100))}


@router.post("/invoices")
def create_invoice(body: dict = Body(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, WHO, "billing")
    bank, per = (body.get("bank") or "").upper(), body.get("period") or ""
    if not bank or len(per) != 7:
        raise HTTPException(400, "Bank and month (YYYY-MM) are required")
    if db.query(models.Invoice).filter(models.Invoice.bank == bank, models.Invoice.period == per,
                                       models.Invoice.status != "cancelled").first():
        raise HTTPException(400, f"An invoice for {bank} {per} already exists")
    lines = body.get("lines") or compute_lines(db, bank, per)
    inv = models.Invoice(bank=bank, period=per, lines=[{"description": str(l["description"])[:200], "amount": float(_r(l["amount"])),
                                                        **{k: l.get(k) for k in ("cases", "paid_cases", "collected", "basis", "rate", "base")}}
                                                       for l in lines],
                         gst_rate=D(svc.settings_of(db, KEY).get("gst_rate") or 18), bill_to=(body.get("bill_to") or "")[:1000],
                         status="draft", created_by=user.id)
    _totals(inv)
    db.add(inv); db.flush()
    inv.number = f"DRAFT-{inv.id}"
    audit.record(db, user, "billing.invoice", entity_type="settings", detail=f"Draft invoice {bank} {per} ₹{inv.total}")
    db.commit()
    return _inv(inv)


@router.put("/invoices/{iid}")
def edit_invoice(iid: int, body: dict = Body(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, WHO, "billing")
    inv = db.get(models.Invoice, iid)
    if not inv or inv.status != "draft":
        raise HTTPException(400, "Only a draft invoice can be edited")
    if "lines" in body:
        lines = []
        for l in body["lines"]:
            if not str(l.get("description") or "").strip():
                raise HTTPException(400, "Every line needs a description")
            lines.append({**l, "description": str(l["description"])[:200], "amount": float(_r(l.get("amount")))})
        inv.lines = lines
    if "bill_to" in body:
        inv.bill_to = (body["bill_to"] or "")[:1000]
    if "gst_rate" in body:
        inv.gst_rate = D(body["gst_rate"])
    _totals(inv)
    db.commit()
    return _inv(inv)


@router.post("/invoices/{iid}/status")
def invoice_status(iid: int, body: dict = Body(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, WHO, "billing")
    inv = db.get(models.Invoice, iid)
    if not inv:
        raise HTTPException(404, "Invoice not found")
    st = body.get("status")
    now = datetime.now(timezone.utc)
    if st == "issued" and inv.status == "draft":
        c = svc.settings_of(db, KEY)
        pre = (c.get("invoice_prefix") or "INV").strip()[:10]
        y = int(inv.period[:4]); m = int(inv.period[5:7])
        fy = f"{y if m >= 4 else y - 1}-{str((y + 1 if m >= 4 else y) % 100).zfill(2)}"
        n = db.query(models.Invoice).filter(models.Invoice.number.like(f"{pre}/{fy}/%")).count() + 1
        inv.number, inv.status, inv.issued_at = f"{pre}/{fy}/{n:04d}", "issued", now
    elif st == "paid" and inv.status == "issued":
        inv.status, inv.paid_at = "paid", now
    elif st == "cancelled" and inv.status in ("draft", "issued"):
        inv.status = "cancelled"
    else:
        raise HTTPException(400, f"Can't move a {inv.status} invoice to {st}")
    audit.record(db, user, "billing.invoice_status", entity_type="settings", detail=f"{inv.number} → {inv.status}")
    db.commit()
    return _inv(inv)


@router.get("/invoices/{iid}.pdf")
def invoice_pdf(iid: int, same_state: bool = True, db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, WHO, "billing")
    inv = db.get(models.Invoice, iid)
    if not inv:
        raise HTTPException(404, "Invoice not found")
    cfg = company_cfg(db)
    co = cfg.get("company") or {}
    c = svc.settings_of(db, KEY)
    from ..ai_files import _pdf
    from ..payroll_engine import words_inr
    pdf = _pdf(cfg, "TAX INVOICE" if inv.status != "draft" else "DRAFT INVOICE")
    pdf.set_font("dv", "", 9)
    left = [co.get("name") or "", co.get("address") or "", f"GSTIN: {c.get('gstin') or '—'}", f"PAN: {co.get('pan') or '—'}"]
    right = [f"Invoice no: {inv.number}", f"Date: {(inv.issued_at or inv.created_at or datetime.now()).strftime('%d-%b-%Y')}",
             f"Period: {inv.period}", f"Status: {inv.status.upper()}"]
    y = pdf.get_y()
    pdf.multi_cell(100, 5, "\n".join(left)); y2 = pdf.get_y()
    pdf.set_xy(120, y); pdf.multi_cell(80, 5, "\n".join(right))
    pdf.set_y(max(y2, pdf.get_y()) + 3)
    pdf.set_font("dv", "B", 9); pdf.cell(0, 5, "Bill to:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("dv", "", 9); pdf.multi_cell(0, 5, inv.bill_to or inv.bank); pdf.ln(3)
    pdf.set_font("dv", "B", 8.5); pdf.set_fill_color(30, 58, 138); pdf.set_text_color(255, 255, 255)
    for w, h in ((10, "#"), (110, "Description"), (25, "Base"), (40, "Amount (₹)")):
        pdf.cell(w, 7, h, fill=True)
    pdf.ln(); pdf.set_text_color(15, 23, 42); pdf.set_font("dv", "", 8.5)
    for i, l in enumerate(inv.lines or [], 1):
        base = l.get("base")
        btxt = f"₹{D(base):,.0f}" if l.get("basis") == "percent" else (f"{int(D(base))} cases" if l.get("basis") == "per_case" else "")
        pdf.cell(10, 6, str(i)); pdf.cell(110, 6, str(l["description"])[:70]); pdf.cell(25, 6, btxt)
        pdf.cell(40, 6, f"{D(l['amount']):,.2f}", align="R"); pdf.ln()
    pdf.ln(2); pdf.set_font("dv", "", 9)
    def row(lbl, v, bold=False):
        pdf.set_font("dv", "B" if bold else "", 9); pdf.cell(145, 6, lbl, align="R"); pdf.cell(40, 6, f"{D(v):,.2f}", align="R"); pdf.ln()
    row("Taxable value", inv.subtotal)
    if same_state:
        half = _r(D(inv.gst) / 2)
        row(f"CGST @ {D(inv.gst_rate) / 2}%", half); row(f"SGST @ {D(inv.gst_rate) / 2}%", D(inv.gst) - half)
    else:
        row(f"IGST @ {D(inv.gst_rate)}%", inv.gst)
    row("Total", inv.total, True)
    pdf.ln(2); pdf.set_font("dv", "", 8.5)
    try:
        pdf.multi_cell(0, 5, "Amount in words: " + words_inr(D(inv.total)))
    except Exception:
        pass
    pdf.ln(8); pdf.multi_cell(0, 5, f"For {co.get('name') or ''}\n\n\nAuthorised signatory")
    audit.record(db, user, "download", entity_type="settings", detail=f"Invoice {inv.number} PDF")
    db.commit()
    return Response(bytes(pdf.output()), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{inv.number.replace("/", "-")}.pdf"'})
