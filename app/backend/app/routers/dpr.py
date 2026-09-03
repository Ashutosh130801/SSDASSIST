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


# ---- Value-aware refinement: banks often reuse the generic word "STATUS" for BOTH the
# PAID/UNPAID flag AND the NORM/STAB settlement type, so header names alone are ambiguous.
# We look at the actual cell values to pick the right column for each role. ----
_PAID_WORDS = ("PAID", "UNPAID", "SUCCESS", "FAIL", "BOUNCE", "REVERS", "RETURN", "SETTLED",
               "DONE", "REJECT", "DISHON", "COLLECT", "RECEIVED", "YES", "NACHFAIL")
_NS_WORDS = ("STAB", "NORM", "ROLL")


def _sample(rows, h, n=60):
    out = []
    for r in rows[:n]:
        v = r.get(h)
        if v not in (None, ""):
            out.append(v)
    return out


def _frac(vals, words):
    tot = sum(1 for v in vals if str(v).strip())
    if not tot:
        return 0.0
    hit = sum(1 for v in vals if any(w in str(v).strip().upper() for w in words))
    return hit / tot


def _refine(cols, headers, rows):
    """Correct the header-based guesses using the column VALUES so PAID/UNPAID vs NORM/STAB
    can't be confused, and the collected AMOUNT is always found even under an odd header."""
    hs = [h for h in headers if h]
    # 1) Paid/unpaid status = the status-like column whose values actually read PAID/UNPAID.
    stat_candidates = [h for h in hs if h in _STAT or _frac(_sample(rows, h), _PAID_WORDS) >= 0.5]
    if stat_candidates:
        best = max(stat_candidates, key=lambda h: _frac(_sample(rows, h), _PAID_WORDS))
        if _frac(_sample(rows, best), _PAID_WORDS) > 0:
            cols["status"] = best
    # 2) NORM/STAB settlement type = a DIFFERENT column whose values are STAB/NORM/ROLLBACK.
    ns_cur = cols.get("ns")
    if not ns_cur or ns_cur == cols.get("status"):
        cand = [h for h in hs if h != cols.get("status")]
        nsh = max(cand, key=lambda h: _frac(_sample(rows, h), _NS_WORDS), default=None)
        if nsh and _frac(_sample(rows, nsh), _NS_WORDS) >= 0.2:
            cols["ns"] = nsh
        elif ns_cur == cols.get("status"):
            cols["ns"] = None
    # 3) Amount fallback: if no amount column was recognised, pick the numeric money column
    #    (not a key / status / ns / name) with the most non-zero values.
    if not cols.get("amount"):
        # Never mistake a small-number column (cycle / bucket / count) for a money column.
        taken = set(cols["keys"]) | {cols.get("status"), cols.get("ns"), cols.get("name"), cols.get("date")}
        small_fields = {"cyc", "cycle", "bucket", "bkt", "dpd", "sno", "srno", "slno", "sl"}
        best_h, best_hits = None, 0
        for h in hs:
            if h in taken or h in small_fields:
                continue
            vals = _sample(rows, h)
            nums = [x for x in (_dec(v) for v in vals) if x is not None]
            hits = sum(1 for x in nums if x > 0)
            if nums and max(nums) > 100 and hits > best_hits:   # amounts are meaningfully large
                best_h, best_hits = h, hits
        if best_h and best_hits >= max(1, len(_sample(rows, best_h)) // 4):
            cols["amount"] = best_h
    return cols


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
    cols = _refine(cols, headers, rows)   # value-aware: fix PAID vs NORM/STAB and find the amount
    if not cols["keys"]:
        raise HTTPException(status_code=400,
                            detail="No account / card / loan number column found in the DPR.")
    field_cols = _detect_fields(headers)
    cols["fields"] = {attr: h for attr, (h, _k, _m) in field_cols.items()}
    # all_periods=True: a DPR for a just-closed month arrives days into the next month, so match
    # cases across ALL periods (incl. closed portfolios), still within the uploader's own scope.
    q = _scope(db.query(models.Case), user, all_periods=True).filter(models.Case.bank == default_bank,
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
            act = "extra_paid"      # already paid + DPR paid again → NEW extra collection, added on top
        elif paid:
            act = "mark_paid"       # unpaid → paid: collect the DPR amount
        elif already:
            act = "mark_unpaid"     # paid → unpaid/fail/reversed: revert with the amount change
        else:
            act = "no_change"       # unpaid → unpaid: nothing to pay (only field sync, if any)
        field_ups = _proposed_fields(match, r, field_cols)
        items.append({"action": act, "case_id": match.id, "key": keyshow,
                      "customer": match.customer_name, "amount": float(amount or 0),
                      "norm_stab": ns, "current": match.paid_status,
                      # a paid row with an explicit ₹0 amount = auto-debit settlement
                      "auto_debit": bool(paid and amount is not None and amount == 0),
                      "updates": {k: str(v) for k, v in field_ups.items()},
                      "_case": match, "_amount": amount, "_ns": ns, "_fields": field_ups})
    return cols, items


@router.post("/preview")
async def dpr_preview(file: UploadFile = File(...), default_bank: str = Form(...),
                      product: str = Form(...), db: Session = Depends(get_db),
                      user: models.User = Depends(require_roles(*DPR_ROLES))):
    content = await file.read()
    cols, items = _prepare(content, default_bank, product, user, db)
    counts = {"mark_paid": 0, "extra_paid": 0, "mark_unpaid": 0, "no_change": 0, "unmatched": 0}
    for it in items:
        counts[it["action"]] = counts.get(it["action"], 0) + 1
    counts["field_updates"] = sum(len(it.get("_fields") or {}) for it in items)
    counts["rows_with_updates"] = sum(1 for it in items if it.get("_fields"))
    # Net cash this DPR will move: + collections / extra, − reversals (a reversal backs out the
    # case's current received amount).
    net = 0.0
    for it in items:
        a, amt, c = it["action"], float(it.get("amount") or 0), it.get("_case")
        if a == "mark_paid":
            net += amt if amt > 0 else float(_pay_base_total(c) or 0)
        elif a == "extra_paid":
            net += amt
        elif a == "mark_unpaid" and c is not None:
            net -= float(c.received_amount or 0)
    counts["collected_preview"] = round(net, 2)
    public = [{k: v for k, v in it.items() if not k.startswith("_")} for it in items]
    return {"bank": default_bank, "product": product, "detected": cols,
            "total": len(items), "counts": counts,
            "rows": public[:500], "capped": len(public) > 500}


@router.post("/commit")
async def dpr_commit(file: UploadFile = File(...), default_bank: str = Form(...),
                     product: str = Form(...), db: Session = Depends(get_db),
                     user: models.User = Depends(require_roles(*DPR_ROLES))):
    import datetime as _dt
    content = await file.read()
    cols, items = _prepare(content, default_bank, product, user, db)
    paid_n = unpaid_n = extra_n = unmatched_n = fields_n = nochange_n = 0
    collected_total = Decimal(0)      # net cash moved by this DPR (positive collections − reversals)
    touched, changes = [], []          # `changes` → stored on the ONE audit entry for the full drill-down

    def _touch(c):
        if c not in touched:
            touched.append(c)

    def _log_payment(case, amt, note):
        """Record the cash movement as a PAYMENT event (what FTD/MTD/Overall + feedback read),
        credited to the case's caller (else FOS, else the uploader) — so it lands on the right
        person's numbers everywhere."""
        credit = case.assigned_caller_id or case.assigned_fos_id or user.id
        db.add(models.CallLog(case_id=case.id, caller_id=credit, disposition="PAYMENT",
                              ptp_amount=amt, note=note))

    for it in items:
        act = it["action"]
        if act == "unmatched":
            unmatched_n += 1
            continue
        case = it["_case"]
        # Snapshot the collection base BEFORE any full-sync field overwrite, so a balance/TOS
        # column in the DPR can't corrupt how much is treated as paid / still pending.
        base = _pay_base_total(case)
        old_status = case.paid_status or "UNPAID"
        prev_recv = Decimal(case.received_amount or 0)
        amt = it["_amount"] if (it["_amount"] and it["_amount"] > 0) else None
        ns = it["_ns"]
        change = {"case_id": case.id, "key": it["key"], "customer": case.customer_name,
                  "action": act, "old_status": old_status, "amount": float(it["_amount"] or 0),
                  "norm_stab": ns}

        # Full-sync of any other recognised columns (contact, bucket, TOS, etc.) — value-only.
        ups = it.get("_fields") or {}
        if ups:
            for attr, val in ups.items():
                setattr(case, attr, val)
            if "new_phone" in ups or "new_address" in ups:
                case.new_contact_by = user.name
                case.new_contact_at = _dt.datetime.utcnow()
            fields_n += len(ups)
            change["fields"] = {k: str(v) for k, v in ups.items()}

        from .. import paymath
        # A paid DPR row with an EXPLICIT ₹0 amount = an auto-debit / e-NACH settlement: mark the
        # case PAID, but collect nothing (cash stays 0, pending stays the full balance). A paid row
        # with no amount at all still means "settle the full outstanding" (unchanged behaviour).
        is_autodebit = (it["_amount"] is not None and it["_amount"] == 0)
        if act == "mark_paid":
            if is_autodebit:
                case.auto_debit = True
                add = Decimal(0)
            else:
                add = amt if amt is not None else base   # amt = the >0 amount, else full base
            new_recv = prev_recv + add
            case.received_amount = new_recv
            if ns:
                case.norm_stab = ns
            # auto_debit → PAID at ₹0; otherwise a NORM/STAB case is PAID only once its settlement
            # is reached (below → PARTIAL), and plain cases PAID once the outstanding is met.
            new_status = paymath.recompute(case)
            _log_payment(case, add, ("DPR: auto-debit settlement (₹0)" if is_autodebit
                                     else f"DPR: paid ₹{add}") + (f" ({ns})" if ns else ""))
            collected_total += add
            change.update({"new_status": new_status, "delta": float(add), "new_received": float(new_recv),
                           "auto_debit": is_autodebit})
            paid_n += 1; _touch(case)

        elif act == "extra_paid" and amt is not None:
            # Already paid + DPR paid again with an amount → a NEW extra collection ADDED on top
            # (customer paid more on their own). Collected amount rises everywhere.
            new_recv = prev_recv + amt
            case.received_amount = new_recv
            if ns:
                case.norm_stab = ns
            new_status = paymath.recompute(case)
            _log_payment(case, amt, f"DPR updated collection: extra ₹{amt}" + (f" ({ns})" if ns else ""))
            collected_total += amt
            change.update({"new_status": new_status, "delta": float(amt), "new_received": float(new_recv),
                           "extra": True})
            extra_n += 1; _touch(case)

        elif act == "mark_unpaid":
            # Paid → unpaid / fail / reversed: revert status and back out the collected amount.
            case.received_amount = Decimal(0)
            case.pending_amount = base
            case.paid_status, case.status, case.norm_stab = "UNPAID", "allocated", None
            case.auto_debit = False   # a reversal / bounce clears any auto-debit settlement
            if prev_recv > 0:
                _log_payment(case, (-prev_recv), "DPR: reversed (marked unpaid)")
                collected_total -= prev_recv
            change.update({"new_status": "UNPAID", "delta": float(-prev_recv), "new_received": 0.0})
            unpaid_n += 1; _touch(case)

        else:
            # no_change (unpaid→unpaid) or extra_paid with no amount → only the field sync, if any.
            if ups:
                nochange_n += 1; _touch(case); change["new_status"] = old_status
            else:
                continue

        audit.stamp_case(case, user)
        changes.append(change)

    # ONE audit entry per DPR upload — the full per-case change list lives in its meta so the
    # activity screen can open the same detail you saw in the preview.
    audit.record(db, user, "import", None, entity_type="import",
                 detail=f"DPR update {default_bank}/{product}: {paid_n} paid, {extra_n} extra, "
                        f"{unpaid_n} reversed, {fields_n} field updates · net ₹{collected_total}",
                 meta={"dpr": True, "bank": default_bank, "product": product,
                       "paid": paid_n, "extra_paid": extra_n, "unpaid": unpaid_n,
                       "no_change": nochange_n, "unmatched": unmatched_n,
                       "field_updates": fields_n, "collected": float(collected_total),
                       "changes": changes})
    db.commit()
    for c in touched:
        db.refresh(c)
    from .realtime import notify_data_changed
    notify_data_changed(default_bank, product)
    _mark_today(db, touched)
    return {"bank": default_bank, "product": product, "total": len(items),
            "paid": paid_n, "extra_paid": extra_n, "unpaid": unpaid_n,
            "no_change": nochange_n, "unmatched": unmatched_n,
            "field_updates": fields_n, "collected": float(collected_total)}
