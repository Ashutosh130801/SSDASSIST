from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import io

from .. import models
from ..database import get_db
from ..deps import require_roles
from ..excel_io import import_workbook, record_to_case_kwargs, export_cases
from ..allocation import run_allocation

router = APIRouter(prefix="/api/import", tags=["import"])


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
                 admin: models.User = Depends(require_roles("admin", "backend")), db: Session = Depends(get_db)):
    content = await file.read()
    try:
        records, sheet = import_workbook(content, default_bank=default_bank)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read file: {e}")

    batch = models.ImportBatch(filename=file.filename, bank=default_bank, sheet=sheet,
                               rows_total=len(records), uploaded_by=admin.id)
    db.add(batch)
    db.flush()

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
                      "disposition", "remarks", "address", "pincode", "phone"):
                if kwargs.get(k) is not None:
                    setattr(existing, k, kwargs[k])
            if default_bank:
                existing.bank = default_bank
            if product:
                existing.product = product
            if segment:
                existing.segment = segment
            if branch:                       # allow a re-upload to (re)assign the branch
                existing.branch = branch
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
        kwargs["import_batch_id"] = batch.id
        db.add(models.Case(**kwargs))
        imported += 1

    batch.rows_imported = imported
    batch.rows_skipped = skipped
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

    return {"sheet": sheet, "imported": imported, "updated": skipped,
            "total": len(records), "allocation": alloc,
            "total_cases": total_cases,
            "assigned_fos_total": assigned_fos,
            "assigned_caller_total": assigned_caller,
            "batch_id": batch.id}


@router.get("/export")
def export(db: Session = Depends(get_db), admin: models.User = Depends(require_roles("admin", "backend"))):
    data = export_cases(db)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=SSD_Recovery_Tracker.xlsx"},
    )
