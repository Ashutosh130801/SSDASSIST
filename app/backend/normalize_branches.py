#!/usr/bin/env python3
"""
One-time branch normalizer.

Collapses duplicate branch spellings (e.g. "kadapa" -> "KADAPA", "Tirupati" ->
"TIRUPATI") onto a single canonical spelling across the live data tables, so a
branch that got accidentally split back into one portfolio.

Canonical choice reuses the exact same rule the API dropdown uses
(app.routers.cases.branch_canon_map): among the variants that share an
UPPERCASE key, prefer the all-uppercase spelling ("if uppercase is there, use
uppercase"); otherwise the alphabetically first spelling.

Tables repointed: User, Case, LegalCase, SupportTicket.
AuditLog is intentionally NOT touched -- it is an immutable history log
("Never edited after write"), so its old branch strings stay as-written.

Usage (run from app/backend):
    python normalize_branches.py            # DRY RUN - shows what would change
    python normalize_branches.py --apply    # actually writes the changes

Safe to run more than once; a second run is a no-op once everything is canonical.
"""
import argparse
import sys

from app.database import SessionLocal
from app import models
from app.routers.cases import branch_canon_map

# (model, human label) for every table whose free-text branch we normalize.
# AuditLog is deliberately excluded (immutable log).
TARGETS = [
    (models.User, "User"),
    (models.Case, "Case"),
    (models.LegalCase, "LegalCase"),
    (models.SupportTicket, "SupportTicket"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Merge duplicate branch spellings onto one canonical spelling.")
    ap.add_argument("--apply", action="store_true",
                    help="Commit the changes. Without this flag the script only reports (dry run).")
    args = ap.parse_args()

    # Bring the target DB's schema up to date first. An older ssd_local.db / Postgres file may be
    # missing columns this build expects (e.g. cases.geo_lat, digipin) that the ORM will SELECT,
    # which otherwise crashes with "no such column". This is the exact auto-migration the app runs
    # on startup — safe and idempotent.
    try:
        from app.main import _ensure_columns
        _ensure_columns()
    except Exception as e:  # noqa: BLE001
        print(f"(schema check skipped: {e})")

    db = SessionLocal()
    try:
        canon = branch_canon_map(db)  # UPPER(branch) -> canonical spelling

        # Show the merge plan (only groups that actually have >1 spelling somewhere).
        print("Canonical mapping:")
        for up in sorted(canon):
            print(f"  {up:<20} -> {canon[up]!r}")
        print()

        grand_total = 0
        for model, label in TARGETS:
            rows = (
                db.query(model)
                .filter(model.branch.isnot(None))
                .filter(model.branch != "")
                .all()
            )
            changed = 0
            per_pair = {}  # (old -> new) : count
            for r in rows:
                cur = str(r.branch).strip()
                target = canon.get(cur.upper())
                if target and target != cur:
                    per_pair[(cur, target)] = per_pair.get((cur, target), 0) + 1
                    r.branch = target
                    changed += 1
            grand_total += changed
            if changed:
                print(f"{label}: {changed} row(s) to repoint")
                for (old, new), n in sorted(per_pair.items()):
                    print(f"    {old!r:>18} -> {new!r:<18} ({n})")
            else:
                print(f"{label}: nothing to change")

        print()
        if grand_total == 0:
            print("All branches already canonical -- no changes needed.")
            return 0

        if args.apply:
            db.commit()
            print(f"APPLIED: repointed {grand_total} row(s) across {len(TARGETS)} table(s).")
        else:
            db.rollback()
            print(f"DRY RUN: {grand_total} row(s) would be repointed. "
                  f"Re-run with --apply to commit.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
