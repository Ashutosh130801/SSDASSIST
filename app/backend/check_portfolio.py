"""
Read-only check: where are a portfolio's cases, month by month, and which upload owns them?
Use it when an upload shows "0 live" to see whether the cases already exist (re-upload only
UPDATED them), were removed by an Undo, or really were not loaded.

USAGE (from app/backend, using the backend's own Python):
    .venv\\Scripts\\python.exe check_portfolio.py AXIS "X"          # bank + part of the product name
    .venv\\Scripts\\python.exe check_portfolio.py AXIS "X" 2026-11  # only one month
Nothing is changed.
"""
import sys
from collections import defaultdict

sys.path.insert(0, ".")
from sqlalchemy import func                     # noqa: E402
from app.database import SessionLocal          # noqa: E402
from app import models                         # noqa: E402

if len(sys.argv) < 3:
    print(__doc__)
    sys.exit(1)
BANK, PROD = sys.argv[1], sys.argv[2]
MONTH = sys.argv[3] if len(sys.argv) > 3 else None

db = SessionLocal()
q = (db.query(models.Case.product, models.Case.period, models.Case.branch, models.Case.removed,
              models.Case.import_batch_id, func.count(models.Case.id))
     .filter(func.upper(models.Case.bank) == BANK.upper(), models.Case.product.ilike(f"%{PROD}%")))
if MONTH:
    q = q.filter(models.Case.period == MONTH)
rows = q.group_by(models.Case.product, models.Case.period, models.Case.branch, models.Case.removed,
                  models.Case.import_batch_id).all()
batches = {b.id: b for b in db.query(models.ImportBatch).all()}
users = {u.id: u.name for u in db.query(models.User.id, models.User.name).all()}

if not rows:
    print(f"No cases at all for bank={BANK} product~'{PROD}'" + (f" month={MONTH}" if MONTH else ""))
    sys.exit(0)

tot = defaultdict(lambda: [0, 0])
print(f"\n{'Product':<16}{'Month':<9}{'Location':<16}{'State':<9}{'Cases':>7}   Owned by upload")
print("-" * 110)
for prod, per, br, rem, bid, n in sorted(rows, key=lambda r: (r[1] or "", r[0] or "", r[2] or "", bool(r[3]))):
    b = batches.get(bid)
    owner = (f"#{bid} {b.filename} ({b.period or '-'}) by {users.get(b.uploaded_by, '-')}, "
             f"{b.created_at:%d-%b %H:%M}" if b else f"#{bid or '-'}")
    state = "REMOVED" if rem else "LIVE"
    print(f"{(prod or '-')[:15]:<16}{(per or '-'):<9}{(br or '-')[:15]:<16}{state:<9}{n:>7}   {owner}")
    tot[(prod, per)][1 if rem else 0] += n
print("-" * 110)
for (prod, per), (live, rem) in sorted(tot.items(), key=lambda x: (x[0][1] or "", x[0][0] or "")):
    print(f"{prod} {per}: {live} live, {rem} removed")
print("\nIf the month you uploaded shows LIVE cases owned by an EARLIER upload, your re-upload only"
      "\nupdated them (that's why the new upload shows 0 live) — the cases are there.")
