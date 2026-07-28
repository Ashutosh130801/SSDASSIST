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
    return [{"id": r.id, "bank": r.bank, "product": r.product,
             "segment": r.segment, "closing_type": r.closing_type} for r in rows]


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
