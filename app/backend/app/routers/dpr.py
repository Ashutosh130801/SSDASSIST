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


# Every header alias that maps to a structural case field (OD NORM/STAB, TOS, POS, MAD, phone,
# address…). These are synced value-for-value and must NEVER be mistaken for a cash-amount column.
_FIELD_ALIASES = set().union(*(aliases for _a, aliases, _k, _m in _FIELD_SPECS))


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
        # Never mistake a small-number column (cycle / bucket / count) for a money column,
        # nor an OUTSTANDING-balance field (OD NORM / OD STAB / TOS / POS…) — those are
        # structural targets synced to the case, never cash the DPR collected.
        taken = set(cols["keys"]) | {cols.get("status"), cols.get("ns"), cols.get("name"), cols.get("date")}
        small_fields = {"cyc", "cycle", "bucket", "bkt", "dpd", "sno", "srno", "slno", "sl"}
        best_h, best_hits = None, 0
        for h in hs:
            if h in taken or h in small_fields or h in _FIELD_ALIASES:
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


def _prepare(content, default_bank, product, user, db, month_bucket=None):
    """Read + detect + match. Returns (cols, items) where each item is a classified row.
    When month_bucket is given (current/next/last/YYYY-MM), only that month's cases are matched —
    so a DPR can be pinned to one month's portfolio when the same account exists in several."""
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
    # A DPR that carries OD-NORM / OD-STAB columns and NO cash-amount column is a PL/BL-format
    # report (outstanding-balance snapshot, never a cash collection). Treat every one of its rows
    # as PL/BL — so paid/unpaid + NORM/STAB + OD values sync but no cash is ever booked — even if a
    # matched case wasn't tagged segment "PL/BL".
    dpr_plbl_format = (("norm_amount" in field_cols or "stab_amount" in field_cols)
                       and not cols.get("amount"))
    cols["plbl_format"] = dpr_plbl_format
    # all_periods=True: a DPR for a just-closed month arrives days into the next month, so match
    # cases across ALL periods (incl. closed portfolios), still within the uploader's own scope.
    q = _scope(db.query(models.Case), user, all_periods=True).filter(models.Case.bank == default_bank,
                                                                     models.Case.product == product)
    if month_bucket:
        from .mis import _period_for
        _per = _period_for(month_bucket) if month_bucket in ("current", "next", "last", "all") else month_bucket
        if _per:
            q = q.filter(models.Case.period == _per)
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
        # ---- SNAPSHOT RECONCILE ----
        # The DPR is the CURRENT status of every case; the amount is the CUMULATIVE total collected
        # to date. So we reconcile the case to it (set received = amount, up OR down) and count only
        # the DELTA as new cash. Unchanged rows do nothing. PL/BL is different: its DPR carries the
        # daily OD-NORM / OD-STAB targets + status, never a cash amount.
        prev = Decimal(match.received_amount or 0)
        already = (match.paid_status or "").upper() == "PAID"
        is_plbl = (match.segment or "") == "PL/BL" or dpr_plbl_format
        status_txt = str(r.get(cols["status"]) or "").strip().upper() if cols["status"] else ""
        explicit_unpaid = any(x in status_txt for x in
                              ("UNPAID", "BOUNCE", "FAIL", "REVERS", "RETURN", "DISHON", "REJECT", "NACHFAIL"))
        has_amt = amount is not None
        field_ups = _proposed_fields(match, r, field_cols)   # incl. OD NORM/STAB → norm_amount/stab_amount

        if is_plbl:
            # PL/BL: update OD targets (via field sync) + the paid/unpaid flag. NO cash from DPR.
            mode = "plbl"
            if explicit_unpaid:
                act = "plbl_unpaid"
            elif paid and status_txt:
                act = "plbl_paid"
            else:
                act = "plbl_update"   # just OD-value / field refresh, no status change
            target = prev; delta = Decimal(0)
        elif explicit_unpaid:
            # Failed / bounced / reversed → back the case out to zero.
            mode = "reverse"; target = Decimal(0); delta = -prev
            act = "reverse" if prev > 0 else "no_change"
        elif paid and not has_amt:
            # Paid with NO amount = auto-debit / e-NACH → mark PAID as-is, add no cash.
            mode = "autodebit"; target = prev; delta = Decimal(0)
            act = "no_change" if (already and getattr(match, "auto_debit", False)) else "mark_paid"
        elif has_amt:
            # Reconcile the case's collected total to the DPR amount (cumulative).
            mode = "reconcile"; target = amount; delta = target - prev
            if delta == 0:
                act = "no_change"
            elif prev <= 0 and target > 0:
                act = "mark_paid"
            elif delta > 0:
                act = "extra"
            else:
                act = "reduce"
        else:
            mode = "nochange"; target = prev; delta = Decimal(0); act = "no_change"

        items.append({"action": act, "case_id": match.id, "key": keyshow,
                      "customer": match.customer_name, "amount": float(amount or 0),
                      "target": float(target), "delta": float(delta), "norm_stab": ns,
                      "current": match.paid_status,
                      "updates": {k: str(v) for k, v in field_ups.items()},
                      "_case": match, "_amount": amount, "_ns": ns, "_fields": field_ups,
                      "_mode": mode, "_target": target, "_delta": delta, "_paid": paid})
    return cols, items


@router.post("/preview")
async def dpr_preview(file: UploadFile = File(...), default_bank: str = Form(...),
                      product: str = Form(...), month_bucket: str = Form(None), db: Session = Depends(get_db),
                      user: models.User = Depends(require_roles(*DPR_ROLES))):
    content = await file.read()
    cols, items = _prepare(content, default_bank, product, user, db, month_bucket)
    counts = {"mark_paid": 0, "extra": 0, "reduce": 0, "reverse": 0, "no_change": 0, "unmatched": 0,
              "plbl_paid": 0, "plbl_unpaid": 0, "plbl_update": 0}
    for it in items:
        counts[it["action"]] = counts.get(it["action"], 0) + 1
    counts["field_updates"] = sum(len(it.get("_fields") or {}) for it in items)
    counts["rows_with_updates"] = sum(1 for it in items if it.get("_fields"))
    # Net cash = the sum of DELTAS this DPR will move (reconcile up/down, reversals negative).
    # PL/BL rows and unchanged rows move ₹0. Only these deltas hit FTD.
    net = 0.0
    amount_total = 0.0          # raw sum of the file's amount column (the number a user eyeballs)
    unmatched_rows = []
    for it in items:
        amount_total += float(it.get("amount") or 0)
        if it["action"] == "unmatched":
            unmatched_rows.append({"key": it.get("key"), "name": it.get("name"),
                                   "amount": float(it.get("amount") or 0)})
        else:
            net += float(it.get("_delta") or 0)
    excluded = round(amount_total - net, 2)   # printed-but-not-booked (unmatched, no-change, PL/BL)
    counts["collected_preview"] = round(net, 2)
    counts["amount_total"] = round(amount_total, 2)
    counts["excluded_amount"] = excluded if excluded > 0 else 0.0
    public = [{k: v for k, v in it.items() if not k.startswith("_")} for it in items]
    return {"bank": default_bank, "product": product, "detected": cols,
            "plbl_format": cols.get("plbl_format", False),
            "total": len(items), "parsed": len(items), "counts": counts,
            "unmatched_rows": unmatched_rows,
            "rows": public[:500], "capped": len(public) > 500}


@router.post("/commit")
async def dpr_commit(file: UploadFile = File(...), default_bank: str = Form(...),
                     product: str = Form(...), month_bucket: str = Form(None), db: Session = Depends(get_db),
                     user: models.User = Depends(require_roles(*DPR_ROLES))):
    import datetime as _dt
    content = await file.read()
    cols, items = _prepare(content, default_bank, product, user, db, month_bucket)
    paid_n = unpaid_n = extra_n = unmatched_n = fields_n = nochange_n = 0
    collected_total = Decimal(0)      # net cash moved by this DPR (positive collections − reversals)
    touched, changes = [], []          # `changes` → stored on the ONE audit entry for the full drill-down

    def _touch(c):
        if c not in touched:
            touched.append(c)

    def _log_payment(case, amt, note):
        """Record the cash movement as a PAYMENT event (what FTD/MTD/Overall + feedback read),
        credited to the case's caller (else FOS, else the uploader) — so it lands on the right
        person's numbers everywhere. The note carries the uploader so History shows who ran the DPR."""
        credit = case.assigned_caller_id or case.assigned_fos_id or user.id
        db.add(models.CallLog(case_id=case.id, caller_id=credit, disposition="PAYMENT",
                              ptp_amount=amt, note=f"{note} · via DPR by {user.name}"))

    reduce_n = plbl_n = 0
    not_paid = []   # DPR rows that did NOT end as PAID — so the user can see exactly which are missing
    from .. import paymath
    for it in items:
        act = it["action"]; mode = it.get("_mode")
        if act == "unmatched":
            unmatched_n += 1
            not_paid.append({"account": it.get("key"), "customer": it.get("name"),
                             "amount": float(it.get("amount") or 0), "status": "—",
                             "reason": "unmatched — no case with this number in this portfolio"})
            continue
        case = it["_case"]
        old_status = case.paid_status or "UNPAID"
        prev_recv = Decimal(case.received_amount or 0)
        ns = it["_ns"]
        delta = Decimal(str(it.get("_delta") or 0))
        target = Decimal(str(it.get("_target") or 0))
        change = {"case_id": case.id, "key": it["key"], "customer": case.customer_name,
                  "action": act, "old_status": old_status, "amount": float(it["_amount"] or 0),
                  "norm_stab": ns}

        # Full-sync recognised columns (contact, bucket, TOS, and for PL/BL the OD-NORM/OD-STAB
        # → norm_amount/stab_amount) — value-only, blanks never wipe.
        ups = it.get("_fields") or {}
        if ups:
            for attr, val in ups.items():
                setattr(case, attr, val)
            if "new_phone" in ups or "new_address" in ups:
                case.new_contact_by = user.name
                case.new_contact_at = _dt.datetime.utcnow()
            fields_n += len(ups)
            change["fields"] = {k: str(v) for k, v in ups.items()}

        if mode == "plbl":
            # PL/BL: OD targets already synced above; DPR sets the paid/unpaid flag + the
            # NORM/STAB settlement type. NO cash, NO dated event — PL/BL cash comes solely
            # from call-log + visit collections.
            old_ns = case.norm_stab
            if act == "plbl_paid":
                case.auto_debit = True
                if ns:                       # STATUS column (NORM/STAB) → the case's settlement tag
                    case.norm_stab = ns      # (kept, since auto_debit short-circuits autotag)
            elif act == "plbl_unpaid":
                case.auto_debit = False
                case.paid_locked = False     # unpaid / flow → un-settle
                case.norm_stab = None        # unpaid / flow → no settlement tag
            new_status = paymath.recompute(case)
            change.update({"new_status": new_status, "delta": 0.0,
                           "norm_stab": case.norm_stab, "auto_debit": case.auto_debit})
            if (case.norm_stab or None) != (old_ns or None):
                change.setdefault("fields", {})["norm_stab"] = str(case.norm_stab or "—")
            plbl_n += 1; _touch(case)

        elif mode == "reverse":
            # DPR says UNPAID on a case that had collection → payment failed → back it out to ₹0.
            if prev_recv > 0:
                _log_payment(case, -prev_recv, "DPR: reversed (payment failed / marked unpaid)")
                collected_total -= prev_recv
            case.received_amount = Decimal(0)
            case.auto_debit = False
            case.paid_locked = False           # a reversal un-settles the case
            new_status = paymath.recompute(case)
            change.update({"new_status": new_status, "delta": float(-prev_recv), "new_received": 0.0})
            unpaid_n += 1; _touch(case)

        elif mode == "autodebit":
            # Paid, no amount = auto-debit / e-NACH → mark PAID as-is, collect nothing.
            case.auto_debit = True
            new_status = paymath.recompute(case)
            change.update({"new_status": new_status, "delta": 0.0, "new_received": float(prev_recv),
                           "auto_debit": True})
            paid_n += 1; _touch(case)

        elif mode == "reconcile":
            # Snapshot: set the collected total to the DPR's cumulative amount (up OR down); the
            # DELTA is the only new cash and the only thing that hits FTD.
            case.auto_debit = False
            case.received_amount = target
            # DPR AUTHORITY: if the bank marked the row PAID with a NORM/STAB tag, honour it as a
            # confirmed settlement — stays PAID under that tag even if the amount is below target.
            if it.get("_paid") and ns:
                case.norm_stab = ns
                case.paid_locked = True
            else:
                case.paid_locked = False        # a non-paid / untagged snapshot re-derives normally
            new_status = paymath.recompute(case)   # paid_locked → PAID + keeps the tag; else auto-tag
            if delta != 0:
                _log_payment(case, delta, f"DPR reconciled: total ₹{target} (Δ {delta})")
                collected_total += delta
            if delta > 0 and prev_recv <= 0:
                paid_n += 1
            elif delta > 0:
                extra_n += 1
            elif delta < 0:
                reduce_n += 1
            change.update({"new_status": new_status, "delta": float(delta), "new_received": float(target),
                           "norm_stab": case.norm_stab})
            _touch(case)
            if (new_status or "").upper() != "PAID" and target > 0:
                not_paid.append({"account": it["key"], "customer": case.customer_name,
                                 "amount": float(target), "status": new_status,
                                 "reason": f"collected ₹{float(target):.0f} but below the settlement — marked {new_status}"})

        else:  # no_change
            if ups:
                nochange_n += 1; _touch(case); change["new_status"] = old_status
            else:
                continue

        # Per-case audit attributed to the UPLOADER (not the credited caller) so the case
        # History shows who ran the DPR + exactly what changed.
        new_status = change.get("new_status", old_status)
        cdelta = change.get("delta", 0.0)
        bits = []
        if new_status and new_status != old_status:
            bits.append(f"{old_status} → {new_status}")
        if cdelta:
            bits.append(f"Δ ₹{float(cdelta):.0f}")
        if change.get("fields"):
            bits.append(", ".join(f"{k}={v}" for k, v in change["fields"].items()))
        audit.record(db, user, "dpr_update", case,
                     field=act, old=old_status, new=new_status,
                     detail=f"DPR {act}" + (": " + " · ".join(bits) if bits else "")
                            + f" (uploaded by {user.name})")
        audit.stamp_case(case, user)
        changes.append(change)

    # ONE audit entry per DPR upload — the full per-case change list lives in its meta so the
    # activity screen can open the same detail you saw in the preview.
    audit.record(db, user, "import", None, entity_type="import",
                 detail=f"DPR update {default_bank}/{product}: {paid_n} paid, {extra_n} extra, "
                        f"{reduce_n} reduced, {unpaid_n} reversed, {plbl_n} PL/BL, "
                        f"{fields_n} field updates · net ₹{collected_total}",
                 meta={"dpr": True, "bank": default_bank, "product": product,
                       "paid": paid_n, "extra": extra_n, "reduce": reduce_n, "unpaid": unpaid_n,
                       "plbl": plbl_n, "no_change": nochange_n, "unmatched": unmatched_n,
                       "field_updates": fields_n, "collected": float(collected_total),
                       "changes": changes})
    db.commit()
    for c in touched:
        db.refresh(c)
    from .realtime import notify_data_changed
    notify_data_changed(default_bank, product)
    _mark_today(db, touched)
    partial_n = sum(1 for r in not_paid if r["status"] not in ("—",))
    paid_final = max(0, paid_n - partial_n)
    return {"bank": default_bank, "product": product, "total": len(items),
            "parsed": len(items),
            "paid": paid_n, "paid_final": paid_final, "partial": partial_n,
            "extra": extra_n, "extra_paid": extra_n, "reduce": reduce_n,
            "unpaid": unpaid_n, "plbl": plbl_n,
            "no_change": nochange_n, "unmatched": unmatched_n,
            "field_updates": fields_n, "collected": float(collected_total),
            "not_paid": not_paid}
