"""Seed the database with staff accounts and (optionally) cases from an Excel file.

Usage:
    python -m app.seed                       # users only
    python -m app.seed /path/to/loading.xlsx ICICI   # + import cases for a bank
"""
import os
import sys

from sqlalchemy import inspect, text

from .database import Base, engine, SessionLocal
from . import models
from .config import get_settings
from .security import hash_password
from .excel_io import import_workbook, record_to_case_kwargs
from .allocation import run_allocation


def _sync_columns():
    """Add any column that exists on the models but is missing from an older database,
    so seeding never crashes on a schema that predates the newest fields. Generic: works
    for every table/column without a hand-maintained list."""
    insp = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        existing = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing:
                continue
            try:
                ddl = col.type.compile(dialect=engine.dialect)
                with engine.begin() as conn:
                    conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {ddl}'))
            except Exception:
                pass

settings = get_settings()

# PRODUCTION: only the owner/admin is created. The admin then creates real staff
# through the app (Staff → Add staff), so no weak demo passwords ever exist in prod.
ADMIN_USER = dict(name="Administrator", email=settings.admin_email, role="admin",
                  password=settings.admin_password, branch="Head Office")

# DEMO staff — only seeded when SEED_DEMO=1 (for local testing, never in production).
DEMO_STAFF = [
    dict(name="Vizag Manager", email="manager@ssdrecovery.in", role="manager",
         password="mgr123", branch="Visakhapatnam", banks=["ICICI", "RBL", "AXIS"], employment_type="Full-time"),
    dict(name="Ravi (FO)", email="ravi@ssdrecovery.in", role="fos", password="fos123",
         branch="Visakhapatnam", banks=["ICICI", "RBL", "AXIS"],
         assigned_pincodes=["530001", "530002", "530016"], home_lat=17.7231, home_lng=83.3013),
    dict(name="Anil (FO)", email="anil@ssdrecovery.in", role="fos", password="fos123",
         branch="Visakhapatnam", banks=["AXIS", "RBL"],
         assigned_pincodes=["530013", "530017", "531001"], home_lat=17.7526, home_lng=83.2185),
    dict(name="Suresh (FO)", email="suresh@ssdrecovery.in", role="fos", password="fos123",
         branch="Vizianagaram", banks=["ICICI"],
         assigned_pincodes=["535002", "535003"], home_lat=18.1067, home_lng=83.3956),
    dict(name="Krishna Sai (TC)", email="krishna@ssdrecovery.in", role="telecaller", password="tc123",
         branch="Head Office", banks=["ICICI", "RBL", "AXIS"]),
    dict(name="Prasanth (TC)", email="prasanth@ssdrecovery.in", role="telecaller", password="tc123",
         branch="Head Office", banks=["AXIS", "RBL"]),
]


def _create(db, u):
    if db.query(models.User).filter(models.User.email == u["email"]).first():
        return 0
    db.add(models.User(
        name=u["name"], email=u["email"], role=u["role"],
        hashed_password=hash_password(u["password"]), branch=u.get("branch"),
        banks=u.get("banks", []), assigned_pincodes=u.get("assigned_pincodes", []),
        home_lat=u.get("home_lat"), home_lng=u.get("home_lng"),
        employment_type=u.get("employment_type"),
    ))
    return 1


def seed_users(db):
    created = _create(db, ADMIN_USER)
    if os.environ.get("SEED_DEMO", "").lower() in ("1", "true", "yes"):
        for u in DEMO_STAFF:
            created += _create(db, u)
    db.commit()
    print(f"Users: {created} created (skipped existing). Admin: {ADMIN_USER['email']}")


def seed_cases(db, path, bank=None):
    with open(path, "rb") as f:
        content = f.read()
    records, sheet = import_workbook(content, default_bank=bank)
    admin = db.query(models.User).filter(models.User.role == "admin").first()
    batch = models.ImportBatch(filename=path.split("/")[-1], bank=bank, sheet=sheet,
                               rows_total=len(records), uploaded_by=admin.id if admin else None)
    db.add(batch)
    db.flush()
    imported = 0
    for rec in records:
        kwargs = record_to_case_kwargs(rec)
        if kwargs.get("account_no") and db.query(models.Case).filter(
                models.Case.account_no == kwargs["account_no"]).first():
            continue
        kwargs["import_batch_id"] = batch.id
        db.add(models.Case(**kwargs))
        imported += 1
    batch.rows_imported = imported
    db.commit()
    print(f"Cases from {sheet}: {imported} imported.")
    alloc = run_allocation(db, only_unallocated=True)
    print(f"Allocation: {alloc}")


def main():
    Base.metadata.create_all(bind=engine)
    _sync_columns()                 # bring an older DB up to the current schema first
    db = SessionLocal()
    try:
        seed_users(db)
        if len(sys.argv) > 1:
            bank = sys.argv[2] if len(sys.argv) > 2 else None
            seed_cases(db, sys.argv[1], bank)
    finally:
        db.close()
    print("Seed complete.")


if __name__ == "__main__":
    main()
