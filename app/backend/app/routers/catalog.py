"""Admin-managed bank / product catalog additions.

Lets an admin onboard a NEW bank or a NEW product (with its closing rule) at runtime,
without a code change. These merge on top of the built-in list in products.py."""
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..deps import require_roles
from .. import audit

router = APIRouter(prefix="/api/catalog", tags=["catalog"])

VALID_CLOSING = {"cyc", "month_end", "due_date"}


@router.get("/custom")
def list_custom(db: Session = Depends(get_db),
                admin: models.User = Depends(require_roles("admin"))):
    """The admin-added banks/products (so they can be reviewed or removed)."""
    rows = db.query(models.CatalogProduct).filter(
        models.CatalogProduct.is_active.isnot(False)).order_by(
        models.CatalogProduct.bank, models.CatalogProduct.product).all()
    def n_cases(r):
        q = db.query(models.Case).filter(models.Case.bank == r.bank, models.Case.removed.isnot(True))
        if r.product:
            q = q.filter(models.Case.product == r.product)
        return q.count()
    return [{"id": r.id, "bank": r.bank, "product": r.product, "segment": r.segment,
             "closing_type": r.closing_type, "cases": n_cases(r)} for r in rows]


@router.patch("/product/{cid}")
def edit_product(cid: int, body: dict = Body(...), db: Session = Depends(get_db),
                 admin: models.User = Depends(require_roles("admin"))):
    """Edit a custom bank/product: name, segment and/or closing rule. With rename_cases=true the
    existing cases under the old bank/product are renamed too, so they stay in the same portfolio."""
    row = db.query(models.CatalogProduct).filter(models.CatalogProduct.id == cid).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    old_bank, old_prod = row.bank, row.product
    bank = (body.get("bank") if "bank" in body else old_bank) or ""
    bank = bank.strip()
    product = ((body.get("product") if "product" in body else old_prod) or "").strip() or None
    if not bank:
        raise HTTPException(status_code=400, detail="Bank name is required")
    closing = body.get("closing_type", row.closing_type)
    closing = (closing or "").strip().lower() or None
    if closing and closing not in VALID_CLOSING:
        raise HTTPException(status_code=400, detail="closing_type must be cyc, month_end or due_date")
    if (bank, product) != (old_bank, old_prod):
        dupe = db.query(models.CatalogProduct).filter(
            models.CatalogProduct.bank == bank, models.CatalogProduct.product == product,
            models.CatalogProduct.id != cid, models.CatalogProduct.is_active.isnot(False)).first()
        if dupe:
            raise HTTPException(status_code=409, detail="Another entry already has that bank/product")
    moved = 0
    if body.get("rename_cases") and (bank, product) != (old_bank, old_prod):
        q = db.query(models.Case).filter(models.Case.bank == old_bank)
        if old_prod:
            q = q.filter(models.Case.product == old_prod)
            moved = q.update({models.Case.bank: bank, models.Case.product: product}, synchronize_session=False)
        else:
            moved = q.update({models.Case.bank: bank}, synchronize_session=False)
    row.bank, row.product = bank, product
    if "segment" in body:
        row.segment = (body.get("segment") or "").strip() or None
    row.closing_type = closing
    old_label = f"{old_bank}{(' · ' + old_prod) if old_prod else ''}"
    new_label = f"{bank}{(' · ' + product) if product else ''}"
    audit.record(db, admin, "catalog_edit", None, entity_type="catalog", old=old_label, new=new_label,
                 detail=f"Edited {old_label} → {new_label}" + (f" [{closing}]" if closing else "")
                        + (f" · {moved} case(s) renamed" if moved else ""))
    db.commit()
    return {"ok": True, "id": row.id, "bank": row.bank, "product": row.product,
            "segment": row.segment, "closing_type": row.closing_type, "cases_renamed": moved}


@router.post("/product")
def add_product(body: dict = Body(...), db: Session = Depends(get_db),
                admin: models.User = Depends(require_roles("admin"))):
    """Add a bank and/or product. `bank` is required; `product` optional (blank = just
    register the bank). `closing_type` (cyc / month_end / due_date) sets how the product's
    cases close — defaults to month_end when a product is given."""
    bank = (body.get("bank") or "").strip()
    product = (body.get("product") or "").strip() or None
    segment = (body.get("segment") or "").strip() or None
    closing_type = (body.get("closing_type") or "").strip().lower() or None
    if not bank:
        raise HTTPException(status_code=400, detail="Bank name is required")
    if closing_type and closing_type not in VALID_CLOSING:
        raise HTTPException(status_code=400, detail="closing_type must be cyc, month_end or due_date")
    if product and not closing_type:
        closing_type = "month_end"     # sensible default so the product still closes

    # Don't duplicate an existing built-in or custom entry.
    from ..products import BANK_PRODUCTS
    if product and product in BANK_PRODUCTS.get(bank, []):
        raise HTTPException(status_code=409, detail=f"{bank} · {product} already exists")
    dupe = db.query(models.CatalogProduct).filter(
        models.CatalogProduct.bank == bank, models.CatalogProduct.product == product,
        models.CatalogProduct.is_active.isnot(False)).first()
    if dupe:
        raise HTTPException(status_code=409, detail="That bank/product is already added")

    row = models.CatalogProduct(bank=bank, product=product, segment=segment,
                                closing_type=closing_type, created_by=admin.id)
    db.add(row)
    audit.record(db, admin, "catalog_add", None, entity_type="catalog",
                 new=f"{bank}{(' · ' + product) if product else ''}",
                 detail=f"Added {bank}{(' · ' + product) if product else ' (bank)'}"
                        + (f" [{closing_type}]" if closing_type else ""))
    db.commit()
    db.refresh(row)
    return {"id": row.id, "bank": row.bank, "product": row.product,
            "segment": row.segment, "closing_type": row.closing_type}


@router.delete("/product/{cid}")
def remove_product(cid: int, db: Session = Depends(get_db),
                   admin: models.User = Depends(require_roles("admin"))):
    """Remove a custom bank/product (built-in ones can't be removed here)."""
    row = db.query(models.CatalogProduct).filter(models.CatalogProduct.id == cid).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    label = f"{row.bank}{(' · ' + row.product) if row.product else ''}"
    db.delete(row)
    audit.record(db, admin, "catalog_remove", None, entity_type="catalog",
                 old=label, detail=f"Removed {label} from catalog")
    db.commit()
    return {"ok": True}
