"""One-shot: recompute the LATE flag on existing attendance rows under the new rule.

Why: the "late after" cutoff was changed to a uniform 10:00 for ALL roles (previously non-frontline
roles got until 10:30, so some people who checked in between 10:00-10:30 were saved as present, not
late). That change only affects NEW check-ins — rows already written keep their old flag. This
script re-evaluates existing rows against the current rule so today's / this month's attendance
reflects the 10:00 cutoff.

What it does, per attendance row in range with status == "present" and a check-in time:
  late = (check-in time in IST) > the role's late_after   AND the user is NOT an HO-Manager
  (HO-Manager is exempt from late by design, same as live check-in.)
It only flips the `late` boolean; it never changes present/absent/leave/week-off, check-in times,
worked hours, or anything else. IDEMPOTENT — re-running makes no further change.

Run from the backend folder with the same DATABASE_URL the app uses:
    cd app/backend
    python recompute_attendance_late.py                 # dry-run for TODAY (prints changes)
    python recompute_attendance_late.py --commit        # apply for TODAY
    python recompute_attendance_late.py --period 2026-10 --commit   # whole month (YYYY-MM)
    python recompute_attendance_late.py --all --commit             # every attendance row
"""
import sys
from datetime import datetime, timezone, date as date_cls

from app.database import SessionLocal
from app import models
from app.routers.attendance import _shift, _hm, IST


def _ci_ist_time(check_in_at):
    """Return the check-in clock time in IST (times stored naive are UTC)."""
    dt = check_in_at
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST).time()


def main():
    args = sys.argv[1:]
    commit = "--commit" in args
    do_all = "--all" in args
    period = None
    if "--period" in args:
        period = args[args.index("--period") + 1]

    db = SessionLocal()
    try:
        q = db.query(models.Attendance).filter(models.Attendance.status == "present",
                                                models.Attendance.check_in_at.isnot(None))
        scope = "ALL dates"
        if period:
            y, m = period.split("-")
            start = date_cls(int(y), int(m), 1)
            end = date_cls(int(y) + (1 if int(m) == 12 else 0),
                           1 if int(m) == 12 else int(m) + 1, 1)
            q = q.filter(models.Attendance.date >= start, models.Attendance.date < end)
            scope = f"month {period}"
        elif not do_all:
            today = datetime.now(IST).date()
            q = q.filter(models.Attendance.date == today)
            scope = f"today ({today.isoformat()})"

        rows = q.all()
        # users cache for role + ho_manager flag
        uids = {a.user_id for a in rows}
        users = {u.id: u for u in db.query(models.User).filter(models.User.id.in_(uids)).all()} if uids else {}

        changed = 0
        for a in rows:
            u = users.get(a.user_id)
            if not u:
                continue
            _ss, _se, la = _shift(u.role)
            should_late = (_ci_ist_time(a.check_in_at) > _hm(la)) and not getattr(u, "ho_manager", False)
            if bool(a.late) != bool(should_late):
                print(f"  {a.date}  {u.name or u.id:28}  {u.role:11}  "
                      f"check-in {_ci_ist_time(a.check_in_at):%H:%M}  late {bool(a.late)} -> {bool(should_late)}")
                a.late = bool(should_late)
                changed += 1

        print(f"\nScope: {scope} · rows scanned: {len(rows)} · to re-flag: {changed}")
        if commit and changed:
            db.commit()
            print("Committed.")
        elif changed:
            print("Dry-run — re-run with --commit to apply.")
        else:
            print("Nothing to change.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
