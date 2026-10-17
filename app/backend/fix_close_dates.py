"""
One-off: re-align every case's CLOSE DATE with its CURRENT cycle / bank / product / period.

Before the fix, the close date was set once at upload and never updated when the cycle changed
afterwards (DPR upload, "Correct columns" upload, Live-Sheet edit). Example: uploaded as CYC 15,
corrected to CYC 18, but the case still closed on the 15th. New changes are handled automatically
now; this script corrects the cases that already drifted.

USAGE (from app/backend, same DATABASE_URL as the app):
    python fix_close_dates.py             # report only — lists what would change
    python fix_close_dates.py --apply     # apply the corrections
Due-date (BRBL) cases keep their sheet due date and are not touched.
"""
import sys
from collections import Counter

sys.path.insert(0, ".")
from app.database import SessionLocal          # noqa: E402
from app import models, close_sync             # noqa: E402

APPLY = "--apply" in sys.argv


def main():
    db = SessionLocal()
    try:
        rows, per = [], Counter()
        for c in db.query(models.Case).filter(models.Case.removed.isnot(True),
                                              models.Case.period.isnot(None)).all():
            old = (c.close_date, c.closing_type)
            if close_sync.recompute(db, c):
                rows.append((c, old))
                per[f"{c.bank} / {c.product}"] += 1
        print(f"\n=== Close-date check — {'APPLIED' if APPLY else 'REPORT ONLY (nothing changed)'} ===")
        print(f"Cases whose close date doesn't match their current cycle: {len(rows)}\n")
        for k, n in per.most_common():
            print(f"  {k:<40} {n}")
        print()
        for c, (ocd, ot) in rows[:40]:
            print(f"  #{c.id:<7} {(c.customer_name or '')[:24]:<24} cyc {str(c.cycle or '-'):<6} "
                  f"{ot or '-'} {ocd or '-'}  ->  {c.closing_type} {c.close_date}")
        if len(rows) > 40:
            print(f"  … and {len(rows) - 40} more")
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
