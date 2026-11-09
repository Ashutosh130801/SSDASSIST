"""🤝 Settlement / OTS add-on.

Anyone working a case may propose a one-time settlement (offer amount + optional instalments). The waiver %
decides who must approve (limits set in ⚙️ Services):
   waiver ≤ caller limit      → auto-approved
   waiver ≤ team-lead limit   → a team lead (or above) approves
   waiver ≤ manager/HO limit  → a manager / head office approves
   above that                 → Admin only
Approved offers produce a settlement letter (PDF). Instalments are ticked off as the customer pays; when all
are paid the offer is completed. Offers never change the case balance by themselves — payments still come
through the normal payment / DPR / payment-link flows.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import audit, models
from .. import services as svc
from ..addons_common import CASE_WORKERS, D, case_or_404, need, now_ist, outstanding, scoped_cases
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/api/settlements", tags=["settlements"])
KEY = "settlement"
RANK = {"fos": 0, "telecaller": 0, "backend": 0, "teamlead": 1, "manager": 2, "headoffice": 2, "admin": 3, "techsupport": 3}
NEED_NAME = {1: "teamlead", 2: "manager", 3: "admin"}


def needed_rank(db, waiver_pct: Decimal) -> int:
    c = svc.settings_of(db, KEY)
    if waiver_pct <= D(c.get("caller_max_waiver_pct") or 0):
        return 0
    if waiver_pct <= D(c.get("teamlead_max_waiver_pct") or 0):
        return 1
    if waiver_pct <= D(c.get("manager_max_waiver_pct") or 0):
        return 2
    return 3


def _out(o: models.SettlementOffer, case=None, names=None):
    names = names or {}
    return {"id": o.id, "case_id": o.case_id, "customer": getattr(case, "customer_name", None), "bank": getattr(case, "bank", None),
            "account_no": getattr(case, "account_no", None), "outstanding": float(o.outstanding or 0),
            "offer_amount": float(o.offer_amount or 0), "waiver_pct": float(o.waiver_pct or 0), "installments": o.installments or [],
            "reason": o.reason, "status": o.status, "needs_role": o.needs_role, "created_by": names.get(o.created_by),
            "approved_by": names.get(o.approved_by), "approved_at": o.approved_at, "decision_note": o.decision_note,
            "created_at": o.created_at}


def _names(db, rows):
    ids = {i for o in rows for i in (o.created_by, o.approved_by) if i}
    return {u.id: u.name for u in db.query(models.User).filter(models.User.id.in_(ids or [-1]))}


@router.get("")
def list_offers(status: str = "", db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, CASE_WORKERS, "settlements")
    ids = [i for (i,) in scoped_cases(db, user).with_entities(models.Case.id)]
    q = db.query(models.SettlementOffer).filter(models.SettlementOffer.case_id.in_(ids or [-1]))
    if status:
        q = q.filter(models.SettlementOffer.status == status)
    rows = q.order_by(models.SettlementOffer.created_at.desc()).limit(500).all()
    cases = {c.id: c for c in db.query(models.Case).filter(models.Case.id.in_([o.case_id for o in rows] or [-1]))}
    names = _names(db, rows)
    my = RANK.get(user.role, 0)
    out = []
    for o in rows:
        d = _out(o, cases.get(o.case_id), names)
        d["can_decide"] = o.status == "pending" and my >= RANK.get(o.needs_role or "admin", 3) and o.created_by != user.id
        out.append(d)
    return out


@router.get("/limits")
def limits(db: Session = Depends(get_db), user=Depends(get_current_user)):
    c = svc.settings_of(db, KEY)
    return {"caller": c.get("caller_max_waiver_pct"), "teamlead": c.get("teamlead_max_waiver_pct"),
            "manager": c.get("manager_max_waiver_pct"), "my_rank": RANK.get(user.role, 0)}


@router.post("")
def propose(body: dict = Body(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, CASE_WORKERS, "settlements")
    case = case_or_404(db, user, int(body.get("case_id") or 0))
    out_amt = outstanding(case)          # always from the case — never typed in (the waiver % depends on it)
    offer = D(body.get("offer_amount"))
    if out_amt <= 0:
        raise HTTPException(400, "Outstanding must be more than zero")
    if offer <= 0 or offer > out_amt:
        raise HTTPException(400, "Offer must be more than zero and not above the outstanding")
    if db.query(models.SettlementOffer).filter(models.SettlementOffer.case_id == case.id,
                                               models.SettlementOffer.status.in_(("pending", "approved", "accepted"))).first():
        raise HTTPException(400, "This case already has an open settlement offer")
    inst = []
    total = Decimal(0)
    for i, it in enumerate(body.get("installments") or []):
        try:
            due = date.fromisoformat(str(it.get("due")))
        except ValueError:
            raise HTTPException(400, f"Instalment {i + 1}: date is required")
        a = D(it.get("amount"))
        if a <= 0:
            raise HTTPException(400, f"Instalment {i + 1}: amount must be more than zero")
        inst.append({"due": due.isoformat(), "amount": float(a), "paid": False}); total += a
    if inst and abs(total - offer) > Decimal("1"):
        raise HTTPException(400, f"Instalments add up to ₹{total:,.2f} but the offer is ₹{offer:,.2f}")
    if not inst:
        try:
            due = date.fromisoformat(str(body.get("due") or now_ist().date()))
        except ValueError:
            due = now_ist().date()
        inst = [{"due": due.isoformat(), "amount": float(offer), "paid": False}]
    waiver = ((out_amt - offer) / out_amt * 100).quantize(Decimal("0.01"), ROUND_HALF_UP)
    rank = needed_rank(db, waiver)
    auto = RANK.get(user.role, 0) >= rank and (rank == 0 or user.role == "admin")
    o = models.SettlementOffer(case_id=case.id, outstanding=out_amt, offer_amount=offer, waiver_pct=waiver, installments=inst,
                               reason=(body.get("reason") or "")[:2000], needs_role=NEED_NAME.get(rank, "auto") if rank else "auto",
                               status="approved" if auto else "pending", created_by=user.id,
                               approved_by=user.id if auto else None, approved_at=datetime.now(timezone.utc) if auto else None)
    db.add(o); db.flush()
    audit.record(db, user, "settlement.propose", case, new=str(offer),
                 detail=f"OTS ₹{offer:,.2f} on ₹{out_amt:,.2f} ({waiver}% waiver) — " + ("auto-approved" if auto else f"needs {o.needs_role}"))
    if not auto:
        from .notifications import notify_case_change
        notify_case_change(db, case, user, f"🤝 Settlement ₹{offer:,.0f} ({waiver}% waiver) needs {o.needs_role} approval", ntype="settlement")
    db.commit()
    return _out(o, case, _names(db, [o]))


@router.post("/{oid}/decide")
def decide(oid: int, body: dict = Body(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    o = db.get(models.SettlementOffer, oid)
    if not o:
        raise HTTPException(404, "Offer not found")
    case = case_or_404(db, user, o.case_id)
    if o.status != "pending":
        raise HTTPException(400, f"Offer is already {o.status}")
    if o.created_by == user.id:
        raise HTTPException(403, "You can't approve your own offer")
    if RANK.get(user.role, 0) < RANK.get(o.needs_role or "admin", 3):
        raise HTTPException(403, f"This waiver needs {o.needs_role} approval")
    ok = bool(body.get("approve"))
    o.status = "approved" if ok else "rejected"
    o.approved_by, o.approved_at, o.decision_note = user.id, datetime.now(timezone.utc), (body.get("note") or "")[:1000]
    audit.record(db, user, "settlement.approve" if ok else "settlement.reject", case, detail=f"OTS #{o.id} ₹{o.offer_amount} {o.status}")
    from .notifications import notify_case_change
    notify_case_change(db, case, user, f"🤝 Settlement ₹{D(o.offer_amount):,.0f} {o.status}", ntype="settlement")
    if ok:
        from .. import webhooks_out
        webhooks_out.emit(db, "settlement.approved", {"case_id": case.id, "account_no": case.account_no, "bank": case.bank,
                                                      "offer_amount": float(o.offer_amount), "waiver_pct": float(o.waiver_pct)})
    db.commit()
    return {"ok": True, "status": o.status}


@router.post("/{oid}/status")
def set_status(oid: int, body: dict = Body(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    """accepted (customer agreed) / cancelled; or tick instalments paid → completed when all paid."""
    o = db.get(models.SettlementOffer, oid)
    if not o:
        raise HTTPException(404, "Offer not found")
    case = case_or_404(db, user, o.case_id)
    st = body.get("status")
    if st == "accepted":
        if o.status != "approved":
            raise HTTPException(400, "Only an approved offer can be accepted")
        o.status = "accepted"
    elif st == "cancelled":
        if o.status in ("completed", "cancelled", "rejected"):
            raise HTTPException(400, f"Offer is already {o.status}")
        o.status = "cancelled"
    elif "paid_index" in body:
        if o.status not in ("approved", "accepted"):
            raise HTTPException(400, "Offer is not active")
        inst = [dict(x) for x in (o.installments or [])]
        i = int(body["paid_index"])
        if not 0 <= i < len(inst):
            raise HTTPException(400, "No such instalment")
        inst[i]["paid"] = bool(body.get("paid", True))
        o.installments = inst
        o.status = "completed" if all(x["paid"] for x in inst) else "accepted"
    else:
        raise HTTPException(400, "Nothing to change")
    audit.record(db, user, "settlement.status", case, detail=f"OTS #{o.id} → {o.status}")
    db.commit()
    return {"ok": True, "status": o.status, "installments": o.installments}


@router.get("/{oid}/letter.pdf")
def letter(oid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    o = db.get(models.SettlementOffer, oid)
    if not o:
        raise HTTPException(404, "Offer not found")
    case = case_or_404(db, user, o.case_id)
    if o.status not in ("approved", "accepted", "completed"):
        raise HTTPException(400, "A letter is available once the offer is approved")
    from ..addons_common import company_cfg
    from ..ai_files import _pdf
    pdf = _pdf(company_cfg(db), "One-Time Settlement Offer")
    c = svc.settings_of(db, KEY)
    pdf.set_font("dv", "", 10)
    lines = [f"Ref: OTS/{o.id}/{now_ist():%Y}", f"Date: {now_ist():%d-%b-%Y}", "",
             f"To: {case.customer_name or ''}", f"Account: {case.bank or ''} — {case.account_no or ''}", "",
             "Subject: One-time settlement of your outstanding dues", "",
             f"With reference to your account above, the total outstanding is ₹{D(o.outstanding):,.2f}. "
             f"On your request, a one-time settlement of ₹{D(o.offer_amount):,.2f} is offered, payable as below:", ""]
    for ln in lines:
        pdf.multi_cell(0, 5.5, ln)
    pdf.set_font("dv", "B", 9.5)
    pdf.cell(20, 7, "#", border=1); pdf.cell(60, 7, "Due date", border=1); pdf.cell(60, 7, "Amount (₹)", border=1); pdf.ln()
    pdf.set_font("dv", "", 9.5)
    for i, it in enumerate(o.installments or [], 1):
        pdf.cell(20, 7, str(i), border=1); pdf.cell(60, 7, date.fromisoformat(it["due"]).strftime("%d-%b-%Y"), border=1)
        pdf.cell(60, 7, f"{D(it['amount']):,.2f}", border=1); pdf.ln()
    pdf.ln(4)
    for ln in ["If the payments are not made on the dates above, this offer lapses and the full outstanding becomes payable.",
               "Please pay only through the official channels shared by us and keep the receipts.", "",
               c.get("letter_footer") or "", "", "Authorised signatory"]:
        pdf.multi_cell(0, 5.5, ln)
    audit.record(db, user, "download", case, detail=f"Settlement letter OTS #{o.id}")
    db.commit()
    return Response(bytes(pdf.output()), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="OTS_{o.id}.pdf"'})
