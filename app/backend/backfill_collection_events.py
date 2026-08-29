"""One-shot backfill: give every already-collected rupee a DATED payment event.

Why: the collections trend and the FTD/MTD/LMTD windows are built from payment EVENTS
(CallLog PAYMENT/PAID + Visit collections). Cases whose `received_amount` was set directly
by an import (an opening balance) never produced an event, so that money is invisible to the
trend even though it shows in the lifetime KPIs. This script closes that gap once, so the
trend reconciles with received without a re-upload.

What it does, per non-removed case with received_amount > 0:
  covered = sum(existing payment events for the case)   # calls (PAYMENT/PAID) + visits
  gap     = received_amount - covered
  if gap > 1:  add ONE CallLog(disposition="PAYMENT", ptp_amount=gap) dated to the case's
               own timeline (updated_at → created_at → now), credited to its caller/FOS.

It is IDEMPOTENT: a second run sees the event it just wrote as "covered" and adds nothing.

Run from the backend folder with the same DATABASE_URL the app uses:
    cd app/backend
    source .venv/bin/activate         # or: .venv\\Scripts\\activate on Windows
    python backfill_collection_events.py            # dry-run: prints what it WOULD do
    python backfill_collection_events.py --commit    # actually write the events
"""
import sys
from datetime import datetime, timezone

from app.database import SessionLocal
from app import models

TOL = 1.0                       # ignore sub-rupee rounding gaps
NOTE = "Backfill: opening collection (dated for trend)"


def _f(x) -> float:
    try:
        return float(x or 0)
    except Exception:
        return 0.0


def main(commit: bool) -> None:
    db = SessionLocal()
    try:
        cases = db.query(models.Case).filter(models.Case.removed.isnot(True)).all()

        # Pre-sum existing events per case in two grouped passes (fast, no per-case queries).
        from sqlalchemy import func
        covered: dict[int, float] = {}
        for cid, amt in (db.query(models.CallLog.case_id,
                                  func.coalesce(func.sum(models.CallLog.ptp_amount), 0))
                         .filter(models.CallLog.disposition.in_(("PAYMENT", "PAID")))
                         .group_by(models.CallLog.case_id).all()):
            covered[cid] = covered.get(cid, 0.0) + _f(amt)
        for cid, amt in (db.query(models.Visit.case_id,
                                  func.coalesce(func.sum(models.Visit.amount_collected), 0))
                         .group_by(models.Visit.case_id).all()):
            covered[cid] = covered.get(cid, 0.0) + _f(amt)

        now = datetime.now(timezone.utc)
        made = 0
        total_gap = 0.0
        for c in cases:
            recv = _f(c.received_amount)
            if recv <= 0:
                continue
            gap = recv - covered.get(c.id, 0.0)
            if gap <= TOL:
                continue
            when = getattr(c, "updated_at", None) or getattr(c, "created_at", None) or now
            credit = c.assigned_caller_id or c.assigned_fos_id
            made += 1
            total_gap += gap
            if commit:
                db.add(models.CallLog(case_id=c.id, caller_id=credit,
                                      disposition="PAYMENT", ptp_amount=round(gap, 2),
                                      note=NOTE, created_at=when))

        if commit:
            db.commit()
            print(f"COMMITTED {made} backfill events, total ₹{total_gap:,.0f}")
        else:
            print(f"DRY-RUN: would create {made} events, total ₹{total_gap:,.0f}")
            print("Re-run with --commit to write them.")
    finally:
        db.close()


if __name__ == "__main__":
    main("--commit" in sys.argv)
