"""Excel import/export.

Import understands two layouts found in SSD's sheets:
  * "loading file" / funding layout (telecaller): S.NO, BANK, CUS NAME, PHONE NO,
    ACCOUNT NO, CC NO, FUNDING AMOUNT, RECEIVED AMOUNT, PENDING AMOUNT, CALLER,
    FOS, ADDRESS, BKT, CYC, MONTH ...
  * Axis "LIVE SHEET" (field): ACC NO, CUS NAME, CARD NO, TOS, POS, TAD, MAD,
    PHONE NUMBER, CYCLE, AREA, FOS, PAID/UNPAID, STATUS, DISPO, REMARKS ...

Money is parsed with Decimal and quantized to 2 dp so banking totals stay exact.
"""
import io
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from openpyxl import load_workbook, Workbook

from . import models

TWO = Decimal("0.01")


def to_decimal(v) -> Decimal:
    if v is None or v == "":
        return Decimal("0.00")
    if isinstance(v, (int, float, Decimal)):
        try:
            return Decimal(str(v)).quantize(TWO, rounding=ROUND_HALF_UP)
        except InvalidOperation:
            return Decimal("0.00")
    s = re.sub(r"[^0-9.\-]", "", str(v))
    if s in ("", "-", ".", "-."):
        return Decimal("0.00")
    try:
        return Decimal(s).quantize(TWO, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return Decimal("0.00")


def _clean(v):
    if v is None:
        return None
    s = str(v).strip()
    return s if s and s.lower() != "none" else None


def _norm(h):
    return re.sub(r"[^a-z0-9]", "", str(h).lower()) if h is not None else ""


PIN_RE = re.compile(r"\b(\d{6})\b")


def extract_pincode(address):
    if not address:
        return None
    # Indian pincodes sit at the END of the address; a leading 6-digit run is
    # usually a door/house number, so prefer the last valid 6-digit group.
    matches = PIN_RE.findall(str(address))
    for m in reversed(matches):
        if m[0] != "0":          # pincodes never start with 0
            return m
    return matches[-1] if matches else None


# map normalized header -> canonical field
HEADER_MAP = {
    "bank": "bank",
    "cusname": "customer_name", "names": "customer_name", "name": "customer_name",
    "phone": "phone", "phoneno": "phone", "phonenumber": "phone", "phoneno1": "phone",
    "mobile": "phone", "mobileno": "phone", "mobilenumber": "phone", "mobno": "phone", "mob": "phone",
    "mobile1": "phone", "custmobile": "phone", "customermobile": "phone", "customermobileno": "phone",
    "custmobileno": "phone", "contactno": "phone", "contactnumber": "phone", "contact": "phone",
    "cellno": "phone", "cellnumber": "phone", "registeredmobile": "phone", "regmobile": "phone",
    "customeralternateno": "alt_phone", "alternateno": "alt_phone", "altno": "alt_phone",
    "altphone": "alt_phone", "alternatemobile": "alt_phone", "alternatephone": "alt_phone",
    "secondarymobile": "alt_phone", "altmobile": "alt_phone",
    "accountno": "account_no", "accno": "account_no", "acc.no": "account_no", "accno.": "account_no",
    "ccno": "card_no", "cardno": "card_no",
    "cardtype": "product", "product": "product",
    # Address — accept the common header variants seen across bank allocation files.
    "address": "address", "add": "address", "addr": "address",
    "custaddress": "address", "customeraddress": "address", "custadd": "address",
    "resaddress": "address", "residenceaddress": "address", "residentialaddress": "address",
    "communicationaddress": "address", "commaddress": "address", "mailingaddress": "address",
    "billingaddress": "address", "permanentaddress": "address", "currentaddress": "address",
    "curraddress": "address", "fulladdress": "address", "completeaddress": "address",
    "address1": "address", "addressline1": "address", "addressline": "address",
    "location": "address", "custaddr": "address", "customeraddr": "address",
    # Pincode — capture a dedicated column when present (else it's parsed from the address).
    "pincode": "pincode", "pin": "pincode", "pincodeno": "pincode", "pinno": "pincode",
    "zip": "pincode", "zipcode": "pincode", "postalcode": "pincode", "postcode": "pincode",
    "bkt": "bucket", "bucket": "bucket", "allocationdpdbracket": "bucket",
    "cyc": "cycle", "cycle": "cycle",
    "month": "month",
    "fundingamount": "funding_amount", "stab": "stab_amount", "norm": "norm_amount",
    "amount": "received_amount", "receivedamount": "received_amount", "cashcoll": "received_amount",
    "pendingamount": "pending_amount", "pending": "pending_amount",
    "totalouts": "total_outstanding", "tos": "total_outstanding", "currbal": "total_outstanding",
    "pos": "principal_outstanding", "principaloutstd": "principal_outstanding", "pri": "principal_outstanding",
    "tad": "total_outstanding", "mad": "min_amount_due",
    # MIS core inputs
    "enr": "enr", "emios": "_emi_os", "emi0s": "_emi_os",
    "normstab": "norm_stab", "nstab": "norm_stab", "ns": "norm_stab",
    "caller": "_caller", "tcname": "_caller",
    "fos": "_fos", "fosname": "_fos",
    "area": "_area",
    "team": "team_lead",
    "catallo": "cat", "cat": "cat", "category": "cat",
    "visits": "_visits", "visit": "_visits", "fosdispo": "_fosdispo",
    "paidunpaid": "paid_status",
    "status": "final_status",
    "dispo": "disposition", "disposition": "disposition", "tcdispo": "disposition",
    "remarks": "remarks", "tcremark": "remarks",
    "finalstatus": "final_status",
    "cardlimit": "_ignore", "creditlimi": "_ignore",
}

MONEY_FIELDS = {
    "funding_amount", "received_amount", "pending_amount",
    "total_outstanding", "principal_outstanding", "min_amount_due",
    "enr", "norm_amount", "stab_amount", "_emi_os",
}


def _find_header_row(ws, max_scan=8):
    """Find the row that looks like a header (has known column names)."""
    best_row, best_hits = 1, -1
    for i, row in enumerate(ws.iter_rows(min_row=1, max_row=max_scan, values_only=True), start=1):
        hits = sum(1 for c in row if _norm(c) in HEADER_MAP)
        if hits > best_hits:
            best_hits, best_row = hits, i
    return best_row, best_hits


def import_workbook(file_bytes: bytes, default_bank=None, sheet_name=None):
    wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    sheets = [sheet_name] if sheet_name else wb.sheetnames

    all_records = []
    used_sheets = []
    for sn in sheets:
        if sn not in wb.sheetnames:
            continue
        ws = wb[sn]
        hdr_row, hits = _find_header_row(ws)
        if hits < 2:
            continue
        rows = list(ws.iter_rows(min_row=hdr_row, values_only=True))
        if not rows:
            continue
        headers = [_norm(h) for h in rows[0]]
        col_field = {idx: HEADER_MAP[h] for idx, h in enumerate(headers) if h in HEADER_MAP}
        if not col_field:
            continue
        used_sheets.append(sn)
        for r in rows[1:]:
            rec = {}
            for idx, field in col_field.items():
                if idx >= len(r) or field in ("_ignore",):
                    continue
                val = r[idx]
                if field in MONEY_FIELDS:
                    rec[field] = to_decimal(val)
                elif field in ("_caller", "_fos", "_area", "paid_status", "final_status",
                               "disposition", "remarks", "bucket", "cycle", "month", "product"):
                    rec[field] = _clean(val)
                else:
                    rec[field] = _clean(val)
            # must have at least a name or account no to be a real case
            if not rec.get("customer_name") and not rec.get("account_no"):
                continue
            rec["bank"] = rec.get("bank") or default_bank
            # Normalise a dedicated pincode column (Excel may read it as a number).
            if rec.get("pincode"):
                pc = str(rec["pincode"]).strip()
                if pc.endswith(".0"):
                    pc = pc[:-2]
                m = PIN_RE.search(pc)
                rec["pincode"] = m.group(1) if m else (pc or None)
            if rec.get("address") and not rec.get("pincode"):
                rec["pincode"] = extract_pincode(rec["address"])
            # derive pending if missing
            all_records.append(rec)
        # process every sheet that looks like case data (e.g. addresses may live
        # only in a later month's sheet), not just the first.
    wb.close()
    return all_records, ", ".join(used_sheets) if used_sheets else None


def record_to_case_kwargs(rec: dict) -> dict:
    fields = {
        "bank", "branch", "product", "account_no", "card_no", "customer_name",
        "phone", "alt_phone", "address", "pincode", "bucket", "cycle", "month",
        "total_outstanding", "principal_outstanding", "min_amount_due",
        "funding_amount", "received_amount", "pending_amount",
        "disposition", "remarks", "final_status",
        # MIS
        "enr", "norm_amount", "stab_amount", "norm_stab", "cat", "team_lead",
    }
    kwargs = {k: v for k, v in rec.items() if k in fields and v is not None}

    funding = rec.get("funding_amount") or Decimal("0.00")
    received = rec.get("received_amount") or Decimal("0.00")

    # ENR = End Net Receivables = EMI 0/S + CURR_BAL (fallback if no ENR column).
    if not kwargs.get("enr"):
        emi = rec.get("_emi_os") or Decimal("0.00")
        curr = rec.get("total_outstanding") or Decimal("0.00")
        if emi or curr:
            kwargs["enr"] = (Decimal(emi) + Decimal(curr)).quantize(TWO)

    pending = rec.get("pending_amount")
    if pending is None:
        # unpaid STAB (settlement) target outstanding, else funding - received
        stab = rec.get("stab_amount")
        pending = ((Decimal(stab) - received) if stab else (funding - received)).quantize(TWO)
    kwargs["pending_amount"] = pending

    # MIS text dimensions
    caller = _clean(rec.get("_caller"))
    if caller:
        kwargs["caller_name"] = caller
    fos = _clean(rec.get("_fos"))
    if fos:
        kwargs["fos_name"] = fos
    area = _clean(rec.get("_area"))
    if area:
        kwargs["team"] = area                      # AREA / region code (GTR, KDP, TS...)
    ns = _clean(rec.get("norm_stab"))
    if ns:
        kwargs["norm_stab"] = "STAB" if "STAB" in ns.upper() else ("NORM" if "NORM" in ns.upper() else ns)

    # VISITED — from VISITS column (or an explicit FOS disposition)
    vis = _clean(rec.get("_visits")) or _clean(rec.get("_fosdispo"))
    if vis:
        vu = vis.upper()
        kwargs["visited"] = ("VISIT" in vu and "NOT" not in vu)

    paid = _clean(rec.get("paid_status"))
    if paid:
        pu = paid.upper()
        kwargs["paid_status"] = "PAID" if "PAID" in pu and "UN" not in pu else ("UNPAID" if "UNPAID" in pu else pu)
        if received > 0 and pending <= 0:
            kwargs["status"] = "paid"
    return kwargs


# ---------------- Export ----------------
EXPORT_COLUMNS = [
    ("id", "Case ID"),
    ("bank", "Bank"),
    ("branch", "Branch"),
    ("customer_name", "Customer Name"),
    ("account_no", "Account No"),
    ("card_no", "Card No"),
    ("phone", "Phone"),
    ("address", "Address"),
    ("pincode", "Pincode"),
    ("bucket", "Bucket"),
    ("cycle", "Cycle"),
    ("funding_amount", "Target Amount"),
    ("received_amount", "Received"),
    ("pending_amount", "Pending"),
    ("status", "Status"),
    ("paid_status", "Paid/Unpaid"),
    ("disposition", "Disposition"),
    ("fos_name", "Field Officer"),
    ("caller_name", "Telecaller"),
    ("last_visit", "Last Visit"),
    ("visit_paid", "Visit Paid?"),
    ("visit_amount", "Visit Amount"),
    ("visit_lat", "Visit Lat"),
    ("visit_lng", "Visit Lng"),
    ("location_correct", "Location OK?"),
    ("person_moved", "Moved?"),
    ("visit_note", "Field Note"),
    ("remarks", "Remarks"),
]


def export_cases(db) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Recovery Tracker"
    ws.append([c[1] for c in EXPORT_COLUMNS])

    users = {u.id: u.name for u in db.query(models.User).all()}
    cases = db.query(models.Case).order_by(models.Case.bank, models.Case.id).all()
    for c in cases:
        last = (
            db.query(models.Visit)
            .filter(models.Visit.case_id == c.id)
            .order_by(models.Visit.created_at.desc())
            .first()
        )
        row = {
            "id": c.id, "bank": c.bank, "branch": c.branch,
            "customer_name": c.customer_name, "account_no": c.account_no,
            "card_no": c.card_no, "phone": c.phone, "address": c.address,
            "pincode": c.pincode, "bucket": c.bucket, "cycle": c.cycle,
            "funding_amount": float(c.funding_amount or 0),
            "received_amount": float(c.received_amount or 0),
            "pending_amount": float(c.pending_amount or 0),
            "status": c.status, "paid_status": c.paid_status,
            "disposition": c.disposition,
            "fos_name": users.get(c.assigned_fos_id, ""),
            "caller_name": users.get(c.assigned_caller_id, ""),
            "remarks": c.remarks,
        }
        if last:
            row.update({
                "last_visit": last.created_at.strftime("%Y-%m-%d %H:%M") if last.created_at else "",
                "visit_paid": "YES" if last.paid else "NO",
                "visit_amount": float(last.amount_collected or 0),
                "visit_lat": last.latitude, "visit_lng": last.longitude,
                "location_correct": "" if last.location_correct is None else ("YES" if last.location_correct else "NO"),
                "person_moved": "YES" if last.person_moved else "NO",
                "visit_note": last.note,
            })
        ws.append([row.get(k, "") for k, _ in EXPORT_COLUMNS])

    # bold header
    for cell in ws[1]:
        cell.font = cell.font.copy(bold=True)
    ws.freeze_panes = "A2"
    for col in ws.columns:
        width = max((len(str(c.value)) for c in col if c.value is not None), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 10), 40)

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
