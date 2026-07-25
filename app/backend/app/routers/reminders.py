"""PTP reminders — surfaces promise-to-pay cases that are due today or overdue to the
staff responsible for them. The SAME case reminds BOTH its assigned field officer and
telecaller, so nobody misses a promised payment."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/api/reminders", tags=["reminders"])
IST = timezone(timedelta(hours=5, minutes=30))


@router.get("")
def my_reminders(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    today = datetime.now(IST).date()
    q = db.query(models.Case).filter(
        models.Case.disposition.in_(["PTP", "RTP"]),
        models.Case.status.notin_(["paid", "closed"]),
        models.Case.follow_up_date.isnot(None),
        models.Case.follow_up_date <= today,
    )
    if user.role == "fos":
        q = q.filter(models.Case.assigned_fos_id == user.id)
    elif user.role == "telecaller":
        q = q.filter(models.Case.assigned_caller_id == user.id)
    elif user.role == "manager":
        ids = select(models.User.id).where(models.User.branch == user.branch)
        q = q.filter(or_(models.Case.branch == user.branch,
                         models.Case.assigned_fos_id.in_(ids), models.Case.assigned_caller_id.in_(ids)))
    cases = q.order_by(models.Case.follow_up_date.asc()).all()

    names = {u.id: u.name for u in db.query(models.User).all()}
    rows = []
    for c in cases:
        rows.append({
            "case_id": c.id, "customer": c.customer_name, "account": c.account_no,
            "bank": c.bank, "product": c.product, "phone": c.phone,
            "ptp_date": c.follow_up_date.isoformat() if c.follow_up_date else None,
            "pending": float(c.pending_amount or 0),
            "overdue": bool(c.follow_up_date and c.follow_up_date < today),
            "fos": names.get(c.assigned_fos_id, ""), "caller": names.get(c.assigned_caller_id, ""),
        })
    overdue = sum(1 for r in rows if r["overdue"])
    return {"date": today.isoformat(), "count": len(rows),
            "overdue": overdue, "due_today": len(rows) - overdue, "rows": rows}
