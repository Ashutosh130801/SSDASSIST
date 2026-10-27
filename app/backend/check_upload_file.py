"""
Read-only: compare an upload FILE with what is loaded in RecoverIQ, to find why the file has more
rows than the live case count (e.g. 675 rows in the sheet but 529 live cases). Nothing is changed.

USAGE (from app/backend, using the backend's own Python):
    .venv\\Scripts\\python.exe check_upload_file.py "C:\\path\\AXIS CC X NOV.xlsx" AXIS "X" 2026-11

It reports:
  1. rows in the sheet vs rows the importer actually reads (blank / no-name-no-account rows drop)
  2. rows with NO account number
  3. DUPLICATE account numbers inside the file (the importer keeps ONE case per account+bank+
     product+month, so duplicates collapse into one case) — with names/cards so you can tell a
     genuine repeat from numbers Excel rounded (16+ digit numbers stored as numbers lose digits)
  4. file accounts vs the month's cases in the DB: live / only removed / missing
  5. live cases in the DB that are NOT in the file
  6. every upload of this portfolio+month with rows read / new / updated, and who uploaded it
     (a TEAM LEAD upload keeps only rows whose TL column is that team lead)
"""
import sys
from collections import Counter, defaultdict

sys.path.insert(0, ".")
from sqlalchemy import func                          # noqa: E402
from app.database import SessionLocal               # noqa: E402
from app import models                              # noqa: E402
from app.excel_io import import_workbook, record_to_case_kwargs   # noqa: E402

if len(sys.argv) < 5:
    print(__doc__)
    sys.exit(1)
PATH, BANK, PROD, PERIOD = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]


def norm(v):
    s = ("" if v is None else str(v)).strip()
    return s or None


content = open(PATH, "rb").read()

# 1) raw non-empty rows per sheet (header row excluded) vs records the importer reads
from openpyxl import load_workbook                  # noqa: E402
wb = load_workbook(PATH, read_only=True, data_only=True)
raw = {}
for ws in wb.worksheets:
    n = sum(1 for row in ws.iter_rows(values_only=True) if any(c not in (None, "") for c in row))
    raw[ws.title] = max(n - 1, 0)
records, sheet = import_workbook(content, default_bank=BANK)
print(f"\nFILE: {PATH}")
print(f"  Non-empty rows per sheet (minus 1 header): {raw}")
print(f"  Sheet(s) the importer used: {sheet}")
print(f"  Rows the importer READ: {len(records)}")

kw = [record_to_case_kwargs(r) for r in records]
accts = [norm(k.get("account_no")) for k in kw]

# 2) no account number
no_acct = [k for k, a in zip(kw, accts) if not a]
print(f"\n  Rows with NO account number: {len(no_acct)}")
for k in no_acct[:5]:
    print(f"     e.g. {k.get('customer_name')}  card={k.get('card_no')}")

# 3) duplicates
cnt = Counter(a for a in accts if a)
dups = {a: n for a, n in cnt.items() if n > 1}
collapsed = sum(n - 1 for n in dups.values())
print(f"\n  Distinct account numbers: {len(cnt)}")
print(f"  Account numbers appearing MORE THAN ONCE: {len(dups)}  → {collapsed} row(s) collapse into existing cases")
sus = [a for a in cnt if ("E+" in a.upper()) or (a.isdigit() and len(a) >= 15 and a.endswith("000"))]
if sus:
    print(f"  ⚠ {len(sus)} account number(s) look ROUNDED by Excel (scientific / ending 000 on 15+ digits): {sus[:5]}")
by_acct = defaultdict(list)
for k, a in zip(kw, accts):
    if a in dups:
        by_acct[a].append(k)
shown = 0
for a, ks in sorted(by_acct.items(), key=lambda x: -len(x[1])):
    names = {norm(k.get("customer_name")) for k in ks}
    cards = {norm(k.get("card_no")) for k in ks}
    kind = "SAME customer (true repeat)" if len(names) == 1 else "DIFFERENT customers (number collision!)"
    print(f"     {a}  ×{len(ks)}  — {kind}; names={list(names)[:3]} cards={list(cards)[:3]}")
    shown += 1
    if shown >= 12:
        print("     …")
        break

# 4/5) compare with DB
db = SessionLocal()
q = db.query(models.Case).filter(func.upper(models.Case.bank) == BANK.upper(),
                                 models.Case.product.ilike(f"%{PROD}%"), models.Case.period == PERIOD)
cases = q.all()
live = {c.account_no for c in cases if not c.removed}
removed = {c.account_no for c in cases if c.removed} - live
fset = set(cnt)
print(f"\nDB ({BANK} / *{PROD}* / {PERIOD}): {sum(1 for c in cases if not c.removed)} live case(s), "
      f"{sum(1 for c in cases if c.removed)} removed")
prods = Counter((c.product, c.branch, bool(c.removed)) for c in cases)
for (p, b, r), n in sorted(prods.items(), key=lambda x: (x[0][0] or "", x[0][1] or "")):
    print(f"     {p} · {b or '-'} · {'REMOVED' if r else 'live'}: {n}")
print(f"  File accounts found LIVE: {len(fset & live)}")
print(f"  File accounts only in REMOVED bin: {len(fset & removed)}  {sorted(fset & removed)[:5]}")
missing = sorted(fset - live - removed)
print(f"  File accounts NOT in this month at all: {len(missing)}  {missing[:8]}")
if missing:
    other = (db.query(models.Case.account_no, models.Case.bank, models.Case.product, models.Case.period,
                      models.Case.removed)
             .filter(models.Case.account_no.in_(missing[:500])).all())
    if other:
        print("   → some of these exist under ANOTHER bank/product/month:")
        for a, b, p, per, r in other[:10]:
            print(f"       {a}: {b} / {p} / {per}{' (removed)' if r else ''}")
extra = sorted(live - fset)
print(f"  Live cases NOT in this file: {len(extra)}  {extra[:8]}")

# 6) uploads of this portfolio + month
users = {u.id: (u.name, u.role) for u in db.query(models.User).all()}
bs = (db.query(models.ImportBatch).filter(func.upper(models.ImportBatch.bank) == BANK.upper(),
                                          models.ImportBatch.product.ilike(f"%{PROD}%"))
      .order_by(models.ImportBatch.created_at).all())
print("\nUploads of this portfolio:")
for b in bs:
    nm, rl = users.get(b.uploaded_by, ("-", "-"))
    print(f"  #{b.id} {b.created_at:%d-%b %H:%M}  {b.filename}  month={b.period}  loc={b.branch or '-'}  "
          f"read={b.rows_total} new={b.rows_imported} updated={b.rows_skipped}  by {nm} ({rl})")
print(f"\nIf a TEAM-LEAD upload shows read < {len(records)}, the difference was dropped because those rows'"
      "\nTL column was not that team lead (TL uploads keep only their own team's rows).")
