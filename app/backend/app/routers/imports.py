from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime, date
import io

from .. import models
from ..database import get_db
from ..deps import require_roles
from ..excel_io import import_workbook, record_to_case_kwargs, export_cases
from ..allocation import run_allocation
from .. import audit, closing

router = APIRouter(prefix="/api/import", tags=["import"])


def _parse_due(val):
    """Best-effort parse of a due-date cell (date object or many string formats)."""
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%d-%b-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


@router.post("/preview")
async def preview(file: UploadFile = File(...), default_bank: str | None = Form(None),
                  product: str | None = Form(None), segment: str | None = Form(None),
                  admin: models.User = Depends(require_roles("admin", "backend"))):
    content = await file.read()
    try:
        records, sheet = import_workbook(content, default_bank=default_bank)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read file: {e}")
    sample = [record_to_case_kwargs(r) for r in records[:10]]
    for s in sample:
        if default_bank:
            s["bank"] = default_bank
        if product:
            s["product"] = product
        if segment:
            s["segment"] = segment
        for k, v in list(s.items()):        # Decimals -> str for JSON
            if hasattr(v, "quantize"):
                s[k] = str(v)
    return {"sheet": sheet, "total_rows": len(records), "sample": sample}


@router.post("/commit")
async def commit(file: UploadFile = File(...), default_bank: str | None = Form(None),
                 product: str | None = Form(None), segment: str | None = Form(None),
                 branch: str | None = Form(None), auto_allocate: bool = Form(True),
                 year: int | None = Form(None), month: int | None = Form(None),
                 admin: models.User = Depends(require_roles("admin", "backend")), db: Session = Depends(get_db)):
    content = await file.read()
    try:
        records, sheet = import_workbook(content, default_bank=default_bank)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read file: {e}")

    # The month/year picked on the upload form is the authoritative PERIOD this batch
    # belongs to (multiple uploads in a month accumulate into the same period). Falls
    # back to the current IST month if not supplied.
    from datetime import timezone, timedelta
    now_ist = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    yy = int(year) if year else now_ist.year
    mm = int(month) if month else now_ist.month
    period = f"{yy:04d}-{mm:02d}"

    from ..products import custom_closing_type
    def _apply_period(case_obj, rec):
        """Stamp the period + compute the close date from the product's closing rule
        (an admin-defined rule for a custom product wins over the built-in map)."""
        b = default_bank or case_obj.bank
        p = product or case_obj.product
        due = _parse_due((rec.get("_extra") or {}).get("x_due_date"))
        cd, ctype = closing.compute_close(b, p, period,
                                          cyc=(rec.get("cycle") or getattr(case_obj, "cycle", None)),
                                          due_date=due,
                                          force_type=custom_closing_type(db, b, p))
        case_obj.period = period
        case_obj.close_date = cd
        case_obj.closing_type = ctype

    batch = models.ImportBatch(filename=file.filename, bank=default_bank, sheet=sheet,
                               rows_total=len(records), uploaded_by=admin.id)
    db.add(batch)
    db.flush()

    # Resolve the sheet's CALLER column to a caller: it now carries the caller's ID
    # (emp_code, e.g. TC001) generated at profile creation. Fall back to matching by name
    # for older sheets. When matched we also normalise caller_name to the real name (MIS).
    _users = db.query(models.User).all()
    _by_code = {u.emp_code.strip().upper(): u for u in _users if u.emp_code}
    _by_name = {u.name.strip().upper(): u for u in _users if u.name}
    # FOS is resolved the same way as caller — straight from the sheet's FOS column
    # (its ID or name), CROSS-BRANCH. A Vizag caller can work a case whose FOS is in
    # another branch; both come from the file, not from any branch rule.
    _fos_by_code = {u.emp_code.strip().upper(): u for u in _users if u.emp_code and u.role == "fos"}
    _fos_by_name = {u.name.strip().upper(): u for u in _users if u.name and u.role == "fos"}
    _caller_cands = [(u.name.strip().upper(), u) for u in _users
                     if u.name and u.role in ("telecaller", "teamlead")]
    _fos_cands = [(u.name.strip().upper(), u) for u in _users if u.name and u.role == "fos"]

    def _match(val, by_code, by_name, candidates):
        """Resolve one CALLER/FOS cell to a person and say WHY if it can't.
        Returns (user_or_None, reason) where reason is:
          '' matched · 'blank' no value in the cell · 'unknown' name/ID not in the system
          · 'ambiguous' the partial name fits more than one person (left unassigned on purpose).
        First-upload safety net: the sheet may hold just part of a name ('Krishna' for
        'Krishna Sai Durga') — matched only when it points to exactly ONE person."""
        if val is None or not str(val).strip():
            return None, "blank"
        key = str(val).strip().upper()
        exact = by_code.get(key) or by_name.get(key)
        if exact:
            return exact, ""
        if len(key) < 3:
            return None, "unknown"
        hits = {}
        for nm, u in candidates:
            words = nm.split()
            if key == nm or key in words or nm.startswith(key) or (words and words[0].startswith(key)):
                hits[u.id] = u
        if len(hits) == 1:
            return next(iter(hits.values())), ""
        return None, ("ambiguous" if len(hits) > 1 else "unknown")

    def _match_caller(val):
        return _match(val, _by_code, _by_name, _caller_cands)

    def _match_fos(val):
        return _match(val, _fos_by_code, _fos_by_name, _fos_cands)

    def _resolve_caller(val):
        return _match_caller(val)[0]

    def _resolve_fos(val):
        return _match_fos(val)[0]

    # Per-row diagnostics: rows whose CALLER/FOS was named on the sheet but didn't map to
    # anyone (typo, person not created yet, or an ambiguous partial name). Blanks are counted
    # but not listed — not every case carries both a caller and a field officer.
    _REASON_TEXT = {"unknown": "no matching employee (check spelling / create them first)",
                    "ambiguous": "name matches more than one person — use their ID (e.g. TC001)"}
    unresolved_rows: list = []
    blank_caller = blank_fos = 0
    _UNRESOLVED_CAP = 300

    def _flag(rec_kwargs, field, raw, reason):
        nonlocal blank_caller, blank_fos
        if reason == "blank":
            if field == "caller":
                blank_caller += 1
            else:
                blank_fos += 1
            return
        if len(unresolved_rows) < _UNRESOLVED_CAP:
            unresolved_rows.append({
                "account_no": rec_kwargs.get("account_no"),
                "customer": rec_kwargs.get("customer_name") or rec_kwargs.get("name"),
                "field": field,
                "value_in_sheet": (str(raw).strip() if raw is not None else None),
                "reason": reason,
                "detail": _REASON_TEXT.get(reason, reason),
            })

    imported, skipped = 0, 0
    for rec in records:
        kwargs = record_to_case_kwargs(rec)
        acct = kwargs.get("account_no")
        existing = None
        if acct:
            existing = db.query(models.Case).filter(models.Case.account_no == acct).first()
        if existing:
            # update amounts / status, don't duplicate
            for k in ("funding_amount", "received_amount", "pending_amount", "paid_status",
                      "disposition", "remarks", "address", "pincode", "phone",
                      "enr", "norm_amount", "stab_amount", "rollback_amount", "norm_stab",
                      "total_outstanding", "principal_outstanding",
                      "caller_name", "fos_name", "team", "bucket", "cycle", "final_status"):
                if kwargs.get(k) is not None:
                    setattr(existing, k, kwargs[k])
            if kwargs.get("extra"):                 # merge new loan/caller columns
                existing.extra = {**(existing.extra or {}), **kwargs["extra"]}
            _rawc = kwargs.get("caller_name")
            cu, _cr = _match_caller(_rawc)
            if cu:
                existing.assigned_caller_id = cu.id
                existing.caller_name = cu.name
            elif not existing.assigned_caller_id:      # still nobody on this case → report why
                _flag(kwargs, "caller", _rawc, _cr)
            _rawf = kwargs.get("fos_name")
            fu, _fr = _match_fos(_rawf)
            if fu:
                existing.assigned_fos_id = fu.id
                existing.fos_name = fu.name
                if fu.branch and not branch:            # case's branch = its field owner (FOS) branch
                    existing.branch = fu.branch
            elif not existing.assigned_fos_id:
                _flag(kwargs, "fos", _rawf, _fr)
            if default_bank:
                existing.bank = default_bank
            if product:
                existing.product = product
            if segment:
                existing.segment = segment
            if branch:                       # allow a re-upload to (re)assign the branch
                existing.branch = branch
            _apply_period(existing, rec)      # re-stamp period + recompute close date
            skipped += 1
            continue
        # This upload is for one bank + product + segment — stamp every new row.
        if default_bank:
            kwargs["bank"] = default_bank
        if product:
            kwargs["product"] = product
        if segment:
            kwargs["segment"] = segment
        if branch:
            kwargs["branch"] = branch
        _rawc = kwargs.get("caller_name")
        cu, _cr = _match_caller(_rawc)
        if cu:
            kwargs["assigned_caller_id"] = cu.id
            kwargs["caller_name"] = cu.name
        else:
            _flag(kwargs, "caller", _rawc, _cr)
        _rawf = kwargs.get("fos_name")
        fu, _fr = _match_fos(_rawf)
        if fu:
            kwargs["assigned_fos_id"] = fu.id
            kwargs["fos_name"] = fu.name
            if fu.branch and not kwargs.get("branch"):   # case's branch = its field owner (FOS) branch
                kwargs["branch"] = fu.branch
        else:
            _flag(kwargs, "fos", _rawf, _fr)
        kwargs["import_batch_id"] = batch.id
        new_case = models.Case(**kwargs)
        _apply_period(new_case, rec)
        db.add(new_case)
        imported += 1

    batch.rows_imported = imported
    batch.rows_skipped = skipped
    audit.record(db, admin, "import", None, entity_type="import",
                 new=str(imported), detail=f"Imported {imported} cases from {file.filename}"
                 + (f" ({default_bank})" if default_bank else ""),
                 meta={"batch_id": batch.id, "bank": default_bank, "sheet": sheet,
                       "rows_total": len(records), "skipped": skipped})
    db.commit()

    alloc = {"fos_allocated": 0, "caller_allocated": 0}
    if auto_allocate:
        alloc = run_allocation(db, only_unallocated=True, bank=default_bank)

    # Report the overall assignment state so a repeat upload (0 *new* allocations)
    # isn't mistaken for "nothing is allocated".
    q = db.query(models.Case)
    if default_bank:
        q = q.filter(models.Case.bank == default_bank)
    total_cases = q.count()
    assigned_fos = q.filter(models.Case.assigned_fos_id.isnot(None)).count()
    assigned_caller = q.filter(models.Case.assigned_caller_id.isnot(None)).count()

    # Post-commit assignment report: which named rows couldn't be mapped, and why.
    unresolved_caller = sum(1 for r in unresolved_rows if r["field"] == "caller")
    unresolved_fos = sum(1 for r in unresolved_rows if r["field"] == "fos")
    assignment_report = {
        "unresolved_caller": unresolved_caller,
        "unresolved_fos": unresolved_fos,
        "blank_caller": blank_caller,
        "blank_fos": blank_fos,
        "capped": len(unresolved_rows) >= _UNRESOLVED_CAP,
        "rows": unresolved_rows,
    }

    return {"sheet": sheet, "imported": imported, "updated": skipped,
            "total": len(records), "allocation": alloc,
            "total_cases": total_cases,
            "assigned_fos_total": assigned_fos,
            "assigned_caller_total": assigned_caller,
            "assignment_report": assignment_report,
            "batch_id": batch.id}


@router.get("/export")
def export(db: Session = Depends(get_db), admin: models.User = Depends(require_roles("admin", "backend"))):
    data = export_cases(db)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=SSD_Recovery_Tracker.xlsx"},
    )
