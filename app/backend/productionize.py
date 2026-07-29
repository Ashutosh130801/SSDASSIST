"""One-time go-live: turn a demo/test database into a clean production one.

    python productionize.py "SSDE Man power.xlsx" "SSDE_login_credentials.xlsx"

Steps:
  1. Bring the schema up to date (adds any new columns).
  2. Create the real admin from ADMIN_EMAIL / ADMIN_PASSWORD (.env).
  3. Import all real employees from the manpower + credentials sheets.
  4. RE-MAP every existing case to the newly-created employees, matching the case's
     caller / FOS / team-lead name (full, partial or emp-code) — so old data attaches
     to real people. Later uploads match by ID automatically.
  5. Deactivate the demo/test accounts (admin@ssd.local and the sample staff) so no test
     login works anymore.

Existing cases are kept (nothing is deleted) — only their staff mapping is refreshed.
"""
import os
import sys

from app.database import SessionLocal, Base, engine
from app import models
from app.seed import _sync_columns, seed_users


# Known demo/test accounts to switch off once real staff exist.
DEMO_EMAILS = {
    "admin@ssd.local", "manager@ssdrecovery.in", "ravi@ssdrecovery.in",
    "anil@ssdrecovery.in", "suresh@ssdrecovery.in", "krishna@ssdrecovery.in",
    "prasanth@ssdrecovery.in", "admin@ssdrecovery.in",
}


def _purge_demo_cases(db):
    """Delete the ICICI FR TEST dataset (seed_fr_test.py tags it with this import batch),
    plus its visits/calls — so no demo cases remain. Real uploads are untouched."""
    batches = db.query(models.ImportBatch).filter(
        models.ImportBatch.filename == "fr_xbkt_july26.xlsx").all()
    bids = [b.id for b in batches]
    if not bids:
        return 0
    case_ids = [r[0] for r in db.query(models.Case.id)
                .filter(models.Case.import_batch_id.in_(bids)).all()]
    if case_ids:
        db.query(models.Visit).filter(models.Visit.case_id.in_(case_ids)).delete(synchronize_session=False)
        db.query(models.CallLog).filter(models.CallLog.case_id.in_(case_ids)).delete(synchronize_session=False)
        # audit rows just reference the case id (denormalised) — null them so nothing dangles
        db.query(models.AuditLog).filter(models.AuditLog.case_id.in_(case_ids)).update(
            {models.AuditLog.case_id: None}, synchronize_session=False)
        db.query(models.Case).filter(models.Case.id.in_(case_ids)).delete(synchronize_session=False)
    for b in batches:
        db.delete(b)
    db.commit()
    return len(case_ids)


def _remap_cases(db):
    """Re-resolve each case's assigned caller / FOS from its stored name, against the
    real (active) employees. Full name, single-word/partial name, or emp_code all work."""
    users = [u for u in db.query(models.User).all() if u.is_active is not False]
    by_code = {u.emp_code.strip().upper(): u for u in users if u.emp_code}
    callers = [(u.name.strip().upper(), u) for u in users if u.name and u.role in ("telecaller", "teamlead")]
    foses = [(u.name.strip().upper(), u) for u in users if u.name and u.role == "fos"]
    caller_by_name = {n: u for n, u in callers}
    fos_by_name = {n: u for n, u in foses}

    def resolve(val, cands, by_name):
        if not val:
            return None
        key = str(val).strip().upper()
        if key in by_code:
            return by_code[key]
        if key in by_name:
            return by_name[key]
        if len(key) < 3:
            return None
        hits, picked = set(), None
        for nm, u in cands:
            w = nm.split()
            if key == nm or key in w or nm.startswith(key) or (w and w[0].startswith(key)):
                hits.add(u.id); picked = u
        return picked if len(hits) == 1 else None

    remapped_c = remapped_f = 0
    for case in db.query(models.Case).all():
        cu = resolve(case.caller_name, callers, caller_by_name)
        if cu and case.assigned_caller_id != cu.id:
            case.assigned_caller_id = cu.id; case.caller_name = cu.name; remapped_c += 1
        fu = resolve(case.fos_name, foses, fos_by_name)
        if fu and case.assigned_fos_id != fu.id:
            case.assigned_fos_id = fu.id; case.fos_name = fu.name; remapped_f += 1
    db.commit()
    return remapped_c, remapped_f


def main(manpower=None, creds=None):
    Base.metadata.create_all(bind=engine)
    _sync_columns()
    db = SessionLocal()
    try:
        # 2) real admin (from .env)
        seed_users(db)

        # 3) import the real employees
        if manpower and creds and os.path.exists(manpower) and os.path.exists(creds):
            import import_manpower
            db.close()
            import_manpower.main(manpower, creds)
            db = SessionLocal()
            print("Employees imported from manpower sheets.")
        else:
            print("(!) Manpower / credentials sheet not supplied — skipped employee import.")

        # 4) purge the demo/test cases (ICICI FR test dataset), then remap what's left
        purged = _purge_demo_cases(db)
        print(f"Purged {purged} demo/test cases (and their visits/calls).")
        rc, rf = _remap_cases(db)
        print(f"Re-mapped {rc} caller assignments and {rf} FOS assignments to real staff.")

        # 5) deactivate demo/test accounts
        off = 0
        for u in db.query(models.User).all():
            if u.email and (u.email.lower() in DEMO_EMAILS or u.email.lower().endswith("@ssd.local")):
                if u.is_active is not False:
                    u.is_active = False; off += 1
        db.commit()
        print(f"Deactivated {off} demo/test account(s).")
    finally:
        db.close()
    print("Production setup complete.")


if __name__ == "__main__":
    mp = sys.argv[1] if len(sys.argv) > 1 else None
    cr = sys.argv[2] if len(sys.argv) > 2 else None
    main(mp, cr)
