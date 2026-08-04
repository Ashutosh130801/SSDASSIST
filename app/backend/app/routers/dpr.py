"""DPR (Daily Payment Report) bulk update — portfolio-wise.

Head office uploads a bank's DPR for one bank+product; the app auto-detects the columns
(account/card/loan number, name, amount, paid/unpaid status, NORM/STAB), matches each row to
a case in that portfolio, and shows a PREVIEW. On commit it marks the matched cases Paid (or
Unpaid for reversals) through the same pipeline as manual mark-paid — so MIS, caller/FOS
credit and the resolved list all update. Already-paid rows are skipped, so re-uploading a DPR
never double-counts.
"""
import io
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import audit, models
from ..database import get_db
from ..deps import require_roles
from .cases import _mark_today, _pay_base_total, _scope, propensity

router = APIRouter(prefix="/api/dpr", tags=["dpr"])
DPR_ROLES = ("admin", "headoffice", "manager", "backend")


def _norm(h):
    return "".join(ch for ch in str(h or "").strip().lower() if ch.isalnum())


# Header keywords (normalised) that identify each column's role.
_KEY = {"accountno", "acno", "account", "accountnumber", "acctno", "loanno", "loanaccount",
        "loanaccountno", "loanacno", "lan", "lano", "cardno", "card", "cardnumber", "ccno",
        "agreementno", "agreement", "agreementnumber", "proposalno", "crnno", "crn",
        "loannumber", "loanid", "refno", "referenceno"}
_NAME = {"name", "customer", "cusname", "customername", "custname", "borrower", "borrowername",
         "customersname", "clientname", "accountname"}
_AMT = {"amount", "paidamount", "amountpaid", "cashcoll", "cashcollected", "collected",
        "received", "receivedamount", "settlementamount", "settlement", "payment",
        "paymentamount", "collectionamount", "emipaid", "amountreceived", "paidamt", "amt",
        "collamount", "recoveryamount", "recovery"}
_STAT = {"status", "paid", "paidunpaid", "paymentstatus", "dpstatus", "result", "paystatus",
         "collectionstatus", "recoverystatus"}
_NS = {"normstab", "norm", "stab", "type", "paidat", "settlementtype", "category", "rollback",
       "ns", "paymenttype", "normstabrollback"}
_DATE = {"date", "paymentdate", "txndate", "transactiondate", "paiddate", "collectiondate",
         "depositdate", "valuedate"}


def _read_rows(content: bytes):
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    ws = wb.active
    data = [list(r) for r in ws.iter_rows(values_only=True)]
    if not data:
        return [], []
    known = _KEY | _NAME | _AMT | _STAT | _NS | _DATE
    hdr_i = 0
    for i, r in enumerate(data[:10]):
        if sum(1 for c in r if _norm(c) in known) >= 2:
            hdr_i = i
            break
    headers = [_norm(c) for c in data[hdr_i]]
    rows = []
    for r in data[hdr_i + 1:]:
        if not any(c not in (None, "") for c in r):
            continue
        rows.append({headers[j]: r[j] for j in range(min(len(headers), len(r)))})
    return headers, rows


def _detect(headers):
    cols = {"keys": [], "name": None, "amount": None, "status": None, "ns": None, "date": None}
    for h in headers:
        if not h:
            continue
        if h in _KEY:
            cols["keys"].append(h)
        elif h in _NAME and not cols["name"]:
            cols["name"] = h
        elif h in _AMT and not cols["amount"]:
            cols["amount"] = h
        elif h in _STAT and not cols["status"]:
            cols["status"] = h
        elif h in _NS and not cols["ns"]:
            cols["ns"] = h
        elif h in _DATE and not cols["date"]:
            cols["date"] = h
    return cols


def _dec(v):
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v).replace(",", "").replace("₹", "").strip())
    except (InvalidOperation, ValueError):
        return None


def _keyset(s):
    if s in (None, ""):
        return set()
    up = str(s).strip().upper()
    digits = "".join(ch for ch in up if ch.isdigit())
    return {k for k in (up, digits) if k}


def _is_paid(status_val, amount):
    s = str(status_val or "").strip().upper()
    if any(x in s for x in ("UNPAID", "BOUNCE", "FAIL", "REVERS", "RETURN", "DISHON", "REJECT", "NACHFAIL")):
        return False
    if any(x in s for x in ("PAID", "SUCCESS", "SETTLED", "CLOSED", "COLLECT", "RECEIVED", "YES", "DONE")):
        return True
    return (amount or 0) > 0          # no clear status → paid when an amount is present


def _ns_val(v):
    s = str(v or "").strip().upper()
    if "ROLL" in s:
        return "ROLLBACK"
    if "STAB" in s:
        return "STAB"
    if "NORM" in s:
        return "NORM"
    return None


def _prepare(content, default_bank, product, user, db):
    """Read + detect + match. Returns (cols, items) where each item is a classified row."""
    try:
        headers, rows = _read_rows(content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read the DPR file: {e}")
    cols = _detect(headers)
    if not cols["keys"]:
        raise HTTPException(status_code=400,
                            detail="No account / card / loan number column found in the DPR.")
    q = _scope(db.query(models.Case), user).filter(models.Case.bank == default_bank,
                                                   models.Case.product == product)
    cases = [c for c in q.all() if c.removed is not True]
    lut = {}
    for c in cases:
        for kv in (_keyset(c.account_no) | _keyset(c.card_no)):
            lut.setdefault(kv, c)

    items = []
    for r in rows:
        keyvals = set()
        for kcol in cols["keys"]:
            keyvals |= _keyset(r.get(kcol))
        match = next((lut[kv] for kv in keyvals if kv in lut), None)
        amount = _dec(r.get(cols["amount"])) if cols["amount"] else None
        paid = _is_paid(r.get(cols["status"]) if cols["status"] else None, amount)
        ns = _ns_val(r.get(cols["ns"])) if cols["ns"] else None
        name = r.get(cols["name"]) if cols["name"] else None
        keyshow = next((k for k in keyvals if not k.isdigit()), next(iter(keyvals), "")) if keyvals else ""
        if not match:
            items.append({"action": "unmatched", "key": keyshow, "name": name,
                          "amount": float(amount or 0),
                          "reason": "no case with this number in this portfolio"})
            continue
        already = (match.paid_status or "").upper() == "PAID"
        if paid and already:
            act = "already_paid"
        elif paid:
            act = "mark_paid"
        else:
            act = "mark_unpaid"
        items.append({"action": act, "case_id": match.id, "key": keyshow,
                      "customer": match.customer_name, "amount": float(amount or 0),
                      "norm_stab": ns, "current": match.paid_status,
                      "_case": match, "_amount": amount, "_ns": ns})
    return cols, items


@router.post("/preview")
async def dpr_preview(file: UploadFile = File(...), default_bank: str = Form(...),
                      product: str = Form(...), db: Session = Depends(get_db),
                      user: models.User = Depends(require_roles(*DPR_ROLES))):
    content = await file.read()
    cols, items = _prepare(content, default_bank, product, user, db)
    counts = {"mark_paid": 0, "mark_unpaid": 0, "already_paid": 0, "unmatched": 0}
    for it in items:
        counts[it["action"]] = counts.get(it["action"], 0) + 1
    public = [{k: v for k, v in it.items() if not k.startswith("_")} for it in items]
    return {"bank": default_bank, "product": product, "detected": cols,
            "total": len(items), "counts": counts,
            "rows": public[:500], "capped": len(public) > 500}


@router.post("/commit")
async def dpr_commit(file: UploadFile = File(...), default_bank: str = Form(...),
                     product: str = Form(...), db: Session = Depends(get_db),
                     user: models.User = Depends(require_roles(*DPR_ROLES))):
    content = await file.read()
    cols, items = _prepare(content, default_bank, product, user, db)
    paid_n = unpaid_n = already_n = unmatched_n = 0
    touched = []
    for it in items:
        act = it["action"]
        if act == "unmatched":
            unmatched_n += 1
            continue
        if act == "already_paid":
            already_n += 1
            continue
        case = it["_case"]
        if act == "mark_paid":
            amt = it["_amount"] if (it["_amount"] and it["_amount"] > 0) else (
                _pay_base_total(case) - Decimal(case.received_amount or 0))
            if amt < 0:
                amt = Decimal(0)
            case.received_amount = Decimal(case.received_amount or 0) + amt
            pend = _pay_base_total(case) - Decimal(case.received_amount or 0)
            case.pending_amount = pend if pend > 0 else Decimal(0)
            case.paid_status, case.status, case.follow_up_date = "PAID", "paid", None
            if it["_ns"]:
                case.norm_stab = it["_ns"]
            credit = case.assigned_caller_id or case.assigned_fos_id or user.id
            tag = f" ({it['_ns']})" if it["_ns"] else ""
            db.add(models.CallLog(case_id=case.id, caller_id=credit, disposition="PAID",
                                  ptp_amount=amt, note=f"DPR: paid ₹{amt}{tag}"))
            audit.record(db, user, "paid", case, old="UNPAID", new="PAID",
                         detail=f"DPR bulk paid ₹{amt}{tag}")
            audit.stamp_case(case, user)
            paid_n += 1
            touched.append(case)
        else:  # mark_unpaid (reversal)
            prev = Decimal(case.received_amount or 0)
            case.received_amount = Decimal(0)
            case.pending_amount = _pay_base_total(case)
            case.paid_status, case.status, case.norm_stab = "UNPAID", "allocated", None
            if prev > 0:
                credit = case.assigned_caller_id or case.assigned_fos_id or user.id
                db.add(models.CallLog(case_id=case.id, caller_id=credit, disposition="PAID",
                                      ptp_amount=(-prev), note="DPR: reversed (marked unpaid)"))
            audit.record(db, user, "unpaid", case, old="PAID", new="UNPAID",
                         detail="DPR bulk reversal")
            audit.stamp_case(case, user)
            unpaid_n += 1
            touched.append(case)

    audit.record(db, user, "import", None, entity_type="import",
                 detail=f"DPR update {default_bank}/{product}: {paid_n} paid, {unpaid_n} reversed",
                 meta={"bank": default_bank, "product": product, "paid": paid_n,
                       "unpaid": unpaid_n, "already": already_n, "unmatched": unmatched_n})
    db.commit()
    for c in touched:
        db.refresh(c)
    from .realtime import notify_data_changed
    notify_data_changed(default_bank, product)
    _mark_today(db, touched)
    return {"bank": default_bank, "product": product, "total": len(items),
            "paid": paid_n, "unpaid": unpaid_n, "already_paid": already_n,
            "unmatched": unmatched_n}
