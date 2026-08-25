from decimal import Decimal
from datetime import datetime, time, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user, require_roles
from ..allocation import run_allocation
from ..config import get_settings
from ..storage import resolve as resolve_photo
from .. import audit

router = APIRouter(prefix="/api/cases", tags=["cases"])


def _needs_geocode(q):
    return q.filter(models.Case.latitude.is_(None)).filter(
        or_(models.Case.address.isnot(None), models.Case.pincode.isnot(None)))


@router.post("/geocode")
def geocode(limit: int = 40, db: Session = Depends(get_db),
            admin: models.User = Depends(require_roles("admin"))):
    """Fill in latitude/longitude for cases that only have an address/pincode,
    so they show up as pins on the field map. Processes up to `limit` per call
    (call again while `remaining` > 0). Uses the free OpenStreetMap (Nominatim)
    geocoder — no API key needed. Nominatim asks for max ~1 request/second, so
    this paces itself and is intentionally gentle."""
    import time
    cases = _needs_geocode(db.query(models.Case)).limit(limit).all()
    geocoded, failed = 0, 0
    headers = {"User-Agent": "RecoverIQ/1.0 (collections app; contact admin)"}
    with httpx.Client(timeout=15, headers=headers) as client:
        for c in cases:
            parts = [p for p in [c.address, c.pincode] if p]
            query = (" ".join(parts) + " India").strip()
            try:
                r = client.get("https://nominatim.openstreetmap.org/search",
                               params={"q": query, "format": "json", "limit": 1, "countrycodes": "in"})
                data = r.json()
                if isinstance(data, list) and data:
                    c.latitude, c.longitude = float(data[0]["lat"]), float(data[0]["lon"])
                    geocoded += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
            time.sleep(1)  # respect Nominatim's ~1 req/sec usage policy
    db.commit()
    remaining = _needs_geocode(db.query(models.Case)).count()
    return {"geocoded": geocoded, "failed": failed, "remaining": remaining}


@router.delete("/all")
def delete_all_cases(confirm: str = Query(""), db: Session = Depends(get_db),
                     admin: models.User = Depends(require_roles("admin"))):
    """DANGER: permanently remove every case and its visits/calls, so a fresh loading
    file can be uploaded from scratch. Requires ?confirm=DELETE-ALL. Staff and settings
    are untouched — only case data is wiped."""
    if confirm != "DELETE-ALL":
        raise HTTPException(status_code=400, detail="Pass confirm=DELETE-ALL to wipe all cases.")
    # break foreign-key links first so the delete is safe on Postgres too
    db.query(models.LocationPing).update({models.LocationPing.active_case_id: None}, synchronize_session=False)
    db.query(models.LegalCase).update({models.LegalCase.case_id: None}, synchronize_session=False)
    v = db.query(models.Visit).delete(synchronize_session=False)
    cl = db.query(models.CallLog).delete(synchronize_session=False)
    n = db.query(models.Case).delete(synchronize_session=False)
    db.query(models.ImportBatch).delete(synchronize_session=False)
    db.commit()
    return {"deleted_cases": n, "deleted_visits": v, "deleted_calls": cl}


def _branch_user_ids(user: models.User):
    return select(models.User.id).where(models.User.branch == user.branch)


def _team_member_ids(user: models.User):
    """User ids of every FOS/caller reporting to this team lead."""
    return select(models.User.id).where(models.User.team_lead_id == user.id)


def teamlead_case_filter(user: models.User):
    """A team lead owns a case when the case's own team-lead field (set from the
    upload sheet) names them — NOT because the handling FOS/caller reports to them.
    So the same FOS/caller can sit under different team leads on different cases,
    and a team lead sees only the cases that carry their name. Matched on the
    team lead's name (case/space-insensitive), with emp_code as a fallback."""
    name = (user.name or "").strip().lower()
    conds = []
    if name:
        conds.append(func.lower(func.trim(models.Case.team_lead)) == name)
    if user.emp_code:
        conds.append(func.lower(func.trim(models.Case.team_lead)) == user.emp_code.strip().lower())
    return or_(*conds) if conds else func.lower(models.Case.team_lead) == "\x00"  # match nothing


def _scope_user_ids(db, user: models.User):
    """Concrete list of staff ids a manager/team-lead may act on. For a team lead this
    is derived per-case: the FOS/callers assigned to cases carrying the lead's name."""
    if user.role == "teamlead":
        rows = db.query(models.Case.assigned_fos_id, models.Case.assigned_caller_id).filter(
            teamlead_case_filter(user)).all()
        ids = set()
        for fos_id, caller_id in rows:
            if fos_id:
                ids.add(fos_id)
            if caller_id:
                ids.add(caller_id)
        return list(ids)
    if user.role == "manager":
        return [uid for (uid,) in db.query(models.User.id).filter(models.User.branch == user.branch).all()]
    return []


_IST_TZ = timezone(timedelta(hours=5, minutes=30))


def _current_period() -> str:
    """The month everyone is currently working in, as 'YYYY-MM' (IST)."""
    return datetime.now(_IST_TZ).strftime("%Y-%m")


def _next_period() -> str:
    """Next month as 'YYYY-MM' (IST). Uploaded-early next-month data is workable now."""
    d = datetime.now(_IST_TZ)
    return f"{d.year + 1:04d}-01" if d.month == 12 else f"{d.year:04d}-{d.month + 1:02d}"


def _case_closed(case: models.Case) -> bool:
    if not case.close_date:
        return False
    return case.close_date < datetime.now(_IST_TZ).date()


def _ensure_open(case: models.Case, user: models.User):
    """Block field/calling operations on a case that has already closed for the month.
    Applies to FOS & telecallers; admin / manager / head office keep the ability to make
    corrections and post DPR payments."""
    if user.role in ("fos", "telecaller") and _case_closed(case):
        raise HTTPException(status_code=403,
                            detail="This case has closed for the month and is locked. Ask an admin if a change is needed.")


def _scope(q, user: models.User, include_removed: bool = False):
    """Restrict rows by role — FO sees own field cases, telecaller sees own queue,
    branch manager sees cases handled by staff in their branch, team lead sees cases
    handled by the FOS/callers who report to them. Removed (soft-deleted) cases are
    hidden everywhere unless explicitly requested."""
    if not include_removed:
        q = q.filter(models.Case.removed.isnot(True))
    # Monthly lifecycle: field/calling staff work the CURRENT month plus any NEXT-month
    # data uploaded early (so it can be allocated & started ahead of time). This month's
    # cases stay visible even after they close (cycle date / month-end) but closed ones are
    # locked. Past months become admin-only history. Cases with no period (legacy) stay on.
    if user.role not in ("admin", "techsupport"):
        q = q.filter(or_(models.Case.period.is_(None),
                         models.Case.period.in_([_current_period(), _next_period()])))
    if user.role == "fos":
        return q.filter(models.Case.assigned_fos_id == user.id)
    if user.role == "telecaller":
        return q.filter(models.Case.assigned_caller_id == user.id)
    if user.role == "teamlead":
        # Case-level ownership: the case's team_lead (from the upload) names this lead.
        return q.filter(teamlead_case_filter(user))
    if user.role == "manager":
        ids = _branch_user_ids(user)
        # A case belongs to a branch if it's tagged with that branch OR handled by its staff.
        return q.filter(or_(models.Case.branch == user.branch,
                            models.Case.assigned_fos_id.in_(ids),
                            models.Case.assigned_caller_id.in_(ids)))
    return q  # admin: everything


def propensity(c) -> int:
    """Heuristic 0-100 'likelihood to recover' score to help prioritise cases.
    Pure function of the case's current signals (no extra queries)."""
    s = 50
    disp = (c.disposition or "").upper()
    if "PTP" in disp:                       # includes BPTP; RTP (Refuse to Pay) is NOT a promise
        s += 22
    if (c.paid_status or "") == "PARTIAL":
        s += 15
    if float(c.received_amount or 0) > 0:
        s += 8
    if any(x in disp for x in ("RTP", "RNR", "SWITCH", "WRONG", "NOT REACHABLE", "REFUSED", "DISPUTE")):
        s -= 22
    if "X" in (c.bucket or "").upper():
        s -= 8
    if c.last_contacted_at:
        s += 5
    if float(c.pending_amount or 0) > 100000:
        s -= 10
    return max(1, min(99, s))


def _with_score(cases):
    for c in cases:
        c.propensity = propensity(c)
    return cases


_IST = timezone(timedelta(hours=5, minutes=30))


def _mark_today(db, cases):
    """Tag each case with contacted_today / visited_today so the FOS & caller views can
    sink touched cases and keep untouched work on top."""
    today = datetime.now(_IST).date()
    start = datetime.combine(today, time.min, tzinfo=_IST).astimezone(timezone.utc)
    ids = [c.id for c in cases]
    visited = set()
    if ids:
        visited = {vid for (vid,) in db.query(models.Visit.case_id).filter(
            models.Visit.case_id.in_(ids), models.Visit.created_at >= start).distinct().all()}
    for c in cases:
        c.visited_today = c.id in visited
        lc = c.last_contacted_at
        if lc and lc.tzinfo is None:
            lc = lc.replace(tzinfo=timezone.utc)
        c.contacted_today = bool(lc and lc.astimezone(_IST).date() == today)
    _attach_assignees(db, cases)
    return cases


def _attach_assignees(db, cases):
    """Resolve the assigned FOS/caller's name + phone onto each case so the UI can
    show 'Call FOS' / 'Call Caller' buttons."""
    ids = {c.assigned_fos_id for c in cases if c.assigned_fos_id} \
        | {c.assigned_caller_id for c in cases if c.assigned_caller_id}
    umap = {}
    if ids:
        for uid, name, phone, code in db.query(
                models.User.id, models.User.name, models.User.phone, models.User.emp_code).filter(models.User.id.in_(ids)).all():
            umap[uid] = (name, phone, code)
    for c in cases:
        f = umap.get(c.assigned_fos_id)
        cc = umap.get(c.assigned_caller_id)
        c.assigned_fos_name = f[0] if f else None
        c.assigned_fos_phone = f[1] if f else None
        c.assigned_fos_code = f[2] if f else None
        c.assigned_caller_name = cc[0] if cc else None
        c.assigned_caller_phone = cc[1] if cc else None
        c.assigned_caller_code = cc[2] if cc else None
    return cases


@router.get("", response_model=list[schemas.CaseOut])
def list_cases(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
    bank: str | None = None,
    product: str | None = None,
    segment: str | None = None,
    branch: str | None = None,
    status: str | None = None,
    paid_status: str | None = None,
    search: str | None = None,
    period: str | None = None,          # "YYYY-MM" — admin can view a past month's cases
    month_bucket: str | None = None,    # 'current' | 'next' — this month vs next month
    area: str | None = None,            # AREA/region code (team) — scope to one area
    closed: bool | None = None,         # True = only closed(locked), False = only open
    closing_type: str | None = None,    # cyc / month_end / due_date
    cyc: int | None = None,             # cycle day-of-month it closes on
    caller_id: int | None = None,       # cases currently assigned to this telecaller (for transfers)
    fos_id: int | None = None,          # cases currently assigned to this FOS
    team_lead: str | None = None,       # cases currently under this team-lead (name or emp code)
    cycles: str | None = None,          # multi-select cycle filter — CSV of cycle values (e.g. "2,3")
    fos_ids: str | None = None,         # multi-select FOS filter — CSV of user ids
    caller_ids: str | None = None,      # multi-select caller filter — CSV of user ids
    with_notes: bool = False,           # attach merged notes/remarks history (live sheet)
    limit: int = Query(500, le=5000),
    offset: int = 0,
):
    q = _scope(db.query(models.Case), user)
    if caller_id:
        q = q.filter(models.Case.assigned_caller_id == caller_id)
    if fos_id:
        q = q.filter(models.Case.assigned_fos_id == fos_id)
    # ---- multi-select filters (all AND-combined with everything else) ----
    _cyc_list = [c.strip() for c in (cycles or "").split(",") if c.strip()]
    if _cyc_list:
        q = q.filter(func.lower(func.trim(func.coalesce(models.Case.cycle, ""))).in_(
            [c.lower() for c in _cyc_list]))
    _fos_list = [int(x) for x in (fos_ids or "").split(",") if x.strip().isdigit()]
    if _fos_list:
        q = q.filter(models.Case.assigned_fos_id.in_(_fos_list))
    _caller_list = [int(x) for x in (caller_ids or "").split(",") if x.strip().isdigit()]
    if _caller_list:
        q = q.filter(models.Case.assigned_caller_id.in_(_caller_list))
    if team_lead:
        tl = team_lead.strip().lower()
        q = q.filter(func.lower(func.trim(models.Case.team_lead)) == tl)
    if period:
        q = q.filter(models.Case.period == period)
    if month_bucket == "current":
        q = q.filter(models.Case.period == _current_period())
    elif month_bucket == "next":
        q = q.filter(models.Case.period == _next_period())
    if closing_type:
        q = q.filter(models.Case.closing_type == closing_type)
    if closed is not None:
        today = datetime.now(_IST_TZ).date()
        if closed:
            q = q.filter(models.Case.close_date.isnot(None), models.Case.close_date < today)
        else:
            q = q.filter(or_(models.Case.close_date.is_(None), models.Case.close_date >= today))
    if bank:
        q = q.filter(models.Case.bank == bank)
    if product:
        q = q.filter(models.Case.product == product)
    if segment:
        q = q.filter(models.Case.segment == segment)
    if branch:
        q = q.filter(models.Case.branch == branch)
    if area:
        q = q.filter(models.Case.team == area)
    if status:
        q = q.filter(models.Case.status == status)
    if paid_status:
        q = q.filter(models.Case.paid_status == paid_status)
    if search:
        like = f"%{search}%"
        q = q.filter(or_(
            models.Case.customer_name.ilike(like),
            models.Case.account_no.ilike(like),
            models.Case.phone.ilike(like),
            models.Case.pincode.ilike(like),
        ))
    rows = _mark_today(db, _with_score(q.order_by(models.Case.updated_at.desc()).offset(offset).limit(limit).all()))
    if with_notes:
        from ..notes import case_notes_map, join_notes
        nmap = case_notes_map(db, [c.id for c in rows], limit=5)
        for c in rows:
            ns = nmap.get(c.id, [])
            c.notes = ns
            c.notes_text = join_notes(ns)
    return rows


class EscalateIn(BaseModel):
    to_user_id: int | None = None       # default: escalate to the actor themselves
    note: str | None = None


def _manager_owns(db, actor, case):
    if actor.role == "manager" and case.branch != actor.branch:
        raise HTTPException(status_code=403, detail="Not in your branch")
    if actor.role == "teamlead":
        tl = (case.team_lead or "").strip().lower()
        owns = bool(tl) and (tl == (actor.name or "").strip().lower()
                             or (actor.emp_code and tl == actor.emp_code.strip().lower()))
        if not owns and case.escalated_to != actor.id:
            raise HTTPException(status_code=403, detail="Not one of your team's cases")


@router.get("/escalated", response_model=list[schemas.CaseOut])
def escalated_cases(mine: bool = False, db: Session = Depends(get_db),
                    actor: models.User = Depends(require_roles("admin", "manager", "backend", "headoffice", "teamlead"))):
    """Cases pulled off the field/calling staff. `mine=true` limits to ones escalated to me."""
    q = db.query(models.Case).filter(models.Case.escalated.is_(True), models.Case.removed.isnot(True))
    if actor.role == "manager":
        q = q.filter(models.Case.branch == actor.branch)
    if actor.role == "teamlead" or mine:
        q = q.filter(models.Case.escalated_to == actor.id)
    return _mark_today(db, _with_score(q.order_by(models.Case.updated_at.desc()).all()))


@router.post("/{case_id}/escalate")
def escalate_case(case_id: int, body: EscalateIn = EscalateIn(), db: Session = Depends(get_db),
                  actor: models.User = Depends(require_roles("admin", "manager", "backend", "teamlead"))):
    """Take a hard/high-value case away from its FOS & caller and own it personally.
    It leaves their queues and individual performance, but stays in MIS & feedback
    (which key off the case's own fos_name/caller/product, not the live assignment)."""
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    _manager_owns(db, actor, case)
    owner_id = body.to_user_id or actor.id
    owner = db.query(models.User).filter(models.User.id == owner_id).first()
    if not owner or owner.role not in ("admin", "manager", "backend", "headoffice", "teamlead"):
        raise HTTPException(status_code=400, detail="Escalation owner must be admin, manager, back-office, head office or team lead")
    case.escalated = True
    case.escalated_to = owner_id
    case.escalated_by = actor.id
    case.escalated_at = datetime.now(timezone.utc)
    case.assigned_fos_id = None            # drop from the FOS queue / performance
    case.assigned_caller_id = None         # drop from the caller queue / performance
    if body.note:
        case.allocation_reason = f"Escalated: {body.note}"
    audit.record(db, actor, "escalate", case, new=owner.name,
                 detail=f"Escalated to {owner.name}" + (f": {body.note}" if body.note else ""),
                 target_user_id=owner_id)
    audit.stamp_case(case, actor)
    db.commit()
    from .realtime import notify_data_changed
    notify_data_changed(case.bank, case.product)
    return {"ok": True, "escalated_to": owner_id}


@router.post("/{case_id}/deescalate")
def deescalate_case(case_id: int, db: Session = Depends(get_db),
                    actor: models.User = Depends(require_roles("admin", "manager", "backend", "headoffice", "teamlead"))):
    """Release an escalated case back to the pool (admin can re-run allocation to reassign)."""
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    _manager_owns(db, actor, case)
    case.escalated = False
    case.escalated_to = None
    audit.record(db, actor, "deescalate", case, detail="Released escalation back to pool")
    audit.stamp_case(case, actor)
    db.commit()
    from .realtime import notify_data_changed
    notify_data_changed(case.bank, case.product)
    return {"ok": True}


@router.get("/areas")
def portfolio_areas(bank: str | None = None, product: str | None = None, branch: str | None = None,
                    db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Distinct AREA codes (team) in a portfolio, so the UI can offer an area filter."""
    q = _scope(db.query(models.Case.team).distinct(), user)
    if bank:
        q = q.filter(models.Case.bank == bank)
    if product:
        q = q.filter(models.Case.product == product)
    if branch:
        q = q.filter(models.Case.branch == branch)
    return sorted({(t or "").strip() for (t,) in q.all() if t and str(t).strip()})


def _period_bucket(month_bucket):
    """'current' → this month, 'next' → next month, else None (all months)."""
    if month_bucket == "current":
        return _current_period()
    if month_bucket == "next":
        return _next_period()
    return None


def _portfolio_rows(db, user, period=None):
    """Every visible case reduced to the few fields the portfolio cards need. Recovered / Pending
    are computed the SAME way the case detail does — real base (FUNDING → TOS → ENR) minus cash
    received — NOT the stored pending_amount column (only filled once a payment/edit lands).
    When `period` is given, only that month's book is counted (clean month-wise separation)."""
    q = _scope(db.query(
        models.Case.bank, models.Case.product, models.Case.segment, models.Case.branch,
        models.Case.branch_explicit, models.Case.period,
        models.Case.funding_amount, models.Case.total_outstanding, models.Case.enr,
        models.Case.principal_outstanding, models.Case.received_amount,
    ), user)
    if period:
        q = q.filter(models.Case.period == period)
    return q.all()


def _blank(d):
    return {"count": 0, "pending": 0.0, "received": 0.0, "count_current": 0, "count_next": 0, **d}


@router.get("/product-summary")
def product_summary(month_bucket: str | None = None, db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)):
    """Portfolio cards, grouped by BANK + PRODUCT (no accidental branch split). A product is only
    branch-split when at least one of its cases had a branch chosen EXPLICITLY at upload; those
    carry a `branches` breakdown so the UI can offer location sub-cards. FOS-inherited branches do
    NOT split a portfolio. `month_bucket` (current/next/all) scopes the whole section to one month."""
    cur, nxt = _current_period(), _next_period()
    agg: dict = {}
    for b, p, s, br, bexp, per, fund, tos, enr, pos, recv in _portfolio_rows(db, user, _period_bucket(month_bucket)):
        base = float(fund or 0) or float(tos or 0) or float(enr or 0) or float(pos or 0)   # funding → TOS → ENR → POS
        rc = float(recv or 0)
        pend = max(0.0, base - rc)
        key = (b, p)
        d = agg.setdefault(key, _blank({"segment": s, "branch_split": False, "branches": {}}))
        d["count"] += 1; d["received"] += rc; d["pending"] += pend
        if per == cur: d["count_current"] += 1
        elif per == nxt: d["count_next"] += 1
        if bexp:
            d["branch_split"] = True
        # per-branch breakdown (only meaningful for split products; cheap to always keep)
        bk = (br or "").strip() or "— No location —"
        bd = d["branches"].setdefault(bk, _blank({"branch": bk}))
        bd["count"] += 1; bd["received"] += rc; bd["pending"] += pend
        if per == cur: bd["count_current"] += 1
        elif per == nxt: bd["count_next"] += 1
    out = []
    for (b, p), d in agg.items():
        branches = sorted(d.pop("branches").values(), key=lambda x: x["branch"]) if d["branch_split"] else []
        out.append({"bank": b or "—", "product": p or "—", "branch": "", **d, "branches": branches})
    out.sort(key=lambda x: (x["bank"], x["product"]))
    return out


# Bank name → primary domain, so the UI can pull a logo from logo.clearbit.com/<domain>.
# Unknown banks fall back to an initials badge on the frontend.
_BANK_DOMAIN = {
    "ICICI": "icicibank.com", "AXIS": "axisbank.com", "HDFC": "hdfcbank.com",
    "SBI": "sbi.co.in", "KOTAK": "kotak.com", "RBL": "rblbank.com",
    "INDUSIND": "indusind.com", "YES": "yesbank.in", "IDFC": "idfcfirstbank.com",
    "BAJAJ": "bajajfinserv.in", "AMEX": "americanexpress.com", "CITI": "citibank.com",
    "HSBC": "hsbc.co.in", "STANDARD CHARTERED": "sc.com", "FEDERAL": "federalbank.co.in",
    "BOB": "bankofbaroda.in", "PNB": "pnbindia.in", "CANARA": "canarabank.com",
    "UNION": "unionbankofindia.co.in", "AU": "aubank.in", "DBS": "dbs.com",
    "PIRAMAL": "piramalfinance.com", "TATA": "tatacapital.com", "TATA CAPITAL": "tatacapital.com",
    "ADITYA BIRLA": "adityabirlacapital.com", "ABFL": "adityabirlacapital.com",
    "L&T": "ltfinance.com", "LTFS": "ltfinance.com", "MAHINDRA": "mahindrafinance.com",
    "MUTHOOT": "muthootfinance.com", "MANAPPURAM": "manappuram.com",
    "SHRIRAM": "shriramfinance.in", "CHOLA": "cholamandalam.com", "CHOLAMANDALAM": "cholamandalam.com",
    "FULLERTON": "grihashakti.com", "HERO": "herofincorp.com", "HERO FINCORP": "herofincorp.com",
    "IIFL": "iifl.com", "POONAWALLA": "poonawallafincorp.com", "UGRO": "ugrocapital.com",
    "BANDHAN": "bandhanbank.com", "EQUITAS": "equitasbank.com", "UJJIVAN": "ujjivansfb.in",
    "INDIABULLS": "indiabullshomeloans.com", "DEUTSCHE": "deutschebank.co.in",
    "SCB": "sc.com", "IDBI": "idbibank.in", "KVB": "kvb.co.in", "SARASWAT": "saraswatbank.com",
}


def _bank_domain(name: str) -> str | None:
    key = (name or "").strip().upper()
    if key in _BANK_DOMAIN:
        return _BANK_DOMAIN[key]
    for k, v in _BANK_DOMAIN.items():          # loose contains match (e.g. "ICICI BANK")
        if k in key:
            return v
    return None


@router.get("/portfolio-banks")
def portfolio_banks(month_bucket: str | None = None, db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)):
    """One card per BANK that has uploaded products — the top level of portfolio navigation.
    Carries a logo domain (for logo.clearbit.com) plus product/case counts and money totals,
    scoped to `month_bucket` (current/next/all) so the whole section is one month at a time."""
    agg: dict = {}
    prods: dict = {}
    for b, p, s, br, bexp, per, fund, tos, enr, pos, recv in _portfolio_rows(db, user, _period_bucket(month_bucket)):
        base = float(fund or 0) or float(tos or 0) or float(enr or 0) or float(pos or 0)
        rc = float(recv or 0)
        bank = b or "—"
        d = agg.setdefault(bank, _blank({"bank": bank}))
        d["count"] += 1; d["received"] += rc; d["pending"] += max(0.0, base - rc)
        prods.setdefault(bank, set()).add(p or "—")
    out = []
    for bank, d in agg.items():
        d["product_count"] = len(prods.get(bank, ()))
        d["logo_domain"] = _bank_domain(bank)
        out.append(d)
    out.sort(key=lambda x: x["bank"])
    return out


@router.get("/filter-options")
def filter_options(bank: str | None = None, product: str | None = None, branch: str | None = None,
                   db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Distinct cycles + the FOS and callers actually present in a portfolio, so the case-list and
    MIS filter dropdowns only offer values that exist. Names resolve to full name + emp code."""
    q = _scope(db.query(
        models.Case.cycle, models.Case.assigned_fos_id, models.Case.assigned_caller_id), user)
    if bank:
        q = q.filter(models.Case.bank == bank)
    if product:
        q = q.filter(models.Case.product == product)
    if branch:
        q = q.filter(models.Case.branch == branch)
    cycles, fos_ids, caller_ids = set(), set(), set()
    for cyc, fid, cid in q.all():
        if cyc is not None and str(cyc).strip():
            cycles.add(str(cyc).strip())
        if fid:
            fos_ids.add(fid)
        if cid:
            caller_ids.add(cid)
    umap = {u.id: u for u in db.query(models.User).filter(
        models.User.id.in_(fos_ids | caller_ids)).all()} if (fos_ids or caller_ids) else {}
    def _people(ids):
        out = [{"id": i, "name": umap[i].name if i in umap else f"#{i}",
                "code": (umap[i].emp_code if i in umap else None)} for i in ids]
        return sorted(out, key=lambda x: (x["name"] or "").lower())
    def _cyc_sort(c):
        try:
            return (0, int(c))
        except (TypeError, ValueError):
            return (1, c)
    return {"cycles": sorted(cycles, key=_cyc_sort),
            "fos": _people(fos_ids), "callers": _people(caller_ids)}


@router.get("/removed", response_model=list[schemas.CaseOut])
def removed_cases(bank: str | None = None, product: str | None = None,
                  db: Session = Depends(get_db),
                  actor: models.User = Depends(require_roles("headoffice", "admin"))):
    """The Removed-cases bin — soft-deleted cases head office can review and restore.
    Declared before /{case_id} so the literal path isn't captured as an id."""
    q = db.query(models.Case).filter(models.Case.removed.is_(True))
    if bank:
        q = q.filter(models.Case.bank == bank)
    if product:
        q = q.filter(models.Case.product == product)
    return _mark_today(db, _with_score(q.order_by(models.Case.removed_at.desc()).all()))


@router.get("/{case_id}", response_model=schemas.CaseOut)
def get_case(case_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    case = _scope(db.query(models.Case), user).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    case.propensity = propensity(case)
    _mark_today(db, [case])            # set visited_today / contacted_today (never null)
    return case


@router.post("", response_model=schemas.CaseOut)
def create_case(body: schemas.CaseCreate, db: Session = Depends(get_db),
                admin: models.User = Depends(require_roles("admin"))):
    case = models.Case(**body.model_dump())
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


@router.patch("/{case_id}", response_model=schemas.CaseOut)
def update_case(case_id: int, body: schemas.CaseUpdate, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)):
    case = _scope(db.query(models.Case), user).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    data = body.model_dump(exclude_unset=True)
    # admin reassigns freely; manager/team-lead may reassign only within their own people.
    if user.role in ("admin", "manager", "teamlead"):
        if user.role in ("manager", "teamlead"):
            allowed = set(_scope_user_ids(db, user))
            for key in ("assigned_fos_id", "assigned_caller_id"):
                if key in data and data[key] is not None and data[key] not in allowed:
                    raise HTTPException(status_code=403, detail="Can only reassign to your own team")
    else:
        data.pop("assigned_fos_id", None)
        data.pop("assigned_caller_id", None)
    # Audit every field that actually changes; assignment changes get a clearer action.
    for k, v in data.items():
        old = getattr(case, k, None)
        if str(old) == str(v):
            continue
        setattr(case, k, v)
        if k in ("assigned_fos_id", "assigned_caller_id"):
            who = db.query(models.User.name).filter(models.User.id == v).scalar() if v else None
            audit.record(db, user, "deallocate" if v is None else "reassign", case,
                         field=k, old=old, new=v,
                         detail=f"{k.replace('_id','')} → {who or 'unassigned'}", target_user_id=v)
        else:
            audit.record(db, user, "edit", case, field=k, old=old, new=v)
    audit.stamp_case(case, user)
    # keep pending consistent when received changes — use the same collection base
    # (funding → TOS → ENR) as record_payment, and never let pending go below zero.
    if "received_amount" in data:
        pend = _pay_base_total(case) - Decimal(case.received_amount or 0)
        case.pending_amount = pend if pend > 0 else Decimal(0)
        if Decimal(case.received_amount or 0) > 0 and case.pending_amount <= 0:
            case.paid_status = "PAID"
            case.status = "paid"
    db.commit()
    db.refresh(case)
    return case


@router.post("/allocate")
def allocate(body: schemas.AllocateRequest, db: Session = Depends(get_db),
             admin: models.User = Depends(require_roles("admin"))):
    return run_allocation(db, only_unallocated=body.only_unallocated, bank=body.bank)


class BulkReassign(BaseModel):
    case_ids: list[int]
    # Any field left as the sentinel "keep" is untouched. Use null to DE-ALLOCATE
    # (clear the FOS/caller) or "" to clear the team-lead tag.
    assigned_fos_id: int | None | str = "keep"
    assigned_caller_id: int | None | str = "keep"
    team_lead: str | None = "keep"
    # Preferred: pick a team lead by their user id from a dropdown; we store their name on the case
    # (that's what the team-lead scope matches on). null clears it; "keep" leaves it.
    team_lead_id: int | None | str = "keep"


@router.post("/bulk-reassign")
def bulk_reassign(body: BulkReassign, db: Session = Depends(get_db),
                  user: models.User = Depends(require_roles("admin", "headoffice", "manager", "teamlead"))):
    """De-allocate and/or re-allocate one or many cases in a single action.
    - assigned_fos_id / assigned_caller_id: an id to assign, null to de-allocate, "keep" to leave.
    - team_lead: a name to set, "" to clear, "keep" to leave.
    Manager/team-lead may only assign to staff within their own scope."""
    if not body.case_ids:
        raise HTTPException(status_code=400, detail="No cases selected")
    cases = _scope(db.query(models.Case), user).filter(models.Case.id.in_(body.case_ids)).all()
    if not cases:
        raise HTTPException(status_code=404, detail="No matching cases in your scope")

    def _uname(uid):
        return db.query(models.User.name).filter(models.User.id == uid).scalar() if uid else None

    # A team lead chosen by id becomes a NAME on the case (the team-lead scope matches on name).
    tl_target = body.team_lead        # legacy: free-text name / "keep" / ""
    if body.team_lead_id != "keep":
        tl_target = "" if body.team_lead_id is None else (_uname(int(body.team_lead_id)) or "")

    # Managers/team-leads can only hand cases to staff they oversee.
    if user.role in ("manager", "teamlead"):
        allowed = set(_scope_user_ids(db, user))
        for key in ("assigned_fos_id", "assigned_caller_id"):
            val = getattr(body, key)
            if val not in ("keep", None) and val not in allowed:
                raise HTTPException(status_code=403, detail="Can only assign to your own team")

    changed = 0
    for case in cases:
        touched = False
        for key in ("assigned_fos_id", "assigned_caller_id"):
            val = getattr(body, key)
            if val == "keep":
                continue
            old = getattr(case, key)
            new = None if val is None else int(val)
            if old == new:
                continue
            setattr(case, key, new)
            audit.record(db, user, "deallocate" if new is None else "reassign", case,
                         field=key, old=_uname(old) or old, new=_uname(new) or new,
                         detail=f"{key.replace('_id','')} → {_uname(new) or 'unassigned'}",
                         target_user_id=new)
            touched = True
        if tl_target != "keep":
            old_tl = case.team_lead
            new_tl = (tl_target or None)
            if (old_tl or None) != new_tl:
                case.team_lead = new_tl
                audit.record(db, user, "reassign" if new_tl else "deallocate", case,
                             field="team_lead", old=old_tl, new=new_tl,
                             detail=f"team lead → {new_tl or 'cleared'}")
                touched = True
        if touched:
            audit.stamp_case(case, user)
            changed += 1
    db.commit()
    return {"updated": changed, "requested": len(body.case_ids)}


class PaymentIn(BaseModel):
    amount: Decimal
    mode: str = "UPI"
    note: str | None = None
    norm_stab: str | None = None      # NORM / STAB paid (credit-card cases)


@router.post("/{case_id}/payment", response_model=schemas.CaseOut)
def record_payment(case_id: int, body: PaymentIn, db: Session = Depends(get_db),
                   user: models.User = Depends(require_roles("telecaller", "admin", "fos"))):
    """Record a collection against a case: adds to received, recomputes pending
    with Decimal precision, and writes an entry to the case's activity history."""
    case = _scope(db.query(models.Case), user).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    _ensure_open(case, user)
    amt = Decimal(str(body.amount or 0))
    if amt <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero")

    case.received_amount = (Decimal(case.received_amount or 0) + amt)
    # Pending is always the real balance = base (TOS when no funding) − received. It stays
    # visible even after the case is resolved; it does NOT get zeroed on 'paid'.
    pend = _pay_base_total(case) - Decimal(case.received_amount or 0)
    case.pending_amount = pend if pend > 0 else Decimal(0)
    if body.norm_stab:
        ns = body.norm_stab.upper()
        case.norm_stab = "ROLLBACK" if "ROLL" in ns else ("STAB" if "STAB" in ns else ("NORM" if "NORM" in ns else case.norm_stab))
    # A NORM/STAB (settlement) payment resolves the case regardless of the remaining balance;
    # a full collection (nothing left) also resolves it. Otherwise it's a partial.
    if bool(body.norm_stab) or pend <= 0:
        case.paid_status = "PAID"
        case.status = "paid"
        case.follow_up_date = None
    else:
        case.paid_status = "PARTIAL"

    note = f"₹{amt} via {body.mode}" + (f" — {body.note}" if body.note else "")
    db.add(models.CallLog(case_id=case.id, caller_id=user.id,
                          disposition="PAYMENT", ptp_amount=amt, note=note))
    audit.record(db, user, "payment", case, new=str(amt),
                 detail=f"Collected ₹{amt} via {body.mode}" + (f" ({body.note})" if body.note else ""))
    audit.stamp_case(case, user)
    db.commit()
    db.refresh(case)
    from .realtime import notify_data_changed
    notify_data_changed(case.bank, case.product)
    return case


# Callers may flip their own cases too (scoped by _scope); head office/back-office/managers
# and admins may flip any case they can see.
PAY_EDIT_ROLES = ("admin", "headoffice", "manager", "backend", "telecaller", "teamlead")


class MarkPaidIn(BaseModel):
    amount: Decimal | None = None            # blank => clear the full pending
    norm_stab: str | None = None             # NORM / STAB (credit-card cases)
    mode: str | None = "DPR"
    note: str | None = None


def _pay_base_total(case) -> Decimal:
    """The full amount the case is worth — the base for PENDING (= base − received). Funding-load
    sheets carry a FUNDING AMOUNT; CC/PL-BL fall back to Total Outstanding (TOS), then ENR, and
    finally Principal Outstanding (POS) for products like 180+ that only carry a POS figure. This
    order guarantees pending reflects the real outstanding instead of showing 0."""
    for v in (case.funding_amount, case.total_outstanding, case.enr,
              getattr(case, "principal_outstanding", 0)):
        d = Decimal(v or 0)
        if d > 0:
            return d
    return Decimal(0)


@router.get("/{case_id}/pay-state")
def pay_state(case_id: int, db: Session = Depends(get_db),
              actor: models.User = Depends(require_roles(*PAY_EDIT_ROLES))):
    """Snapshot used by the head-office live-sheet popups before flipping paid/unpaid —
    current figures plus the last logged payment (so a revert can show what will be undone)."""
    case = _scope(db.query(models.Case), actor).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    last = (db.query(models.CallLog)
            .filter(models.CallLog.case_id == case_id,
                    models.CallLog.disposition.in_(("PAID", "PAYMENT")),
                    models.CallLog.ptp_amount > 0)
            .order_by(models.CallLog.created_at.desc()).first())
    return {
        "id": case.id, "customer_name": case.customer_name, "card_no": case.card_no,
        "account_no": case.account_no, "segment": case.segment,
        "received_amount": float(case.received_amount or 0), "pending_amount": float(case.pending_amount or 0),
        "paid_status": case.paid_status, "status": case.status, "norm_stab": case.norm_stab,
        "funding_amount": float(case.funding_amount or 0), "enr": float(case.enr or 0),
        "last_payment": ({"amount": float(last.ptp_amount or 0), "at": last.created_at, "note": last.note}
                         if last else None),
    }


@router.post("/{case_id}/mark-paid", response_model=schemas.CaseOut)
def mark_paid(case_id: int, body: MarkPaidIn = MarkPaidIn(), db: Session = Depends(get_db),
              actor: models.User = Depends(require_roles(*PAY_EDIT_ROLES))):
    """Head office marks a case PAID (e.g. the customer paid the bank directly, per the DPR).
    Records the amount + NORM/STAB, credits the assigned caller's activity, and reflects
    everywhere (recovered/resolved KPIs, MIS, feedback) since those key off the case fields."""
    case = _scope(db.query(models.Case), actor).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    amt = Decimal(str(body.amount)) if body.amount is not None else Decimal(0)
    if amt <= 0:                                    # default to whatever is still outstanding
        amt = _pay_base_total(case) - Decimal(case.received_amount or 0)
    if amt <= 0:
        raise HTTPException(status_code=400, detail="Nothing outstanding to mark paid — enter an amount")
    case.received_amount = Decimal(case.received_amount or 0) + amt
    pend = _pay_base_total(case) - Decimal(case.received_amount or 0)
    case.pending_amount = pend if pend > 0 else Decimal(0)
    case.paid_status = "PAID"
    case.status = "paid"
    case.follow_up_date = None
    if body.norm_stab:
        ns = body.norm_stab.upper()
        case.norm_stab = "ROLLBACK" if "ROLL" in ns else ("STAB" if "STAB" in ns else ("NORM" if "NORM" in ns else case.norm_stab))
    credit_id = case.assigned_caller_id or case.assigned_fos_id or actor.id
    tag = f" ({case.norm_stab})" if case.norm_stab else ""
    db.add(models.CallLog(case_id=case.id, caller_id=credit_id, disposition="PAID", ptp_amount=amt,
                          note=f"{body.mode or 'DPR'}: customer paid ₹{amt}{tag}" + (f" — {body.note}" if body.note else "")))
    case.last_contacted_at = datetime.now(timezone.utc)
    audit.record(db, actor, "paid", case, old="UNPAID", new="PAID", detail=f"Marked PAID ₹{amt}{tag}")
    audit.stamp_case(case, actor)
    db.commit()
    db.refresh(case)
    from .realtime import notify_data_changed
    notify_data_changed(case.bank, case.product)
    case.propensity = propensity(case)
    _mark_today(db, [case])
    return case


@router.post("/{case_id}/mark-unpaid", response_model=schemas.CaseOut)
def mark_unpaid(case_id: int, db: Session = Depends(get_db),
                actor: models.User = Depends(require_roles(*PAY_EDIT_ROLES))):
    """Revert a case to UNPAID (e.g. an online payment failed / bounced, per the DPR).
    Undoes the logged collection, returns the case to the working pool, and the reversal
    flows through the assigned caller/FOS performance and MIS via the case fields."""
    case = _scope(db.query(models.Case), actor).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    prev = Decimal(case.received_amount or 0)
    case.received_amount = Decimal(0)
    case.pending_amount = _pay_base_total(case)
    case.paid_status = "UNPAID"
    case.status = "allocated"
    case.norm_stab = None
    case.follow_up_date = None
    if prev > 0:                                    # negative entry nets the caller's collected back down
        credit_id = case.assigned_caller_id or case.assigned_fos_id or actor.id
        db.add(models.CallLog(case_id=case.id, caller_id=credit_id, disposition="PAID", ptp_amount=(-prev),
                              note=f"Reversal: payment of ₹{prev} reverted (marked unpaid)"))
    case.last_contacted_at = datetime.now(timezone.utc)
    audit.record(db, actor, "unpaid", case, old="PAID", new="UNPAID",
                 detail=f"Marked UNPAID (reversed ₹{prev})" if prev > 0 else "Marked UNPAID")
    audit.stamp_case(case, actor)
    db.commit()
    db.refresh(case)
    from .realtime import notify_data_changed
    notify_data_changed(case.bank, case.product)
    case.propensity = propensity(case)
    _mark_today(db, [case])
    return case


_UNDO_NUMERIC = {"received_amount", "pending_amount", "funding_amount", "enr", "norm_amount",
                 "stab_amount", "total_outstanding", "principal_outstanding", "min_amount_due",
                 "rollback_amount"}


@router.post("/{case_id}/undo", response_model=schemas.CaseOut)
def undo_last(case_id: int, db: Session = Depends(get_db),
              actor: models.User = Depends(require_roles(*PAY_EDIT_ROLES))):
    """Undo the single most recent change on a case — reverse the last payment, or restore the
    last edited field to its previous value. Repeatable: each call steps one change further back."""
    case = _scope(db.query(models.Case), actor).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    _ensure_open(case, actor)

    # Which audit entries have already been undone (so we don't undo the same thing twice).
    undone_ids = set()
    for u in db.query(models.AuditLog).filter(models.AuditLog.case_id == case_id,
                                              models.AuditLog.action == "undo").all():
        t = (u.meta or {}).get("undo_of")
        if t:
            undone_ids.add(t)

    entries = (db.query(models.AuditLog)
               .filter(models.AuditLog.case_id == case_id,
                       models.AuditLog.action.in_(["payment", "paid", "cell_edit", "edit"]))
               .order_by(models.AuditLog.at.desc(), models.AuditLog.id.desc()).all())
    target = next((e for e in entries if e.id not in undone_ids), None)
    if not target:
        raise HTTPException(status_code=400, detail="Nothing to undo on this case")

    if target.action in ("payment", "paid"):
        # Reverse the most recent payment that hasn't already been reversed.
        logs = [l for l in db.query(models.CallLog).filter(models.CallLog.case_id == case_id)
                .order_by(models.CallLog.created_at.asc()).all() if l.ptp_amount is not None]
        pos = [l for l in logs if Decimal(str(l.ptp_amount)) > 0]
        neg = sum(1 for l in logs if Decimal(str(l.ptp_amount)) < 0)
        undoable = pos[:len(pos) - neg] if neg < len(pos) else []
        if not undoable:
            raise HTTPException(status_code=400, detail="No payment left to undo")
        amt = Decimal(str(undoable[-1].ptp_amount))
        new_recv = Decimal(case.received_amount or 0) - amt
        case.received_amount = new_recv if new_recv > 0 else Decimal(0)
        pend = _pay_base_total(case) - Decimal(case.received_amount or 0)
        case.pending_amount = pend if pend > 0 else Decimal(0)
        if Decimal(case.received_amount or 0) <= 0:
            case.paid_status, case.status, case.norm_stab = "UNPAID", "allocated", None
        elif case.pending_amount > 0:
            case.paid_status, case.status = "PARTIAL", "allocated"
        credit_id = case.assigned_caller_id or case.assigned_fos_id or actor.id
        db.add(models.CallLog(case_id=case.id, caller_id=credit_id, disposition="PAYMENT",
                              ptp_amount=(-amt), note=f"Undo: reversed payment ₹{amt}"))
        desc = f"Reversed last payment ₹{amt}"
    else:
        field = target.field
        if not field:
            raise HTTPException(status_code=400, detail="Nothing to undo on this case")
        old = target.old_value
        if field in _UNDO_NUMERIC:
            try:
                val = Decimal(str(old)) if old not in (None, "") else Decimal(0)
            except Exception:
                val = Decimal(0)
        else:
            val = old if old not in ("",) else None
        setattr(case, field, val)
        desc = f"Restored {field} to '{old if old not in (None, '') else '—'}'"

    audit.record(db, actor, "undo", case, detail=desc, meta={"undo_of": target.id})
    audit.stamp_case(case, actor)
    db.commit()
    db.refresh(case)
    from .realtime import notify_data_changed
    notify_data_changed(case.bank, case.product)
    case.propensity = propensity(case)
    _mark_today(db, [case])
    return case


class ContactUpdateIn(BaseModel):
    new_address: str | None = None
    new_phone: str | None = None


# Who may record a customer's latest address/phone (found mid-cycle). Callers + head office
# primarily; admin/manager/backend/teamlead allowed too.
CONTACT_EDIT_ROLES = ("admin", "headoffice", "manager", "backend", "telecaller", "teamlead")


@router.post("/{case_id}/contact-update", response_model=schemas.CaseOut)
def contact_update(case_id: int, body: ContactUpdateIn, db: Session = Depends(get_db),
                   actor: models.User = Depends(require_roles(*CONTACT_EDIT_ROLES))):
    """A caller / head-office records the customer's latest address / phone discovered
    mid-cycle. It's stored on the case, shown to the assigned field officer, and the FOS is
    notified instantly (live push + a persisted bell notification)."""
    case = _scope(db.query(models.Case), actor).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    na = (body.new_address or "").strip() or None
    nph = (body.new_phone or "").strip() or None
    if na is None and nph is None:
        raise HTTPException(status_code=400, detail="Provide a new address and/or new phone")
    changed = []
    if na is not None and na != (case.new_address or None):
        audit.record(db, actor, "edit", case, field="new_address",
                     old=case.new_address, new=na, detail="Updated customer new address")
        case.new_address = na
        changed.append("address")
    if nph is not None and nph != (case.new_phone or None):
        audit.record(db, actor, "edit", case, field="new_phone",
                     old=case.new_phone, new=nph, detail="Updated customer new phone")
        case.new_phone = nph
        changed.append("phone")
    if not changed:
        return case                                  # nothing actually different
    case.new_contact_by = actor.name
    case.new_contact_at = datetime.now(timezone.utc)

    # Alert the assigned field officer (persisted bell + live push).
    if case.assigned_fos_id:
        parts = []
        if "phone" in changed and case.new_phone:
            parts.append(f"📞 {case.new_phone}")
        if "address" in changed and case.new_address:
            parts.append(f"📍 {case.new_address}")
        who = case.customer_name or case.account_no or f"case #{case.id}"
        from .notifications import push
        push(db, case.assigned_fos_id,
             title=f"Updated contact — {who}",
             body="  ·  ".join(parts) + f"   (by {actor.name})",
             case_id=case.id, ntype="contact_update", by_name=actor.name)

    db.commit()
    db.refresh(case)
    from .realtime import notify_data_changed
    notify_data_changed(case.bank, case.product)
    case.propensity = propensity(case)
    _mark_today(db, [case])
    return case


class IdsIn(BaseModel):
    ids: list[int] = []
    reason: str | None = None


@router.post("/remove")
def remove_cases(body: IdsIn, db: Session = Depends(get_db),
                 actor: models.User = Depends(require_roles("headoffice", "admin"))):
    """Soft-delete the selected cases (head office / admin). They move to the Removed bin and
    drop out of every list, MIS, dashboard and performance calc until restored."""
    if not body.ids:
        raise HTTPException(status_code=400, detail="No cases selected")
    rows = db.query(models.Case).filter(models.Case.id.in_(body.ids)).all()
    now = datetime.now(timezone.utc)
    banks = set()
    for c in rows:
        c.removed = True
        c.removed_at = now
        c.removed_by = actor.id
        if body.reason:
            c.allocation_reason = f"Removed: {body.reason}"
        audit.record(db, actor, "delete", c, detail="Removed" + (f": {body.reason}" if body.reason else ""))
        audit.stamp_case(c, actor)
        banks.add((c.bank, c.product))
    db.commit()
    from .realtime import notify_data_changed
    for bank, product in banks:
        notify_data_changed(bank, product)
    return {"removed": len(rows)}


@router.post("/restore")
def restore_cases(body: IdsIn, db: Session = Depends(get_db),
                  actor: models.User = Depends(require_roles("headoffice", "admin"))):
    """Restore soft-deleted cases back into active work."""
    if not body.ids:
        raise HTTPException(status_code=400, detail="No cases selected")
    rows = db.query(models.Case).filter(models.Case.id.in_(body.ids),
                                        models.Case.removed.is_(True)).all()
    banks = set()
    for c in rows:
        c.removed = False
        c.removed_at = None
        c.removed_by = None
        audit.record(db, actor, "restore", c, detail="Restored from Removed bin")
        audit.stamp_case(c, actor)
        banks.add((c.bank, c.product))
    db.commit()
    from .realtime import notify_data_changed
    for bank, product in banks:
        notify_data_changed(bank, product)
    return {"restored": len(rows)}


@router.post("/removed/purge")
def purge_removed(body: IdsIn, db: Session = Depends(get_db),
                  actor: models.User = Depends(require_roles("headoffice", "admin"))):
    """Permanently delete cases from the Removed bin (irreversible). If ids is empty,
    purges the entire bin."""
    q = db.query(models.Case).filter(models.Case.removed.is_(True))
    if body.ids:
        q = q.filter(models.Case.id.in_(body.ids))
    ids = [c.id for c in q.all()]
    if not ids:
        return {"purged": 0}
    db.query(models.LocationPing).filter(models.LocationPing.active_case_id.in_(ids)).update(
        {models.LocationPing.active_case_id: None}, synchronize_session=False)
    db.query(models.LegalCase).filter(models.LegalCase.case_id.in_(ids)).update(
        {models.LegalCase.case_id: None}, synchronize_session=False)
    db.query(models.Visit).filter(models.Visit.case_id.in_(ids)).delete(synchronize_session=False)
    db.query(models.CallLog).filter(models.CallLog.case_id.in_(ids)).delete(synchronize_session=False)
    n = db.query(models.Case).filter(models.Case.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    return {"purged": n}


@router.get("/{case_id}/timeline")
def timeline(case_id: int, db: Session = Depends(get_db),
             user: models.User = Depends(get_current_user)):
    """Full audit trail for a case: creation, field visits (photo/GPS/paid/location-correct/
    moved), calls, and payments — one merged, time-ordered list."""
    case = _scope(db.query(models.Case), user).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    users = {u.id: u.name for u in db.query(models.User).all()}
    ev = []

    ev.append({"type": "created", "at": case.created_at, "by": None, "title": "Case created",
               "detail": " · ".join([x for x in [case.bank, case.bucket, f"target ₹{float(case.funding_amount or 0):.0f}"] if x])})
    if case.assigned_fos_id or case.assigned_caller_id:
        who = " / ".join([x for x in [users.get(case.assigned_fos_id), users.get(case.assigned_caller_id)] if x])
        ev.append({"type": "allocated", "at": case.created_at, "by": None, "title": "Allocated",
                   "detail": f"{who}" + (f" ({case.allocation_reason})" if case.allocation_reason else "")})

    for v in db.query(models.Visit).filter(models.Visit.case_id == case_id).all():
        bits = [v.disposition or "visit"]
        if v.paid:
            bits.append(f"paid ₹{float(v.amount_collected or 0):.0f}")
        if v.location_correct is not None:
            bits.append("location OK" if v.location_correct else "wrong location")
        if v.person_moved:
            bits.append("person moved")
        ev.append({"type": "visit", "at": v.created_at, "by": users.get(v.officer_id), "title": "Field visit",
                   "detail": " · ".join(bits), "lat": v.latitude, "lng": v.longitude,
                   "photo": resolve_photo(v.photo_path), "note": v.note, "amount": float(v.amount_collected or 0)})

    for cl in db.query(models.CallLog).filter(models.CallLog.case_id == case_id).all():
        is_pay = cl.disposition == "PAYMENT"
        ev.append({"type": "payment" if is_pay else "call", "at": cl.created_at, "by": users.get(cl.caller_id),
                   "title": "Payment" if is_pay else f"Call — {cl.disposition or ''}",
                   "detail": cl.note or cl.disposition or "", "amount": float(cl.ptp_amount or 0),
                   "ptp_date": cl.ptp_date.isoformat() if cl.ptp_date else None})

    from datetime import datetime, timezone
    ev.sort(key=lambda e: e["at"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return ev
