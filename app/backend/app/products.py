"""Bank → product catalog for the collections agency.

Each case-upload is for one bank + one product + a segment (Credit Card or PL/BL).
The built-in list below is the baseline; admins can add extra banks/products (with a
closing rule) at runtime — those live in the `catalog_products` table and are merged on
top here.
"""

BANK_PRODUCTS = {
    "ICICI": ["DR", "FR", "FCPU", "2 BKT", "4 BKT", "SFFRC", "180+", "3 BKT",
              "PL X BKT", "BL X BKT", "PL NPA", "BL NPA"],
    "AXIS": ["X BKT", "BL X BKT", "PL X BKT", "PL NPA", "BL NPA", "180+", "2 BKT", "3 BKT", "CC NPA"],
    "RBL": ["BRBL BKT 3"],
    "PIRAMAL": ["2 BKT"],
    "NAVI": ["X-5 BKT", "180+"],
    "CHOLA": ["CD 2,3,4"],
    "HERO FIN CORP": ["NPA", "180+"],
    "HOMECREDIT": ["180+"],
    "TVS CREDIT": ["180+"],
}

# The loan segment chosen at upload time.
SEGMENTS = ["Credit Card", "PL/BL"]


def catalog(db=None) -> dict:
    """Built-in catalog merged with any admin-added banks/products from the DB."""
    from copy import deepcopy
    products = {k: list(v) for k, v in BANK_PRODUCTS.items()}
    if db is not None:
        from . import models
        for row in db.query(models.CatalogProduct).filter(
                models.CatalogProduct.is_active.isnot(False)).all():
            bank = (row.bank or "").strip()
            if not bank:
                continue
            products.setdefault(bank, [])
            prod = (row.product or "").strip()
            if prod and prod not in products[bank]:
                products[bank].append(prod)
    return {"banks": list(products.keys()), "products": products, "segments": SEGMENTS}


def custom_closing_type(db, bank: str, product: str) -> str | None:
    """A closing rule an admin set for a custom product, if any (else None)."""
    if db is None or not bank or not product:
        return None
    from . import models
    row = (db.query(models.CatalogProduct)
           .filter(models.CatalogProduct.bank == bank,
                   models.CatalogProduct.product == product,
                   models.CatalogProduct.closing_type.isnot(None))
           .first())
    return row.closing_type if row else None
