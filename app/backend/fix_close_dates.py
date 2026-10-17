"""
One-off: re-align every case's CLOSE DATE with its CURRENT cycle / bank / product / period.

Before the fix, the close date was set once at upload and never updated when the cycle changed
afterwards (DPR upload, "Correct columns" upload, Live-Sheet edit). Example: uploaded as CYC 15,
corrected to CYC 18, but the case still closed on the 15th. New changes are handled automatically
now; this script corrects the cases that already drifted.

USAGE (from app/backend, using the backend's own Python):
    .venv\Scripts\python.exe fix_close_dates.py                    # THIS month — report only
    .venv\Scripts\python.exe fix_close_dates.py --apply            # THIS month — correct them
    .venv\Scripts\python.exe fix_close_dates.py --month 2026-09    # a specific month
    .venv\Scripts\python.exe fix_close_dates.py --all              # every month
Due-date (BRBL) cases keep their sheet due date and are not touched.
"""
import sys
from collections import Counter

sys.path.insert(0, ".")
from app.database import SessionLocal          # noqa: E402
from app import models, close_sync             # noqa: E402

APPLY = "--apply" in sys.argv
ALL = "--all" in sys.argv
if "--month" in sys.argv:
    MONTH = sys.argv[sys.argv.index("--month") + 1]
else:
    from datetime import datetime, timedelta, timezone
    MONTH = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m")   # this month (IST)


def main():
    db = SessionLocal()
    try:
        rows, per = [], Counter()
        q = db.query(models.Case).filter(models.Case.removed.isnot(True), models.Case.period.isnot(None))
        if not ALL:
            q = q.filter(models.Case.period == MONTH)
        checked = 0
        for c in q.order_by(models.Case.bank, models.Case.product, models.Case.id).all():
            checked += 1
            old = (c.close_date, c.closing_type)
            if close_sync.recompute(db, c):
                rows.append((c, old))
                per[f"{c.bank} / {c.product}"] += 1
        scope = "ALL months" if ALL else f"month {MONTH}"
        print(f"\n=== Close-date check — {scope} — {'APPLIED' if APPLY else 'REPORT ONLY (nothing changed)'} ===")
        print(f"Cases checked: {checked}   Close date doesn't match current cycle: {len(rows)}\n")
        for k, n in per.most_common():
            print(f"  {k:<40} {n}")
        print()
        print(f"  {'Case':<8} {'Customer':<24} {'Account / Card':<20} {'Portfolio':<22} {'Cycle':<7} {'Old close':<11}    New close")
        for c, (ocd, ot) in rows:
            acct = (c.account_no or c.card_no or "")[-18:]
            print(f"  #{c.id:<7} {(c.customer_name or '')[:24]:<24} {acct:<20} {(str(c.bank) + ' ' + str(c.product))[:22]:<22} "
                  f"{str(c.cycle or '-')[:7]:<7} {str(ocd or '-'):<11} -> {c.close_date} ({c.closing_type})")
        if APPLY:
            db.commit()
            print("\nDone.")
        else:
            db.rollback()
            print("\nRe-run with  --apply  to correct them.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
