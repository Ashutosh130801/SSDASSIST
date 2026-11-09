"""📨 Legal notices (bulk) add-on.

Pick cases (by ids or by filters) + a notice template → one PDF with one notice per page, each with its own
reference number. Then track dispatch (Speed Post / courier / email / hand) and delivery, by hand or by
uploading the post-office tracking sheet. Every notice is written to the case history.

Templates use placeholders: {name} {address} {pincode} {bank} {account_no} {product} {outstanding} {date}
{reply_days} {reply_by} {ref_no} {company} {signatory}
"""
from __future__ import annotations

import io
from datetime import date, timedelta

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import audit, models
from .. import services as svc
from ..addons_common import OFFICE, company_cfg, need, now_ist, outstanding, scoped_cases
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/api/notices", tags=["notices"])
KEY = "legal_notices"
STATUSES = ("generated", "dispatched", "delivered", "returned")
MODES = ("speed_post", "courier", "email", "hand", "registered_post")

TEMPLATES = {
    "demand": {"name": "Demand notice", "subject": "Demand notice for payment of outstanding dues",
               "body": "Dear {name},\n\nYou have availed a {product} facility from {bank} under account {account_no}. "
                       "As per the records, a sum of ₹{outstanding} is outstanding and overdue.\n\n"
                       "You are hereby called upon to pay the said amount within {reply_days} days of receipt of this notice, "
                       "i.e. on or before {reply_by}, or contact us to discuss a repayment arrangement.\n\n"
                       "If the dues are not cleared within this time, the lender may initiate appropriate legal proceedings "
                       "as permitted by law, at your cost and risk.\n\nPlease ignore this notice if you have already paid."},
    "sec138": {"name": "Sec 138 NI Act (cheque bounce)", "subject": "Legal notice under Section 138 of the Negotiable Instruments Act, 1881",
               "body": "Dear {name},\n\nThe cheque issued by you towards repayment of your {bank} account {account_no} was returned "
                       "unpaid by your banker. The amount of ₹{outstanding} remains payable.\n\n"
                       "You are hereby called upon to pay the said amount within 15 days of receipt of this notice. Failing payment, "
                       "the lender will be constrained to file a complaint under Section 138 of the Negotiable Instruments Act, 1881."},
    "arbitration": {"name": "Pre-arbitration / conciliation", "subject": "Notice invoking arbitration under the loan agreement",
                    "body": "Dear {name},\n\nDisputes have arisen under your loan agreement with {bank} (account {account_no}) on account "
                            "of non-payment of ₹{outstanding}. In terms of the arbitration clause of the agreement, the lender intends to "
                            "refer the dispute to arbitration.\n\nYou may settle the dues or contact us within {reply_days} days "
                            "(by {reply_by}) to resolve the matter amicably before the reference is made."},
    "pre_sarfaesi": {"name": "Pre-SARFAESI reminder", "subject": "Reminder before action under the SARFAESI Act, 2002",
                     "body": "Dear {name},\n\nYour secured loan account {account_no} with {bank} is overdue with ₹{outstanding} outstanding. "
                             "Please regularise the account within {reply_days} days (by {reply_by}) to avoid classification as a "
                             "non-performing asset and further action under the SARFAESI Act, 2002."},
}


def _fill(text, case, ref, reply_days, sign, comp):
    reply_by = (now_ist().date() + timedelta(days=reply_days)).strftime("%d-%b-%Y")
    addr = ", ".join(x for x in (case.address_clean or case.address, case.address2) if x)
    vals = {"name": case.customer_name or "", "address": addr, "pincode": case.pincode or "", "bank": case.bank or "",
            "account_no": case.account_no or "", "product": case.product or "loan", "outstanding": f"{outstanding(case):,.2f}",
            "date": now_ist().strftime("%d-%b-%Y"), "reply_days": str(reply_days), "reply_by": reply_by, "ref_no": ref,
            "company": comp, "signatory": sign}
    for k, v in vals.items():
        text = text.replace("{" + k + "}", v)
    return text


@router.get("/templates")
def templates(db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, OFFICE, "legal notices")
    return [{"kind": k, **v} for k, v in TEMPLATES.items()]


def _select(db, user, body):
    q = scoped_cases(db, user)
    ids = [int(i) for i in body.get("case_ids") or []]
    if ids:
        q = q.filter(models.Case.id.in_(ids))
    else:
        f = body.get("filters") or {}
        if not any(f.get(k) for k in ("bank", "product", "bucket", "branch", "disposition")):
            raise HTTPException(400, "Pick cases or at least one filter")
        if f.get("bank"):
            q = q.filter(models.Case.bank == f["bank"])
        if f.get("product"):
            q = q.filter(models.Case.product == f["product"])
        if f.get("bucket"):
            q = q.filter(models.Case.bucket == f["bucket"])
        if f.get("branch"):
            q = q.filter(func.upper(models.Case.branch) == str(f["branch"]).upper())
        if f.get("disposition"):
            q = q.filter(func.upper(models.Case.disposition) == str(f["disposition"]).upper())
        q = q.filter(func.upper(func.coalesce(models.Case.paid_status, "UNPAID")) != "PAID")
    return q.limit(5000).all()


@router.post("/preview")
def preview(body: dict = Body(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, OFFICE, "legal notices")
    cases = _select(db, user, body)
    no_addr = sum(1 for c in cases if not (c.address or c.address_clean))
    return {"count": len(cases), "without_address": no_addr,
            "sample": [{"case_id": c.id, "customer": c.customer_name, "outstanding": float(outstanding(c))} for c in cases[:10]]}


@router.post("/batches")
def create_batch(body: dict = Body(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, OFFICE, "legal notices")
    kind = body.get("kind") or "demand"
    tpl = TEMPLATES.get(kind, {})
    subject = (body.get("subject") or tpl.get("subject") or "").strip()
    text = (body.get("body") or tpl.get("body") or "").strip()
    if not subject or not text:
        raise HTTPException(400, "Subject and notice text are required")
    cases = [c for c in _select(db, user, body) if (c.address or c.address_clean)]
    if not cases:
        raise HTTPException(400, "No selected case has an address")
    b = models.NoticeBatch(name=(body.get("name") or f"{tpl.get('name', 'Notice')} {now_ist():%d-%b-%Y}")[:160], kind=kind,
                           subject=subject[:200], body=text[:8000], count=len(cases), created_by=user.id)
    db.add(b); db.flush()
    yr = now_ist().strftime("%Y%m")
    for c in cases:
        n = models.LegalNotice(batch_id=b.id, case_id=c.id, ref_no=f"LN/{yr}/{b.id}/{c.id}")
        db.add(n)
        audit.record(db, user, "notice.generated", c, detail=f"{tpl.get('name', kind)} — {n.ref_no}")
    db.commit()
    return {"id": b.id, "count": len(cases)}


@router.get("/batches")
def batches(db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, OFFICE, "legal notices")
    rows = db.query(models.NoticeBatch).order_by(models.NoticeBatch.id.desc()).limit(200).all()
    st = defaultdict_count(db)
    return [{"id": b.id, "name": b.name, "kind": b.kind, "count": b.count, "created_at": b.created_at, "status": st.get(b.id, {})} for b in rows]


def defaultdict_count(db):
    out = {}
    for bid, s, n in db.query(models.LegalNotice.batch_id, models.LegalNotice.status, func.count()) \
            .group_by(models.LegalNotice.batch_id, models.LegalNotice.status).all():
        out.setdefault(bid, {})[s] = n
    return out


def _batch_cases(db, user, bid):
    b = db.get(models.NoticeBatch, bid)
    if not b:
        raise HTTPException(404, "Batch not found")
    allowed = {i for (i,) in scoped_cases(db, user, all_periods=True).with_entities(models.Case.id)}
    ns = [n for n in db.query(models.LegalNotice).filter(models.LegalNotice.batch_id == bid).all() if n.case_id in allowed]
    cases = {c.id: c for c in db.query(models.Case).filter(models.Case.id.in_([n.case_id for n in ns] or [-1]))}
    return b, ns, cases


@router.get("/batches/{bid}")
def batch_detail(bid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, OFFICE, "legal notices")
    b, ns, cases = _batch_cases(db, user, bid)
    return {"id": b.id, "name": b.name, "kind": b.kind, "subject": b.subject,
            "notices": [{"id": n.id, "ref_no": n.ref_no, "case_id": n.case_id, "customer": getattr(cases.get(n.case_id), "customer_name", ""),
                         "status": n.status, "mode": n.mode, "tracking_no": n.tracking_no, "dispatched_at": n.dispatched_at,
                         "delivered_at": n.delivered_at, "note": n.note} for n in ns]}


@router.get("/batches/{bid}/pdf")
def batch_pdf(bid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, OFFICE, "legal notices")
    b, ns, cases = _batch_cases(db, user, bid)
    cfg = company_cfg(db)
    c = svc.settings_of(db, KEY)
    comp = (cfg.get("company") or {}).get("name") or ""
    sign = c.get("signatory") or "Authorised signatory"
    days = int(c.get("reply_days") or 15)
    from ..ai_files import _pdf
    pdf = None
    for n in ns:
        case = cases.get(n.case_id)
        if not case:
            continue
        if pdf is None:
            pdf = _pdf(cfg, b.subject[:80])
        else:
            pdf.add_page(); pdf.set_y(15)
        pdf.set_font("dv", "", 9.5)
        pdf.cell(0, 5, f"Ref: {n.ref_no}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 5, f"Date: {now_ist():%d-%b-%Y}", new_x="LMARGIN", new_y="NEXT"); pdf.ln(3)
        pdf.set_font("dv", "B", 10); pdf.multi_cell(0, 5, "To,\n" + (case.customer_name or ""))
        pdf.set_font("dv", "", 9.5)
        pdf.multi_cell(0, 5, ", ".join(x for x in (case.address_clean or case.address, case.address2) if x) +
                       (f" – {case.pincode}" if case.pincode else ""))
        pdf.ln(3); pdf.set_font("dv", "B", 10); pdf.multi_cell(0, 5, "Subject: " + b.subject); pdf.ln(2)
        pdf.set_font("dv", "", 10)
        pdf.multi_cell(0, 5.5, _fill(b.body, case, n.ref_no, days, sign, comp))
        pdf.ln(10); pdf.set_font("dv", "B", 10)
        pdf.multi_cell(0, 5, f"For {comp}\n\n\n{sign}" if comp else sign)
    if pdf is None:
        raise HTTPException(400, "No notices in your scope in this batch")
    audit.record(db, user, "download", entity_type="settings", detail=f"Legal notices batch #{b.id} PDF ({len(ns)})")
    db.commit()
    return Response(bytes(pdf.output()), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="notices_{b.id}.pdf"'})


def _set(db, user, n: models.LegalNotice, st, mode=None, tracking=None, on=None, note=None):
    if st not in STATUSES:
        raise HTTPException(400, "Status must be generated, dispatched, delivered or returned")
    if mode and mode not in MODES:
        raise HTTPException(400, "Mode must be speed_post, registered_post, courier, email or hand")
    n.status = st
    if mode:
        n.mode = mode
    if tracking:
        n.tracking_no = str(tracking)[:60]
    d = on or now_ist().date()
    if st == "dispatched":
        n.dispatched_at = d
    if st in ("delivered", "returned"):
        n.delivered_at = d
    if note:
        n.note = str(note)[:300]
    case = db.get(models.Case, n.case_id)
    audit.record(db, user, f"notice.{st}", case, detail=f"{n.ref_no} {st}" + (f" via {n.mode}" if n.mode else "") +
                 (f" #{n.tracking_no}" if n.tracking_no else "") + (f" — {note}" if note else ""))


@router.post("/{nid}/status")
def set_status(nid: int, body: dict = Body(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, OFFICE, "legal notices")
    n = db.get(models.LegalNotice, nid)
    if not n:
        raise HTTPException(404, "Notice not found")
    if not scoped_cases(db, user, all_periods=True).filter(models.Case.id == n.case_id).first():
        raise HTTPException(404, "Notice not found")
    on = date.fromisoformat(body["date"]) if body.get("date") else None
    _set(db, user, n, body.get("status"), body.get("mode"), body.get("tracking_no"), on, body.get("note"))
    db.commit()
    return {"ok": True}


@router.post("/batches/{bid}/tracking")
async def upload_tracking(bid: int, file: UploadFile = File(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Excel with columns: Ref No, Status (dispatched/delivered/returned), Mode, Tracking No, Date, Note."""
    need(user, OFFICE, "legal notices")
    b, ns, _ = _batch_cases(db, user, bid)
    by_ref = {n.ref_no.upper(): n for n in ns}
    from openpyxl import load_workbook
    try:
        ws = load_workbook(io.BytesIO(await file.read()), read_only=True, data_only=True).active
    except Exception:
        raise HTTPException(400, "Upload an .xlsx file")
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise HTTPException(400, "Empty file")
    hi = next((i for i, r in enumerate(rows[:10]) if any("ref" in str(c or "").lower() for c in r)), 0)
    head = [str(h or "").strip().lower() for h in rows[hi]]
    rows = rows[hi:]
    def col(*w):
        for k in w:
            for j, h in enumerate(head):
                if k in h:
                    return j
        return None
    jr, js, jm, jt, jd, jn = col("ref"), col("status"), col("mode"), col("tracking", "awb", "article"), col("date"), col("note", "remark")
    if jr is None or js is None:
        raise HTTPException(400, "Need at least 'Ref No' and 'Status' columns")
    done, bad = 0, []
    for i, r in enumerate(rows[1:], hi + 2):
        ref = str(r[jr] or "").strip().upper()
        if not ref:
            continue
        n = by_ref.get(ref)
        st = str(r[js] or "").strip().lower()
        if not n or st not in STATUSES:
            bad.append(f"row {i}: {'unknown ref' if not n else 'bad status'}"); continue
        mode = str(r[jm] or "").strip().lower().replace(" ", "_") if jm is not None else None
        on = r[jd] if jd is not None and hasattr(r[jd], "year") else None
        if on is not None and hasattr(on, "date"):
            on = on.date()
        try:
            _set(db, user, n, st, mode if mode in MODES else None, r[jt] if jt is not None else None, on, r[jn] if jn is not None else None)
            done += 1
        except HTTPException as e:
            bad.append(f"row {i}: {e.detail}")
    db.commit()
    return {"updated": done, "errors": bad[:50]}


@router.get("/tracking-template.xlsx")
def tracking_template(bid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, OFFICE, "legal notices")
    b, ns, cases = _batch_cases(db, user, bid)
    from ..ai_files import table_xlsx
    rows = [{"ref_no": n.ref_no, "customer": getattr(cases.get(n.case_id), "customer_name", ""), "status": n.status,
             "mode": n.mode or "speed_post", "tracking_no": n.tracking_no or "", "date": "", "note": ""} for n in ns]
    data = table_xlsx(f"Notice tracking — {b.name}", ["ref_no", "customer", "status", "mode", "tracking_no", "date", "note"], rows)
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="notice_tracking_{b.id}.xlsx"'})
