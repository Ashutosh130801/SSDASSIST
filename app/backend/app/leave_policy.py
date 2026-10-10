"""Leave units (Sundays are weekly-off and never consume leave) and a shared
daily/monthly attendance classification."""


def working_days(first, last):
    """Days in [first, last] excluding Sundays."""
    if first > last:
        return 0
    total = (last - first).days + 1
    weeks, extra = divmod(total, 7)
    sundays = weeks + sum(1 for i in range(extra) if (first.weekday() + i) % 7 == 6)
    return total - sundays


def effective_days(leave, start=None, end=None):
    first = max(leave.start_date, start) if start else leave.start_date
    last = min(leave.end_date, end) if end else leave.end_date
    if first > last:
        return 0.0
    if leave.half_day:
        return 0.0 if first.weekday() == 6 else 0.5
    return float(working_days(first, last))


def day_credit(attendance, leave, day, today):
    checked_in = bool(attendance and attendance.check_in_at)
    half = bool(leave and leave.half_day)
    result = dict(present=0.0, leave=0.0, absent=0.0, weekoff=0, half_days=0,
                  late=int(bool(checked_in and attendance.late)))
    if day.weekday() == 6 and not checked_in:
        # Sunday stays a week-off even inside an approved leave (and is never 'absent').
        result.update(code="W", status="weekoff", weekoff=1)
    elif leave:
        if half:
            result.update(code="HD", status="half_leave", leave=0.5, half_days=1,
                          present=0.5 if checked_in else 0.0,
                          absent=0.5 if not checked_in and day < today else 0.0)
        else:
            result.update(code="LV", status="leave", leave=1.0, late=0)
    elif checked_in:
        result.update(code="L" if attendance.late else "P", status="present", present=1.0)
    elif day.weekday() == 6:
        result.update(code="W", status="weekoff", weekoff=1)
    elif day > today:
        result.update(code="", status="—")
    else:
        result.update(code="A", status="absent", absent=1.0)
    return result
