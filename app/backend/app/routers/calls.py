from decimal import Decimal
from datetime import datetime, timezone, timedelta, time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user, require_roles

router = APIRouter(prefix="/api/calls", tags=["calls"])

IST = timezone(timedelta(hours=5, minutes=30))


def _ist_today():
    return datetime.now(IST).date()


def _contacted_today(case) -> bool:
    if not case.last_contacted_at:
        return False
    lc = case.last_contacted_at
    if lc.tzinfo is None:
        lc = lc.replace(tzinfo=timezone.utc)
    return lc.astimezone(IST).date() == _ist_today()


@router.post("", response_model=schemas.CallOut)
def log_call(body: schemas.CallCreate, db: Session = Depends(get_db),
             user: models.User = Depends(require_roles("telecaller", "admin"))):
    case = db.query(models.Case).filter(models.Case.id == body.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if user.role == "telecaller" and case.assigned_caller_id != user.id:
        raise HTTPException(status_code=403, detail="This case is not in your queue")

    ptp_dt = datetime.combine(body.ptp_date, time.min).replace(tzinfo=timezone.utc) if body.ptp_date else None
    call = models.CallLog(
        case_id=body.case_id, caller_id=user.id, disposition=body.disposition,
        ptp_amount=body.ptp_amount, ptp_date=ptp_dt, note=body.note,
    )
    db.add(call)

    disp = (body.disposition or "").upper()
    case.disposition = body.disposition
    case.last_contacted_at = datetime.now(timezone.utc)   # -> moves to "Contacted today"

    if disp == "PAID":
        amt = Decimal(str(body.paid_amount or 0))
        if amt > 0:
            case.received_amount = (Decimal(case.received_amount or 0) + amt)
            case.pending_amount = (Decimal(case.funding_amount or 0) - Decimal(case.received_amount or 0))
        case.paid_status = "PAID"
        case.status = "paid"
        case.follow_up_date = None                        # out of the queue
    elif disp in ("PTP", "RTP"):
        case.status = "ptp"
        case.follow_up_date = body.ptp_date or body.follow_up_date   # re-queues on the promised date
    else:
        case.status = "callback"
        case.follow_up_date = body.follow_up_date          # None => due again next day

    db.commit()
    db.refresh(call)
    return call


@router.get("/queue")
def queue(bank: str | None = None, db: Session = Depends(get_db),
          user: models.User = Depends(require_roles("telecaller", "admin"))):
    """Telecaller work queue split into three clear sections so nothing is called
    twice or missed: due now, already contacted today, and scheduled for later."""
    today = _ist_today()
    q = db.query(models.Case)
    if user.role == "telecaller":
        q = q.filter(models.Case.assigned_caller_id == user.id)
    q = q.filter(models.Case.status.notin_(["paid", "closed"]))
    if bank:
        q = q.filter(models.Case.bank == bank)
    cases = q.all()

    due, contacted, upcoming = [], [], []
    for c in cases:
        if _contacted_today(c):
            contacted.append(c)
        elif c.follow_up_date and c.follow_up_date > today:
            upcoming.append(c)
        else:
            due.append(c)

    due.sort(key=lambda c: float(c.pending_amount or 0), reverse=True)
    upcoming.sort(key=lambda c: (c.follow_up_date or today))
    contacted.sort(key=lambda c: c.last_contacted_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    def ser(lst):
        return [schemas.CaseOut.model_validate(x) for x in lst]

    return {
        "due": ser(due), "contacted_today": ser(contacted), "upcoming": ser(upcoming),
        "counts": {"due": len(due), "contacted_today": len(contacted), "upcoming": len(upcoming)},
    }


@router.get("/ptp-tracker")
def ptp_tracker(bank: str | None = None, db: Session = Depends(get_db),
                user: models.User = Depends(require_roles("telecaller", "admin", "manager"))):
    """All active promise-to-pay cases with promised amount + date, split into
    overdue / due today / upcoming so broken promises are chased first."""
    today = _ist_today()
    q = db.query(models.Case).filter(
        models.Case.disposition.in_(["PTP", "RTP"]),
        models.Case.status.notin_(["paid", "closed"]),
    )
    if user.role == "telecaller":
        q = q.filter(models.Case.assigned_caller_id == user.id)
    elif user.role == "manager":
        from sqlalchemy import or_, select
        ids = select(models.User.id).where(models.User.branch == user.branch)
        q = q.filter(or_(models.Case.branch == user.branch,
                         models.Case.assigned_caller_id.in_(ids), models.Case.assigned_fos_id.in_(ids)))
    if bank:
        q = q.filter(models.Case.bank == bank)
    cases = q.all()

    rows = []
    for c in cases:
        last_ptp = (
            db.query(models.CallLog)
            .filter(models.CallLog.case_id == c.id, models.CallLog.disposition.in_(["PTP", "RTP"]))
            .order_by(models.CallLog.created_at.desc()).first()
        )
        promised = c.follow_up_date
        bucket = "overdue" if (promised and promised < today) else ("today" if promised == today else "upcoming")
        rows.append({
            "case": schemas.CaseOut.model_validate(c),
            "ptp_amount": float(last_ptp.ptp_amount) if last_ptp and last_ptp.ptp_amount else None,
            "promised_date": promised.isoformat() if promised else None,
            "bucket": bucket,
        })
    order = {"overdue": 0, "today": 1, "upcoming": 2}
    rows.sort(key=lambda r: (order[r["bucket"]], r["promised_date"] or "9999-12-31"))
    counts = {"overdue": 0, "today": 0, "upcoming": 0}
    for r in rows:
        counts[r["bucket"]] += 1
    return {"rows": rows, "counts": counts}


@router.get("/case/{case_id}", response_model=list[schemas.CallOut])
def calls_for_case(case_id: int, db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)):
    return (
        db.query(models.CallLog)
        .filter(models.CallLog.case_id == case_id)
        .order_by(models.CallLog.created_at.desc())
        .all()
    )
