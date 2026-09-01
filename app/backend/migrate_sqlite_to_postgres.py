"""One-time migration: copy everything from the local SQLite file (ssd_local.db) into your
PostgreSQL database, so you can switch the app over to Postgres without losing current data.

It is SAFE to re-run: each table in Postgres is cleared and re-loaded from SQLite every time,
then the id sequences are reset so new inserts don't collide.

Usage (from app/backend, with the venv active):

    # target Postgres is read from your .env DATABASE_URL by default:
    python migrate_sqlite_to_postgres.py

    # ...or pass it explicitly:
    python migrate_sqlite_to_postgres.py "postgresql+psycopg2://ssd:ssd_password@localhost:5432/ssd_recovery"

    # source sqlite file can be overridden with SQLITE_PATH env var (default ./ssd_local.db)

Prerequisites: PostgreSQL is installed and running, and the target database + user exist
(see POSTGRES_SETUP.md). Nothing is written to SQLite — it is read-only here.
"""
import os
import sys

from sqlalchemy import create_engine, inspect, select, text

# Register all models on Base.metadata.
from app.database import Base
from app import models  # noqa: F401
from app.config import get_settings


def _target_url() -> str:
    url = sys.argv[1] if len(sys.argv) > 1 else (os.environ.get("TARGET_DATABASE_URL") or get_settings().database_url)
    if url.startswith("sqlite"):
        raise SystemExit(
            "Refusing to run: the target is SQLite. Pass your Postgres URL as an argument, e.g.\n"
            '  python migrate_sqlite_to_postgres.py "postgresql+psycopg2://ssd:ssd_password@localhost:5432/ssd_recovery"'
        )
    return url


def main() -> None:
    sqlite_path = os.environ.get("SQLITE_PATH", "./ssd_local.db")
    if not os.path.exists(sqlite_path):
        raise SystemExit(f"SQLite file not found: {sqlite_path}")
    src = create_engine(f"sqlite:///{sqlite_path}")
    dst_url = _target_url()
    dst = create_engine(dst_url, pool_pre_ping=True)

    print(f"Source : {sqlite_path}")
    print(f"Target : {dst_url.split('@')[-1]}")

    # 1) Make sure every current table exists in Postgres.
    Base.metadata.create_all(dst)

    src_insp = inspect(src)
    src_tables = set(src_insp.get_table_names())
    tables = list(Base.metadata.sorted_tables)          # FK-dependency order

    # 2) Clear Postgres tables (children first) so a re-run doesn't duplicate rows.
    with dst.begin() as dc:
        for t in reversed(tables):
            dc.execute(t.delete())

    # 3) Copy each table's rows, reading with typed columns so dates/bools/JSON/Decimal
    #    come back as proper Python objects (only columns present in BOTH sides).
    total = 0
    with src.connect() as sc, dst.begin() as dc:
        for t in tables:
            if t.name not in src_tables:
                continue
            src_cols = {c["name"] for c in src_insp.get_columns(t.name)}
            cols = [c for c in t.columns if c.name in src_cols]
            if not cols:
                continue
            rows = sc.execute(select(*cols)).mappings().all()
            if not rows:
                print(f"  {t.name}: 0")
                continue
            dc.execute(t.insert(), [dict(r) for r in rows])
            total += len(rows)
            print(f"  {t.name}: {len(rows)}")

    # 4) Reset integer-PK sequences to MAX(id) so the next insert gets a fresh id.
    with dst.begin() as dc:
        for t in tables:
            pk = list(t.primary_key.columns)
            if len(pk) != 1:
                continue
            col = pk[0]
            if not str(col.type).upper().startswith(("INTEGER", "BIGINT")):
                continue
            dc.execute(text(
                f"SELECT setval(pg_get_serial_sequence('{t.name}', '{col.name}'), "
                f"COALESCE((SELECT MAX({col.name}) FROM {t.name}), 1), true)"
            ))

    print(f"\nDone. Copied {total} rows into Postgres. "
          f"Verify by starting the app with run_postgres.bat and logging in.")


if __name__ == "__main__":
    main()
