#!/usr/bin/env python3
"""
One-time employee-name merge.

When a person is renamed, their old name stays snapshotted on every case they handled
(team_lead / caller_name / fos_name). That splits their history in the MIS and hides the
old cases from their scope. This script re-stamps the OLD name to the NEW (current) name
across those three case columns, so everything collapses under one name.

(Going forward, renaming a person in Manpower now does this automatically — this script is
only for cleaning up renames that happened before that fix.)

Usage (run from app/backend), quote names that contain spaces:
    python merge_employee_name.py "Ganreddi Poornima" "Gandreddi Poornima"            # dry run
    python merge_employee_name.py "Ganreddi Poornima" "Gandreddi Poornima" --apply    # commit

Matching is case-insensitive and trims surrounding spaces. Safe to run more than once.
"""
import argparse
import sys

# Bring the DB schema up to date first (older SQLite/Postgres files may miss newer columns
# that the ORM SELECTs), using the app's own auto-migration — same as the app does on startup.
try:
    from app.main import _ensure_columns
    _ensure_columns()
except Exception as e:  # noqa: BLE001
    print(f"(schema check skipped: {e})")

from sqlalchemy import func
from app.database import SessionLocal
from app import models

COLUMNS = [
    (models.Case.team_lead, "team_lead"),
    (models.Case.caller_name, "caller_name"),
    (models.Case.fos_name, "fos_name"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Merge an old employee name into their current name across cases.")
    ap.add_argument("old_name", help="The old name currently stamped on the split cases")
    ap.add_argument("new_name", help="The current/correct name to merge them into")
    ap.add_argument("--apply", action="store_true", help="Commit the change (default is a dry run).")
    args = ap.parse_args()

    old = args.old_name.strip()
    new = args.new_name.strip()
    if not old or not new:
        print("Both names are required.")
        return 2
    if old.lower() == new.lower():
        print("Old and new names are the same — nothing to merge.")
        return 0

    db = SessionLocal()
    try:
        print(f"Merging  {old!r}  ->  {new!r}\n")
        grand = 0
        for col, label in COLUMNS:
            n = db.query(models.Case).filter(func.lower(func.trim(col)) == old.lower()).count()
            if n:
                print(f"  {label:<12}: {n} case(s)")
                grand += n
                db.query(models.Case).filter(func.lower(func.trim(col)) == old.lower()) \
                    .update({col: new}, synchronize_session=False)
            else:
                print(f"  {label:<12}: none")
        print()
        if grand == 0:
            print(f"No cases carry {old!r}. Nothing to do.")
            db.rollback()
            return 0
        if args.apply:
            db.commit()
            print(f"APPLIED: re-stamped {grand} case reference(s) to {new!r}.")
        else:
            db.rollback()
            print(f"DRY RUN: {grand} case reference(s) would be re-stamped. Re-run with --apply to commit.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
