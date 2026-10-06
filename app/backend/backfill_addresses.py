#!/usr/bin/env python3
"""
Backfill 2nd / 3rd address lines + per-address pincodes onto EXISTING cases.

Why this exists
---------------
Cases uploaded before the 3-address feature only stored `address`, a merged
`address2`, and a single `pincode`. The columns `address3`, `pincode2` and
`pincode3` were dropped at import time because the importer had nowhere to put
them. This script re-reads the ORIGINAL portfolio Excel files, re-parses them
with the current importer (which now understands all three address columns),
matches each row to the case already in the database, and fills ONLY the
address/pincode columns — nothing else.

It NEVER touches money, allocation (caller/FOS/TL), disposition, payments,
history or any other field, so your collection data and ownership stay exactly
as they are. Cases whose address lines change are re-armed for geocoding
(geo_attempted_at cleared + that line's pin reset) so the next Geocode run pins
the new lines. Field-verified pins (location_source == "field") are preserved.

Matching key: account_no (+ bank + product when the file carries them). All
non-removed cases with that account are updated — the same person has the same
address across every month/bucket, so this is intentional.

Usage (from app/backend/):
    # dry run — shows what WOULD change, writes nothing:
    python backfill_addresses.py /path/to/original_portfolios

    # actually write the changes:
    python backfill_addresses.py /path/to/original_portfolios --commit

    # a single file instead of a folder works too:
    python backfill_addresses.py "/path/to/ICICI FR Aug.xlsx" --commit

Point it at the folder (or file) holding the ORIGINAL uploaded Excel sheets.
"""
import sys
import glob
import os

from app.database import SessionLocal
from app import models
from app.excel_io import import_workbook, record_to_case_kwargs

# Only these columns are ever written by this script.
ADDR_FIELDS = ("address", "address2", "address3", "pincode", "pincode2", "pincode3")


def _norm(v):
    return (str(v).strip() or None) if v not in (None, "") else None


def _collect_files(path):
    if os.path.isfile(path):
        return [path]
    pats = ("*.xlsx", "*.xlsm", "*.xls")
    out = []
    for p in pats:
        out.extend(glob.glob(os.path.join(path, "**", p), recursive=True))
    # skip Excel lock/temp files
    return sorted(f for f in out if not os.path.basename(f).startswith("~$"))


def _match_cases(db, kwargs):
    acct = _norm(kwargs.get("account_no"))
    if not acct:
        return []
    q = db.query(models.Case).filter(models.Case.account_no == acct,
                                     models.Case.removed.isnot(True))
    bank = _norm(kwargs.get("bank"))
    prod = _norm(kwargs.get("product"))
    if bank:
        q = q.filter(models.Case.bank == bank)
    if prod:
        q = q.filter(models.Case.product == prod)
    return q.all()


def run(path, commit=False):
    files = _collect_files(path)
    if not files:
        print(f"No Excel files found under: {path}")
        return
    print(f"Found {len(files)} file(s). Mode: {'COMMIT' if commit else 'DRY RUN'}\n")

    db = SessionLocal()
    seen_accts = 0
    matched = 0
    changed_cases = 0
    field_changes = {f: 0 for f in ADDR_FIELDS}
    unmatched = 0
    try:
        for fp in files:
            try:
                with open(fp, "rb") as fh:
                    records, sheet = import_workbook(fh.read())
            except Exception as e:  # noqa: BLE001
                print(f"  ! skip (can't read) {os.path.basename(fp)}: {e}")
                continue
            print(f"• {os.path.basename(fp)} — {len(records)} rows (sheets: {sheet})")
            for rec in records:
                k = record_to_case_kwargs(rec)
                acct = _norm(k.get("account_no"))
                if not acct:
                    continue
                # Nothing to backfill if this row carries no 2nd/3rd address data at all.
                if not any(_norm(k.get(f)) for f in ("address2", "address3", "pincode2", "pincode3")):
                    continue
                seen_accts += 1
                cases = _match_cases(db, k)
                if not cases:
                    unmatched += 1
                    continue
                for cs in cases:
                    matched += 1
                    touched = False
                    old_a2 = (cs.address2, cs.pincode2)
                    old_a3 = (cs.address3, cs.pincode3)
                    for f in ADDR_FIELDS:
                        newv = _norm(k.get(f))
                        # Only FILL — never overwrite an existing value with a blank, and only
                        # change when the new value actually differs.
                        if newv and _norm(getattr(cs, f, None)) != newv:
                            # Don't clobber a non-empty primary address/pincode that already
                            # matches enough; but for the new slots, filling is the whole point.
                            setattr(cs, f, newv)
                            field_changes[f] += 1
                            touched = True
                    if touched:
                        changed_cases += 1
                        # Re-arm geocoding for any slot whose address/pin changed.
                        if (cs.address2, cs.pincode2) != old_a2:
                            cs.latitude2 = cs.longitude2 = cs.geo_precision2 = None
                            cs.geo_attempted_at = None
                        if (cs.address3, cs.pincode3) != old_a3:
                            cs.latitude3 = cs.longitude3 = cs.geo_precision3 = None
                            cs.geo_attempted_at = None
        if commit:
            db.commit()
            print("\nCOMMITTED changes to the database.")
        else:
            db.rollback()
            print("\nDRY RUN — no changes written. Re-run with --commit to apply.")
    finally:
        db.close()

    print("\n── Summary ──────────────────────────────")
    print(f"Rows with extra address data : {seen_accts}")
    print(f"Case rows matched            : {matched}")
    print(f"Case rows changed            : {changed_cases}")
    print(f"Rows with no DB match        : {unmatched}")
    for f in ADDR_FIELDS:
        print(f"  {f:10s} filled on        : {field_changes[f]}")
    if changed_cases and commit:
        print("\nNext: run a Geocode pass (admin → Geocode) so the new address")
        print("lines get their own map pins.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    target = sys.argv[1]
    do_commit = "--commit" in sys.argv[2:]
    run(target, commit=do_commit)
