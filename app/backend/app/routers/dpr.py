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
DPR_ROLES = ("admin", "headoffice", "manager", "backend", "teamlead")


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

# Full-sync field map: any of these columns, if present in the DPR, updates the matching
# case field (only when the cell has a value — blanks never wipe existing data). Payment
# columns (amount/status/norm-stab) are handled by the payment pipeline, not here.
# kind: s = short string, t = text, d = decimal/number, dt = date.
_FIELD_SPECS = [
    ("customer_name", _NAME, "s", 160),
    ("phone", {"phone", "mobile", "mobileno", "phoneno", "contactno", "contact",
               "contactnumber", "phone1", "mobile1", "primaryphone", "cell", "mobilenumber"}, "s", 20),
    ("alt_phone", {"altphone", "alternatephone", "alternatemobile", "phone2", "mobile2",
                   "altmobile", "altcontact", "secondaryphone", "alternatenumber"}, "s", 20),
    ("new_phone", {"newphone", "newmobile", "updatedphone", "updatedmobile", "revisedphone",
                   "newcontact", "newnumber", "updatedcontact"}, "s", 20),
    ("address", {"address", "add1", "addr", "add", "customeraddress", "residenceaddress",
                 "resiaddress", "communicationaddress", "address1", "custaddress"}, "t", None),
    ("new_address", {"newaddress", "updatedaddress", "revisedaddress", "newadd", "currentaddress"}, "t", None),
    ("pincode", {"pincode", "pin", "zip", "zipcode", "postalcode"}, "s", 10),
    ("bucket", {"bucket", "bkt", "dpdbucket", "bucketname"}, "s", 30),
    ("cycle", {"cycle", "cyc", "cycledate"}, "s", 10),
    ("total_outstanding", {"tos", "totaloutstanding", "totalos", "outstanding", "outstandingamount",
                           "currbal", "currentbalance", "currentoutstanding", "ledgerbalance", "tob",
                           "totaloutstandingbalance", "balanceoutstanding", "totalod"}, "d", None),
    ("principal_outstanding", {"pos", "principaloutstanding", "principal", "principalos",
                               "principalbalance", "prinos", "pob"}, "d", None),
    ("min_amount_due", {"mad", "minamountdue", "minimumamountdue", "mindue", "minamt",
                        "minimumdue", "minimumamount"}, "d", None),
    ("funding_amount", {"funding", "fundingamount", "fundamount", "committedamount",
                        "committed", "targetamount"}, "d", None),
    ("enr", {"enr", "endnetreceivable", "endnetreceivables", "netreceivable", "netreceivables"}, "d", None),
    ("norm_amount", {"normamount", "odnorm", "odnormamount", "normtarget", "normvalue"}, "d", None),
    ("stab_amount", {"stabamount", "odstab", "odstabamount", "stabtarget", "stabvalue"}, "d", None),
    ("rollback_amount", {"rollbackamount", "odrollback", "rollbacktarget", "rollbackvalue"}, "d", None),
    ("caller_name", {"caller", "callername", "tccaller", "telecaller"}, "s", 80),
    ("fos_name", {"fos", "fosname", "fieldofficer", "fieldexecutive", "fename"}, "s", 120),
    ("team", {"area", "areacode", "region", "zone"}, "s", 40),
    ("team_lead", {"teamlead", "tlname", "teamleadname", "supervisor"}, "s", 40),
    ("cat", {"cat", "catallo", "catcode", "catallocation"}, "s", 20),
    ("disposition", {"disposition", "dispo", "dispocode", "dispositioncode", "dispositionstatus"}, "s", 60),
    ("remarks", {"remarks", "remark", "comment", "comments", "note", "notes", "feedback", "observation"}, "t", None),
    ("follow_up_date", {"ptpdate", "followupdate", "nextfollowup", "promisedate", "promiseddate",
                        "ptpdt", "nextactiondate"}, "dt", None),
]


def _coerce(kind, v):
    """Convert a raw cell to the case-field type; None means 'no value / skip'."""
    import datetime as _dt
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if kind == "d":
        return _dec(v)
    if kind == "dt":
        if isinstance(v, _dt.datetime):
            return v.date()
        if isinstance(v, _dt.date):
            return v
        s = str(v).strip()
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%d-%b-%Y",
                    "%d %b %Y", "%Y/%m/%d", "%d.%m.%Y"):
            try:
                return _dt.datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        return None
    return str(v).strip() or None


def _detect_fields(headers):
    """Map each recognised extra column to a case field: {attr: (header, kind, maxlen)}."""
    present = [h for h in headers if h]
    out = {}
    for attr, aliases, kind, maxlen in _FIELD_SPECS:
        for h in present:
            if h in aliases and attr not in out:
                out[attr] = (h, kind, maxlen)
                break
    return out


def _proposed_fields(case, row, field_cols):
    """Return {attr: new_value} for columns present with a value that differs from the case."""
    import datetime as _dt
    ups = {}
    for attr, (h, kind, maxlen) in field_cols.items():
        val = _coerce(kind, row.get(h))
        if val is None:
            continue
        if kind in ("s", "t") and maxlen:
            val = val[:maxlen]
        old = getattr(case, attr, None)
        if kind == "d":
            if old is not None and _dec(old) == val:
                continue
        elif kind == "dt":
            oldd = old.date() if isinstance(old, _dt.datetime) else old
            if oldd == val:
                continue
        else:
            if (str(old).strip() if old is not None else "") == val:
                continue
        ups[attr] = val
    return ups


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
    field_cols = _detect_fields(headers)
    cols["fields"] = {attr: h for attr, (h, _k, _m) in field_cols.items()}
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
        field_ups = _proposed_fields(match, r, field_cols)
        items.append({"action": act, "case_id": match.id, "key": keyshow,
                      "customer": match.customer_name, "amount": float(amount or 0),
                      "norm_stab": ns, "current": match.paid_status,
                      "updates": {k: str(v) for k, v in field_ups.items()},
                      "_case": match, "_amount": amount, "_ns": ns, "_fields": field_ups})
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
    counts["field_updates"] = sum(len(it.get("_fields") or {}) for it in items)
    counts["rows_with_updates"] = sum(1 for it in items if it.get("_fields"))
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
    paid_n = unpaid_n = already_n = unmatched_n = fields_n = 0
    touched = []

    def _touch(c):
        if c not in touched:
            touched.append(c)

    for it in items:
        act = it["action"]
        if act == "unmatched":
            unmatched_n += 1
            continue
        case = it["_case"]
        # Snapshot the collection base BEFORE any full-sync field overwrite, so a balance/TOS
        # column in the DPR can't corrupt how much is treated as paid / still pending.
        base = _pay_base_total(case)

        # Full-sync: apply any other recognised columns present (contact, bucket, etc.).
        ups = it.get("_fields") or {}
        if ups:
            for attr, val in ups.items():
                setattr(case, attr, val)
            if "new_phone" in ups or "new_address" in ups:
                import datetime as _dt
                case.new_contact_by = user.name
                case.new_contact_at = _dt.datetime.utcnow()
            audit.record(db, user, "edit", case,
                         detail="DPR sync: " + ", ".join(sorted(ups.keys())),
                         meta={"fields": {k: str(v) for k, v in ups.items()}})
            audit.stamp_case(case, user)
            fields_n += len(ups)
            _touch(case)

        if act == "already_paid":
            already_n += 1
            continue
        if act == "mark_paid":
            # The DPR is the case's CURRENT state, not an increment — so SET the received
            # amount to what the report says (fall back to paid-in-full when no amount given),
            # never add on top (which double-counted).
            amt = it["_amount"] if (it["_amount"] and it["_amount"] > 0) else base
            if amt < 0:
                amt = Decimal(0)
            case.received_amount = amt
            pend = base - amt
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
            _touch(case)
        else:  # mark_unpaid (reversal)
            prev = Decimal(case.received_amount or 0)
            case.received_amount = Decimal(0)
            case.pending_amount = base
            case.paid_status, case.status, case.norm_stab = "UNPAID", "allocated", None
            if prev > 0:
                credit = case.assigned_caller_id or case.assigned_fos_id or user.id
                db.add(models.CallLog(case_id=case.id, caller_id=credit, disposition="PAID",
                                      ptp_amount=(-prev), note="DPR: reversed (marked unpaid)"))
            audit.record(db, user, "unpaid", case, old="PAID", new="UNPAID",
                         detail="DPR bulk reversal")
            audit.stamp_case(case, user)
            unpaid_n += 1
            _touch(case)

    audit.record(db, user, "import", None, entity_type="import",
                 detail=f"DPR update {default_bank}/{product}: {paid_n} paid, {unpaid_n} reversed, "
                        f"{fields_n} field updates",
                 meta={"bank": default_bank, "product": product, "paid": paid_n,
                       "unpaid": unpaid_n, "already": already_n, "unmatched": unmatched_n,
                       "field_updates": fields_n})
    db.commit()
    for c in touched:
        db.refresh(c)
    from .realtime import notify_data_changed
    notify_data_changed(default_bank, product)
    _mark_today(db, touched)
    return {"bank": default_bank, "product": product, "total": len(items),
            "paid": paid_n, "unpaid": unpaid_n, "already_paid": already_n,
            "unmatched": unmatched_n, "field_updates": fields_n}
