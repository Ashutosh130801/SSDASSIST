from decimal import Decimal
from datetime import datetime, time, timedelta, timezone

import io

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user, require_roles
from ..allocation import run_allocation
from ..config import get_settings
from ..storage import resolve as resolve_photo
from .. import audit

router = APIRouter(prefix="/api/cases", tags=["cases"])


def _needs_geocode(q, include_failed: bool = False, period: str | None = None):
    """Cases that still need a map pin. By default this is only NEW / never-attempted addresses —
    a case we already tried (whether it resolved or not) is left alone, so clicking 'Geocode' again
    processes just the remaining/new ones instead of re-running everything from scratch. Pass
    include_failed=True to also re-attempt addresses that were tried but couldn't be located, and
    period='YYYY-MM' to restrict to a single upload month (e.g. this month only)."""
    # A case still needs work if ANY of its present address lines lacks its own pin.
    q = q.filter(
        or_(
            and_(models.Case.latitude.is_(None),
                 or_(models.Case.address.isnot(None), models.Case.pincode.isnot(None))),
            and_(models.Case.latitude2.is_(None),
                 or_(models.Case.address2.isnot(None), models.Case.pincode2.isnot(None))),
            and_(models.Case.latitude3.is_(None),
                 or_(models.Case.address3.isnot(None), models.Case.pincode3.isnot(None))),
        )
    )
    if not include_failed:
        q = q.filter(models.Case.geo_attempted_at.is_(None))
    if period:
        q = q.filter(models.Case.period == period)
    return q


def apply_geocode(case: models.Case, res: dict) -> bool:
    """Store a geocode result on a case. Always records the cleaned address + the geocoder's
    guess (geo_lat/geo_lng/geo_precision) and a DIGIPIN; promotes it to the EFFECTIVE
    latitude/longitude only when the case isn't already field-verified (FOS doorstep GPS wins).
    Returns True if we got usable coordinates."""
    from .. import digipin as _dp
    if res.get("clean"):
        case.address_clean = res["clean"]
    if res.get("pincode") and not case.pincode:
        case.pincode = res["pincode"]
    lat, lng = res.get("lat"), res.get("lng")
    if lat is None or lng is None:
        return False
    case.geo_lat, case.geo_lng = lat, lng
    case.geo_precision = res.get("precision") or "locality"
    # Don't clobber a field-captured location; otherwise this geocode is the effective pin.
    if case.location_source != "field":
        case.latitude, case.longitude = lat, lng
        case.location_source = "geocoded"
        case.location_updated_at = datetime.now(_IST_TZ)
        case.digipin = _dp.encode(lat, lng)
    return True


def apply_geocode_slot(case: models.Case, res: dict, slot: int) -> bool:
    """Store a geocode result for the 2nd (slot=2) or 3rd (slot=3) address line into its own
    latitude{N}/longitude{N}/geo_precision{N} columns, and backfill pincode{N} if missing.
    Returns True when usable coordinates were stored."""
    if res.get("pincode") and not getattr(case, f"pincode{slot}", None):
        setattr(case, f"pincode{slot}", res["pincode"])
    lat, lng = res.get("lat"), res.get("lng")
    if lat is None or lng is None:
        return False
    setattr(case, f"latitude{slot}", lat)
    setattr(case, f"longitude{slot}", lng)
    setattr(case, f"geo_precision{slot}", res.get("precision") or "locality")
    return True


@router.post("/geocode")
def geocode(limit: int = 40, retry_failed: bool = False, month_bucket: str | None = None,
            db: Session = Depends(get_db),
            admin: models.User = Depends(require_roles("admin"))):
    """Fill latitude/longitude for cases that only have an address/pincode, so they pin on the
    field map. Processes up to `limit` per call — call again while `remaining` > 0 (the web
    button loops this). Pass month_bucket='current' to geocode only this month's cases. Uses
    LocationIQ (LOCATIONIQ_KEY) with a cleaned address and a pincode-centroid fallback; paces
    ~1 req/sec to respect the free-tier rate limit."""
    from .. import geocode as _geo
    from ..database import SessionLocal
    if not _geo.has_key():
        raise HTTPException(status_code=400,
                            detail="Geocoding is not configured — set LOCATIONIQ_KEY in the server .env and restart.")
    import time
    # 'current' → this month only; anything else → all months (default behaviour).
    period = _current_period() if month_bucket == "current" else None
    # 1) READ (quick): pull the batch into plain dicts, then RELEASE the DB connection. The geocoding
    # loop below does slow network I/O (LLM + ~1 req/sec HTTP), which must NOT hold a pooled DB
    # connection — doing so is what exhausted the pool ("QueuePool overflow reached").
    rows = _needs_geocode(db.query(
        models.Case.id, models.Case.address, models.Case.address2, models.Case.address3,
        models.Case.pincode, models.Case.pincode2, models.Case.pincode3,
        models.Case.latitude, models.Case.latitude2, models.Case.latitude3)
        .filter(models.Case.removed.isnot(True)),
        include_failed=retry_failed, period=period).limit(limit).all()
    batch = [{"id": r[0], "address": r[1], "address2": r[2], "address3": r[3],
              "pincode": r[4], "pincode2": r[5], "pincode3": r[6],
              "lat": r[7], "lat2": r[8], "lat3": r[9]} for r in rows]
    db.close()                                  # hand the connection back to the pool during network work

    # Which address slots on a case still need a pin: slot 1 (address/pincode), slot 2 (address2/
    # pincode2) and slot 3 (address3/pincode3) are each geocoded independently into their own columns.
    def _slots_for(c):
        out = []
        if c["lat"] is None and (c["address"] or c["pincode"]):
            out.append((1, c["address"], c["pincode"]))
        if c["lat2"] is None and (c["address2"] or c["pincode2"]):
            out.append((2, c["address2"], c["pincode2"]))
        if c["lat3"] is None and (c["address3"] or c["pincode3"]):
            out.append((3, c["address3"], c["pincode3"]))
        return out

    # 2) NETWORK (slow, no DB held): AI clean pass + per-slot geocode.
    # Clean every distinct address line across all slots in one LLM batch (keyed "<caseid>-<slot>").
    clean_map = {}
    if _geo.llm_available():
        items = []
        for c in batch:
            for slot, addr, pin in _slots_for(c):
                items.append({"id": f"{c['id']}-{slot}",
                              "raw": ", ".join(str(p) for p in (addr, pin) if p)})
        if items:
            clean_map = _geo.llm_clean_batch(items)
    ai_cleaned = sum(1 for v in clean_map.values() if v)
    results = []                                 # [(case_id, slot, res_dict)]
    _total_slots = 0
    with httpx.Client(timeout=15) as client:
        first = True
        for c in batch:
            for slot, addr, pin in _slots_for(c):
                _total_slots += 1
                if not first:
                    time.sleep(0.5)              # pace between queries (LocationIQ free tier ~2 req/s)
                first = False
                res = _geo.geocode_one(client, addr, None, pin,
                                       pre_clean=clean_map.get(f"{c['id']}-{slot}"))
                results.append((c["id"], slot, res))
    local_cleaned = max(_total_slots - ai_cleaned, 0)

    # 3) WRITE (quick): re-open a short-lived session, apply results, commit.
    _now = datetime.now(_IST_TZ)
    geocoded = failed = 0
    with SessionLocal() as w:
        by_id = {cs.id: cs for cs in w.query(models.Case).filter(
            models.Case.id.in_([cid for cid, _, _ in results] or [-1])).all()}
        for cid, slot, res in results:
            cs = by_id.get(cid)
            if cs is None:
                continue
            cs.geo_attempted_at = _now           # mark as tried (success OR fail) so a repeat run skips it
            ok = apply_geocode(cs, res) if slot == 1 else apply_geocode_slot(cs, res, slot)
            if ok:
                geocoded += 1
            else:
                failed += 1
        w.commit()
        remaining = _needs_geocode(w.query(models.Case), period=period).count()
        _ft = (w.query(models.Case)
               .filter(models.Case.removed.isnot(True), models.Case.latitude.is_(None),
                       models.Case.geo_attempted_at.isnot(None),
                       or_(models.Case.address.isnot(None), models.Case.pincode.isnot(None))))
        if period:
            _ft = _ft.filter(models.Case.period == period)
        failed_total = _ft.count()
    return {"geocoded": geocoded, "failed": failed, "remaining": remaining,
            "failed_total": failed_total, "processed": len(batch),
            "ai_cleaned": ai_cleaned, "local_cleaned": local_cleaned}


@router.post("/geocode/rebuild")
def geocode_rebuild(month_bucket: str | None = None, db: Session = Depends(get_db),
                    admin: models.User = Depends(require_roles("admin"))):
    """RE-ARM cases for a fresh geocode (e.g. to re-run them through the AI cleaner). Clears the
    'attempted' marker and the geocoded pin for every matching case so the next Geocode run processes
    them all again — INCLUDING ones already pinned. FOS field-captured pins (location_source='field')
    are preserved. Pass month_bucket='current' to re-arm only this month; omit for all months.
    After this, call POST /geocode (with month_bucket=current to match) to actually re-geocode."""
    period = _current_period() if month_bucket == "current" else None
    q = db.query(models.Case).filter(models.Case.removed.isnot(True))
    if period:
        q = q.filter(models.Case.period == period)
    # Only re-arm cases that actually have an address/pin to work with.
    q = q.filter(or_(models.Case.address.isnot(None), models.Case.pincode.isnot(None),
                     models.Case.address2.isnot(None), models.Case.address3.isnot(None)))
    n = 0
    for cs in q.all():
        cs.geo_attempted_at = None
        if cs.location_source != "field":          # never wipe a FOS doorstep GPS pin
            cs.latitude = cs.longitude = cs.geo_precision = None
            cs.geo_lat = cs.geo_lng = None
            cs.location_source = None
        cs.latitude2 = cs.longitude2 = cs.geo_precision2 = None
        cs.latitude3 = cs.longitude3 = cs.geo_precision3 = None
        n += 1
    db.commit()
    return {"rearmed": n, "scope": "current_month" if period else "all"}


@router.get("/geocode/status")
def geocode_status(db: Session = Depends(get_db),
                   admin: models.User = Depends(require_roles("admin"))):
    """Counts for the admin geocode progress UI: how many cases still need a pin, and how many
    total have addresses to work with."""
    from .. import geocode as _geo
    total = db.query(models.Case).filter(models.Case.removed.isnot(True)).count()
    with_pin = db.query(models.Case).filter(models.Case.removed.isnot(True),
                                            models.Case.latitude.isnot(None)).count()
    remaining = _needs_geocode(db.query(models.Case).filter(models.Case.removed.isnot(True))).count()
    # Tried before but still unpinned — surfaced separately so admin can choose to retry them.
    failed_total = (db.query(models.Case)
                    .filter(models.Case.removed.isnot(True), models.Case.latitude.is_(None),
                            models.Case.geo_attempted_at.isnot(None),
                            or_(models.Case.address.isnot(None), models.Case.pincode.isnot(None)))
                    .count())
    # Same counts restricted to THIS month's cases, so the admin can geocode/track just this month.
    cp = _current_period()
    _mbase = db.query(models.Case).filter(models.Case.removed.isnot(True), models.Case.period == cp)
    month_total = _mbase.count()
    month_with_pin = _mbase.filter(models.Case.latitude.isnot(None)).count()
    month_remaining = _needs_geocode(
        db.query(models.Case).filter(models.Case.removed.isnot(True)), period=cp).count()
    month_failed_total = (db.query(models.Case)
                          .filter(models.Case.removed.isnot(True), models.Case.period == cp,
                                  models.Case.latitude.is_(None), models.Case.geo_attempted_at.isnot(None),
                                  or_(models.Case.address.isnot(None), models.Case.pincode.isnot(None)))
                          .count())
    return {"total": total, "with_pin": with_pin, "remaining": remaining,
            "failed_total": failed_total, "configured": _geo.has_key(),
            "month": cp, "month_total": month_total, "month_with_pin": month_with_pin,
            "month_remaining": month_remaining, "month_failed_total": month_failed_total}


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
    # Dual-role lead (a caller/FOS granted the team-lead hat): their team-lead identity on a sheet
    # is their SECOND id, tl_emp_code (e.g. TL045), not their primary emp_code (TC.../FO...). Match
    # it too, so cases stamped with their TL code are recognised without a manual re-allocate.
    if getattr(user, "tl_emp_code", None):
        conds.append(func.lower(func.trim(models.Case.team_lead)) == user.tl_emp_code.strip().lower())
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


def _last_period() -> str:
    """Previous month as 'YYYY-MM' (IST). Its cases are closed/archived; the 'Last month'
    filter lets staff VIEW them read-only (closed cases stay locked for FOS/callers)."""
    d = datetime.now(_IST_TZ)
    return f"{d.year - 1:04d}-12" if d.month == 1 else f"{d.year:04d}-{d.month - 1:02d}"


def _bucket_for_period(period) -> str | None:
    """If a resolved period equals last month, report bucket='last' so _scope will unlock it
    for non-admin viewers. (Reads only — nothing here changes case data.)"""
    return "last" if period and period == _last_period() else None


def branch_canon_map(db) -> dict:
    """Map UPPERCASE(branch) -> the one canonical spelling to use, so 'KADAPA' and 'kadapa'
    collapse to a single branch. Preference when variants exist: an all-uppercase spelling
    (per the house rule 'if uppercase is there, use uppercase'); otherwise the alphabetically
    first existing spelling. Built from both Case.branch and User.branch."""
    names = set()
    for (b,) in db.query(models.Case.branch).distinct().all():
        if b and str(b).strip():
            names.add(str(b).strip())
    for (b,) in db.query(models.User.branch).distinct().all():
        if b and str(b).strip():
            names.add(str(b).strip())
    groups: dict = {}
    for n in names:
        groups.setdefault(n.upper(), []).append(n)
    out = {}
    for up, variants in groups.items():
        out[up] = next((v for v in variants if v.isupper()), None) or sorted(variants)[0]
    return out


def canonical_branch(db, name):
    """Return the canonical spelling for a branch name (case-insensitive). If the branch already
    exists in any case-variant, reuse that spelling so a new upload joins the SAME portfolio
    instead of splitting into a case-duplicate. A genuinely new branch is returned trimmed as-is."""
    if not name or not str(name).strip():
        return name
    n = str(name).strip()
    return branch_canon_map(db).get(n.upper(), n)


def _case_closed(case: models.Case) -> bool:
    if not case.close_date:
        return False
    return case.close_date < datetime.now(_IST_TZ).date()


def _ensure_open(case: models.Case, user: models.User):
    """Block field/calling operations on a case that has already closed for the month, or that
    has been escalated away from the FOS/caller (it stays visible in their list but locked).
    Applies to FOS & telecallers; admin / manager / head office keep the ability to make
    corrections and post DPR payments."""
    if user.role in ("fos", "telecaller"):
        if case.escalated:
            raise HTTPException(status_code=403,
                                detail="This case has been escalated and is locked for you. Your team lead / manager is handling it.")
        if _case_closed(case):
            raise HTTPException(status_code=403,
                                detail="This case has closed for the month and is locked. Ask an admin if a change is needed.")


def _scope(q, user: models.User, include_removed: bool = False, bucket: str | None = None,
           all_periods: bool = False):
    """Restrict rows by role — FO sees own field cases, telecaller sees own queue,
    branch manager sees cases handled by staff in their branch, team lead sees cases
    handled by the FOS/callers who report to them. Removed (soft-deleted) cases are
    hidden everywhere unless explicitly requested.

    `bucket='last'` opens up the previous month for VIEWING only: normally past months are
    hidden for non-admin, but when the user explicitly picks 'Last month' we show that month's
    cases even though they're closed/locked/archived. Writes stay blocked — closed cases are
    already locked for FOS/callers via _ensure_open.

    `all_periods=True` drops the month gate entirely (still keeping per-user ownership scope).
    Used by the DPR bulk update: bank payment reports for a just-closed month often arrive in the
    first week of the next month, so DPR must be able to match a CLOSED portfolio's cases."""
    if not include_removed:
        q = q.filter(models.Case.removed.isnot(True))
    # Monthly lifecycle: field/calling staff work the CURRENT month plus any NEXT-month
    # data uploaded early (so it can be allocated & started ahead of time). This month's
    # cases stay visible even after they close (cycle date / month-end) but closed ones are
    # locked. Past months become admin-only history. Cases with no period (legacy) stay on.
    if user.role not in ("admin", "techsupport") and not all_periods:
        if bucket == "last":
            # Explicit "Last month" view — restrict to (and reveal) the previous month only.
            q = q.filter(models.Case.period == _last_period())
        else:
            q = q.filter(or_(models.Case.period.is_(None),
                             models.Case.period.in_([_current_period(), _next_period()])))
    if user.role == "fos":
        # Own live cases + cases escalated away from them (kept visible but locked).
        return q.filter(or_(models.Case.assigned_fos_id == user.id,
                            and_(models.Case.escalated.is_(True),
                                 models.Case.esc_prev_fos_id == user.id)))
    if user.role == "telecaller":
        return q.filter(or_(models.Case.assigned_caller_id == user.id,
                            and_(models.Case.escalated.is_(True),
                                 models.Case.esc_prev_caller_id == user.id)))
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


def _mark_review_flags(db, user, cases):
    """Attach the signed-in user's personal review-highlight colour to each case (batch)."""
    ids = [c.id for c in cases if getattr(c, "id", None)]
    if not ids or not user:
        return cases
    flags = {f.case_id: f for f in db.query(models.CaseReviewFlag).filter(
        models.CaseReviewFlag.user_id == user.id, models.CaseReviewFlag.case_id.in_(ids)).all()}
    for c in cases:
        f = flags.get(c.id)
        c.review_color = f.color if f else None
        c.review_note = f.note if f else None
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
    vehicle_type: str | None = None,    # AUTO LOANS filter — vehicle type
    brand: str | None = None,           # AUTO LOANS filter — vehicle brand/make
    old_new: str | None = None,         # AUTO LOANS filter — Old / New
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
    review_color: str | None = None,    # only cases the user flagged with this colour
    flagged_review: bool | None = None, # only cases the user has flagged (any colour)
    limit: int = Query(500, le=5000),
    offset: int = 0,
):
    q = _scope(db.query(models.Case), user, bucket=month_bucket)
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
        _real_fos = [i for i in _fos_list if i > 0]
        _conds = []
        if _real_fos:
            _conds.append(models.Case.assigned_fos_id.in_(_real_fos))
        if 0 in _fos_list:                              # "No FOS (caller-only)" sentinel
            _conds.append(models.Case.assigned_fos_id.is_(None))
        if _conds:
            q = q.filter(or_(*_conds))
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
    elif month_bucket == "last":
        q = q.filter(models.Case.period == _last_period())
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
        # case-insensitive so "VISAKHAPATNAM" and "Visakhapatnam" are one location
        q = q.filter(func.lower(func.trim(models.Case.branch)) == branch.strip().lower())
    if area:
        q = q.filter(models.Case.team == area)
    if vehicle_type:
        q = q.filter(func.lower(func.trim(func.coalesce(models.Case.vehicle_type, ""))) == vehicle_type.strip().lower())
    if brand:
        q = q.filter(func.lower(func.trim(func.coalesce(models.Case.brand, ""))) == brand.strip().lower())
    if old_new:
        q = q.filter(func.lower(func.trim(func.coalesce(models.Case.old_new, ""))) == old_new.strip().lower())
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
            models.Case.vehicle_num.ilike(like),   # AUTO LOANS — search by vehicle registration number
        ))
    # Personal review-highlight filters (the user's own colour flags).
    if review_color or flagged_review:
        fq = db.query(models.CaseReviewFlag.case_id).filter(models.CaseReviewFlag.user_id == user.id)
        if review_color:
            fq = fq.filter(models.CaseReviewFlag.color == review_color)
        q = q.filter(models.Case.id.in_(fq))
    rows = _mark_review_flags(db, user, _mark_today(db, _with_score(q.order_by(models.Case.updated_at.desc()).offset(offset).limit(limit).all())))
    if with_notes:
        from ..notes import case_notes_map, join_notes
        nmap = case_notes_map(db, [c.id for c in rows], limit=5)
        for c in rows:
            ns = nmap.get(c.id, [])
            c.notes = ns
            c.notes_text = join_notes(ns)
    attach_joint_display(rows, db, user)
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
    # Remember the original owners so the case stays visible (locked) in their list and can be
    # restored later; nulling the LIVE assignment is what removes it from their queue/perf/MIS.
    if case.assigned_fos_id:
        case.esc_prev_fos_id = case.assigned_fos_id
    if case.assigned_caller_id:
        case.esc_prev_caller_id = case.assigned_caller_id
    case.assigned_fos_id = None            # drop from the FOS queue / performance
    case.assigned_caller_id = None         # drop from the caller queue / performance
    if body.note:
        case.allocation_reason = f"Escalated: {body.note}"
    audit.record(db, actor, "escalate", case, new=owner.name,
                 detail=f"Escalated to {owner.name}" + (f": {body.note}" if body.note else ""),
                 target_user_id=owner_id)
    audit.stamp_case(case, actor)
    from .notifications import notify_case_change
    notify_case_change(db, case, actor,
                       f"Case escalated to {owner.name}" + (f" — {body.note}" if body.note else "") + " (locked for the field/calling staff)",
                       ntype="escalate")
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
    # Hand the case back to its original owners (if it still has none live).
    if case.assigned_fos_id is None and case.esc_prev_fos_id:
        case.assigned_fos_id = case.esc_prev_fos_id
    if case.assigned_caller_id is None and case.esc_prev_caller_id:
        case.assigned_caller_id = case.esc_prev_caller_id
    case.esc_prev_fos_id = None
    case.esc_prev_caller_id = None
    audit.record(db, actor, "deescalate", case, detail="Released escalation back to original owner")
    audit.stamp_case(case, actor)
    from .notifications import notify_case_change
    notify_case_change(db, case, actor, "Escalation released — case returned to its owner", ntype="deescalate")
    db.commit()
    from .realtime import notify_data_changed
    notify_data_changed(case.bank, case.product)
    return {"ok": True}


class ReviewFlagIn(BaseModel):
    color: str | None = None            # '' / null clears the flag
    note: str | None = None


REVIEW_COLORS = {"red", "amber", "green", "blue", "purple", "pink", "grey"}


@router.post("/{case_id}/review-flag", response_model=schemas.CaseOut)
def set_review_flag(case_id: int, body: ReviewFlagIn = ReviewFlagIn(), db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)):
    """Set / change / clear the signed-in user's personal colour highlight on a case
    (to review later). Personal to each user — never shown to others."""
    case = _scope(db.query(models.Case), user).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    color = (body.color or "").strip().lower() or None
    if color and color not in REVIEW_COLORS:
        raise HTTPException(status_code=400, detail="Invalid colour")
    flag = db.query(models.CaseReviewFlag).filter(
        models.CaseReviewFlag.user_id == user.id, models.CaseReviewFlag.case_id == case_id).first()
    if color is None:
        if flag:
            db.delete(flag)
    elif flag:
        flag.color = color
        flag.note = (body.note or "").strip() or None
    else:
        db.add(models.CaseReviewFlag(user_id=user.id, case_id=case_id, color=color,
                                     note=(body.note or "").strip() or None))
    db.commit()
    db.refresh(case)
    _mark_review_flags(db, user, [case])
    case.propensity = propensity(case)
    return case


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
        q = q.filter(func.lower(func.trim(models.Case.branch)) == branch.strip().lower())
    return sorted({(t or "").strip() for (t,) in q.all() if t and str(t).strip()})


def _period_bucket(month_bucket):
    """'current' → this month, 'next' → next month, 'last' → previous month, else None (all)."""
    if month_bucket == "current":
        return _current_period()
    if month_bucket == "next":
        return _next_period()
    if month_bucket == "last":
        return _last_period()
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
        models.Case.principal_outstanding, models.Case.received_amount, models.Case.paid_status,
    ), user, bucket=_bucket_for_period(period))
    if period:
        q = q.filter(models.Case.period == period)
    return q.all()


def _blank(d):
    return {"count": 0, "pending": 0.0, "received": 0.0, "count_current": 0, "count_next": 0,
            "paid": 0, "unpaid": 0, **d}


@router.get("/product-summary")
def product_summary(month_bucket: str | None = None, db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)):
    """Portfolio cards, grouped by BANK + PRODUCT (no accidental branch split). A product is only
    branch-split when at least one of its cases had a branch chosen EXPLICITLY at upload; those
    carry a `branches` breakdown so the UI can offer location sub-cards. FOS-inherited branches do
    NOT split a portfolio. `month_bucket` (current/next/all) scopes the whole section to one month."""
    cur, nxt = _current_period(), _next_period()
    agg: dict = {}
    for b, p, s, br, bexp, per, fund, tos, enr, pos, recv, pstat in _portfolio_rows(db, user, _period_bucket(month_bucket)):
        base = float(fund or 0) or float(tos or 0) or float(enr or 0) or float(pos or 0)   # funding → TOS → ENR → POS
        rc = float(recv or 0)
        pend = max(0.0, base - rc)
        is_paid = (pstat or "").upper() == "PAID"
        # Group by BANK + PRODUCT + SEGMENT so a product uploaded under two segments (e.g. a BL file
        # left on the default 'Credit Card') shows as its own card and its cases are never hidden by
        # the drill-down's segment filter. Normalise the segment so blanks collapse to one bucket.
        sg = (s or "").strip()
        # ...and by PERIOD (upload month), so each month is its own card — months stay separate and
        # the card can show which month it is, alongside the segment.
        pr = (per or "").strip()
        key = (b, p, sg, pr)
        d = agg.setdefault(key, _blank({"segment": sg, "period": pr, "branch_split": False, "branches": {}}))
        d["count"] += 1; d["received"] += rc; d["pending"] += pend
        d["paid" if is_paid else "unpaid"] += 1
        if per == cur: d["count_current"] += 1
        elif per == nxt: d["count_next"] += 1
        if bexp:
            d["branch_split"] = True
        # per-branch breakdown (only meaningful for split products; cheap to always keep).
        # Merge case-insensitively so "VISAKHAPATNAM" and "Visakhapatnam" are ONE location card;
        # key on the upper-case form, display Title Case.
        _braw = (br or "").strip()
        bkey = _braw.upper() or "— NO LOCATION —"
        bdisp = _braw.title() if _braw else "— No location —"
        bd = d["branches"].setdefault(bkey, _blank({"branch": bdisp}))
        bd["count"] += 1; bd["received"] += rc; bd["pending"] += pend
        bd["paid" if is_paid else "unpaid"] += 1
        if per == cur: bd["count_current"] += 1
        elif per == nxt: bd["count_next"] += 1
    out = []
    for (b, p, sg, pr), d in agg.items():
        branches = sorted(d.pop("branches").values(), key=lambda x: x["branch"]) if d["branch_split"] else []
        out.append({"bank": b or "—", "product": p or "—", "branch": "", **d, "branches": branches})
    # newest month first, then bank / product / segment
    out.sort(key=lambda x: (x.get("period") or "", x["bank"], x["product"], x.get("segment") or ""), reverse=True)
    out.sort(key=lambda x: (x["bank"], x["product"], x.get("segment") or ""))
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
    for b, p, s, br, bexp, per, fund, tos, enr, pos, recv, _pstat in _portfolio_rows(db, user, _period_bucket(month_bucket)):
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
        models.Case.cycle, models.Case.assigned_fos_id, models.Case.assigned_caller_id,
        models.Case.vehicle_type, models.Case.brand, models.Case.old_new, models.Case.team_lead), user)
    if bank:
        q = q.filter(models.Case.bank == bank)
    if product:
        q = q.filter(models.Case.product == product)
    if branch:
        q = q.filter(func.lower(func.trim(models.Case.branch)) == branch.strip().lower())
    cycles, fos_ids, caller_ids = set(), set(), set()
    veh_types, brands, oldnew = set(), set(), set()   # AUTO LOANS filter values
    tl_seen = {}                                      # team-lead values (dedupe case-insensitively)
    no_fos_present = False                             # any caller-only case (no FOS allocated)
    for cyc, fid, cid, vt, br, on, tl in q.all():
        if cyc is not None and str(cyc).strip():
            cycles.add(str(cyc).strip())
        if fid:
            fos_ids.add(fid)
        else:
            no_fos_present = True
        if cid:
            caller_ids.add(cid)
        if vt and str(vt).strip():
            veh_types.add(str(vt).strip())
        if br and str(br).strip():
            brands.add(str(br).strip())
        if on and str(on).strip():
            oldnew.add(str(on).strip())
        if tl and str(tl).strip() and str(tl).strip().lower() not in tl_seen:
            tl_seen[str(tl).strip().lower()] = str(tl).strip()
    umap = {u.id: u for u in db.query(models.User).filter(
        models.User.id.in_(fos_ids | caller_ids)).all()} if (fos_ids or caller_ids) else {}
    def _people(ids):
        out = [{"id": i, "name": umap[i].name if i in umap else f"#{i}",
                "code": (umap[i].emp_code if i in umap else None)} for i in ids]
        return sorted(out, key=lambda x: (x["name"] or "").lower())
    _fos_opts = _people(fos_ids)
    if no_fos_present:                                 # sentinel so the dropdown can pick caller-only cases
        _fos_opts.append({"id": 0, "name": "No FOS (caller-only)", "code": None})
    def _cyc_sort(c):
        try:
            return (0, int(c))
        except (TypeError, ValueError):
            return (1, c)
    return {"cycles": sorted(cycles, key=_cyc_sort),
            "fos": _fos_opts, "callers": _people(caller_ids),
            # AUTO LOANS filter options (only non-empty when the portfolio has vehicle data)
            "vehicle_types": sorted(veh_types, key=str.lower),
            "brands": sorted(brands, key=str.lower),
            "old_new": sorted(oldnew, key=str.lower),
            "team_leads": sorted(tl_seen.values(), key=str.lower)}


@router.post("/portfolio/set-segment")
def set_portfolio_segment(body: dict = Body(...), db: Session = Depends(get_db),
                          actor: models.User = Depends(require_roles("admin", "headoffice"))):
    """Re-tag the SEGMENT of a whole portfolio in place (e.g. a BL file uploaded on the default
    'Credit Card'), without deleting or re-uploading. Scope by bank + product + current segment
    (+ optional branch / period). Only the segment changes — allocation, payments, visits, calls
    and history are untouched."""
    new_seg = (body.get("new_segment") or "").strip()
    bank = (body.get("bank") or "").strip()
    product = (body.get("product") or "").strip()
    if not (new_seg and bank and product):
        raise HTTPException(status_code=400, detail="bank, product and new_segment are required")
    q = db.query(models.Case).filter(models.Case.removed.isnot(True),
                                     models.Case.bank == bank, models.Case.product == product)
    cur_seg = (body.get("segment") or "").strip()
    if cur_seg:
        q = q.filter(func.coalesce(models.Case.segment, "") == cur_seg)
    if (body.get("branch") or "").strip():
        q = q.filter(func.lower(func.trim(models.Case.branch)) == body["branch"].strip().lower())
    if (body.get("period") or "").strip():
        q = q.filter(models.Case.period == body["period"].strip())
    rows = q.all()
    for c in rows:
        c.segment = new_seg
    from .. import audit
    audit.record(db, actor, "set_segment", entity_type="portfolio",
                 detail=f"{bank}/{product}{(' · ' + cur_seg) if cur_seg else ''} → segment '{new_seg}' ({len(rows)} cases)")
    db.commit()
    return {"ok": True, "updated": len(rows), "new_segment": new_seg}


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
    # CaseCreate carries a few computed/display-only fields (e.g. visited_today,
    # contacted_today) that are NOT real columns — filter to actual columns so
    # models.Case(**...) never raises "invalid keyword argument".
    _cols = {c.name for c in models.Case.__table__.columns}
    case = models.Case(**{k: v for k, v in body.model_dump().items() if k in _cols})
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
    _ensure_open(case, user)   # escalated/closed cases are read-only for FOS & callers
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
    # Fields whose change is worth notifying associated users about (skips minor numeric tweaks).
    NOTIFY_FIELDS = {
        "status": "Status", "paid_status": "Paid status", "disposition": "Disposition",
        "remarks": "Remarks", "final_status": "Final status", "follow_up_date": "Follow-up / PTP date",
        "new_phone": "New phone", "new_address": "New address",
        "assigned_fos_id": "Assigned FOS", "assigned_caller_id": "Assigned caller",
    }
    change_msgs = []
    _old_recv = Decimal(str(case.received_amount or 0))   # snapshot for the dated payment event
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
            change_msgs.append(f"{NOTIFY_FIELDS[k]} → {who or 'unassigned'}")
        else:
            audit.record(db, user, "edit", case, field=k, old=old, new=v)
            if k in NOTIFY_FIELDS:
                change_msgs.append(f"{NOTIFY_FIELDS[k]}: {old or '—'} → {v or '—'}")
    audit.stamp_case(case, user)
    # Money change → single source of truth (honours NORM/STAB settlement, PARTIAL, auto-debit)
    # and drop a dated PAYMENT event for the delta so the collection shows in the trend / FTD-MTD.
    if any(f in data for f in ("received_amount", "funding_amount", "total_outstanding", "enr",
                               "principal_outstanding", "norm_amount", "stab_amount", "auto_debit", "norm_stab")):
        from .. import paymath
        if "received_amount" in data:
            _delta = Decimal(str(case.received_amount or 0)) - _old_recv
            if abs(_delta) >= Decimal("0.5"):
                _credit = case.assigned_caller_id or case.assigned_fos_id or user.id
                db.add(models.CallLog(case_id=case.id, caller_id=_credit, disposition="PAYMENT",
                                      ptp_amount=_delta, note=f"Case edit collection change (by {user.name})"))
        paymath.recompute(case)
    if change_msgs:
        from .notifications import notify_case_change
        notify_case_change(db, case, user, "; ".join(change_msgs))
    db.commit()
    db.refresh(case)
    from .realtime import notify_data_changed
    notify_data_changed(case.bank, case.product)
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


# ── Joint allocation ─────────────────────────────────────────────────────────────
# A SECOND FOS is sent to a new address when the customer isn't at the original one. The case stays
# allocated to the primary FOS (keeps the target/allocation); the joint FOS sees it in a SEPARATE
# "Joint cases" list. It does NOT count in the joint FOS's own caseload/performance until HE logs a
# PAID visit — at which point the collection credit moves to him (handled in visits + collection_fos_id).
def collection_fos_id(case) -> int | None:
    """Who gets COLLECTION credit for a case: the joint FOS once he's logged a paid visit,
    otherwise the primary (allocated) FOS. Allocation/target always stay with the primary."""
    if getattr(case, "joint_fos_id", None) and getattr(case, "joint_collected_at", None):
        return case.joint_fos_id
    return case.assigned_fos_id


def attach_joint_display(cases, db, viewer=None):
    """Set transient joint_fos_name + joint_for_me on each case for CaseOut serialization."""
    ids = {c.joint_fos_id for c in cases if getattr(c, "joint_fos_id", None)}
    names = {}
    if ids:
        names = {u.id: u.name for u in db.query(models.User.id, models.User.name)
                 .filter(models.User.id.in_(ids)).all()}
    vid = getattr(viewer, "id", None)
    for c in cases:
        c.joint_fos_name = names.get(getattr(c, "joint_fos_id", None))
        c.joint_for_me = bool(vid and getattr(c, "joint_fos_id", None) == vid)
    return cases


class JointAllocateIn(BaseModel):
    case_ids: list[int]
    fos_id: int
    note: str | None = None


@router.post("/joint-allocate")
def joint_allocate(body: JointAllocateIn, db: Session = Depends(get_db),
                   user: models.User = Depends(require_roles("admin", "headoffice", "teamlead", "manager"))):
    """Joint-allocate selected cases to a SECOND FOS (any active FOS). The case stays with its
    primary FOS; the joint FOS gets it in a separate list to visit the new address and collect."""
    if not body.case_ids:
        raise HTTPException(status_code=400, detail="No cases selected")
    fos = db.query(models.User).filter(models.User.id == body.fos_id, models.User.is_active == True).first()
    if not fos or not (fos.role == "fos" or getattr(fos, "also_field_agent", False)):
        raise HTTPException(status_code=400, detail="Pick an active field officer (FOS)")
    cases = _scope(db.query(models.Case), user).filter(models.Case.id.in_(body.case_ids)).all()
    if not cases:
        raise HTTPException(status_code=404, detail="No matching cases in your scope")
    now = datetime.now(_IST_TZ)
    changed = 0
    for case in cases:
        if case.assigned_fos_id == fos.id:
            continue                                   # already the primary — nothing to joint
        case.joint_fos_id = fos.id
        case.joint_assigned_at = now
        case.joint_assigned_by = user.id
        case.joint_collected_at = None                 # fresh joint — not yet collected by them
        case.joint_note = (body.note or "").strip()[:200] or None
        audit.record(db, user, "joint_allocate", case,
                     detail=f"Joint FOS → {fos.name} ({fos.emp_code or ''})"
                            + (f" · {body.note}" if (body.note or '').strip() else ""),
                     target_user_id=fos.id)
        audit.stamp_case(case, user)
        changed += 1
    db.commit()
    return {"joint_allocated": changed, "fos": fos.name, "fos_id": fos.id}


@router.post("/joint-unallocate")
def joint_unallocate(body: dict = Body(...), db: Session = Depends(get_db),
                     user: models.User = Depends(require_roles("admin", "headoffice", "teamlead", "manager"))):
    """Remove the joint FOS from selected cases (only if they haven't already collected)."""
    ids = [int(x) for x in (body.get("case_ids") or []) if str(x).isdigit()]
    if not ids:
        raise HTTPException(status_code=400, detail="No cases selected")
    cases = _scope(db.query(models.Case), user).filter(models.Case.id.in_(ids)).all()
    changed = 0
    for case in cases:
        if not case.joint_fos_id:
            continue
        case.joint_fos_id = None
        case.joint_assigned_at = None
        case.joint_assigned_by = None
        case.joint_note = None
        # keep joint_collected_at history as-is (a past collection credit stays recorded)
        audit.record(db, user, "joint_unallocate", case, detail="Joint FOS removed")
        audit.stamp_case(case, user)
        changed += 1
    db.commit()
    return {"joint_unallocated": changed}


@router.get("/joint-mine", response_model=list[schemas.CaseOut])
def joint_mine(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """The current FOS's JOINT cases — allocated to someone else, but sent to this FOS for a
    new-address visit. Shown in a separate list; they don't count in his own cases/performance
    until he logs a paid visit. Once collected, they drop off this list."""
    cases = (db.query(models.Case)
             .filter(models.Case.joint_fos_id == user.id,
                     models.Case.joint_collected_at.is_(None),
                     models.Case.removed.isnot(True))
             .order_by(models.Case.joint_assigned_at.desc()).all())
    attach_joint_display(cases, db, user)
    return cases


class PaymentIn(BaseModel):
    amount: Decimal
    mode: str = "UPI"
    note: str | None = None
    norm_stab: str | None = None      # NORM / STAB paid (credit-card cases)
    auto_debit: bool = False          # auto-debit / e-NACH: allow ₹0 and still mark PAID


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
    # Auto-debit / e-NACH settlement may be logged at ₹0 (mandate set, nothing collected yet) —
    # it still marks the case PAID. Every other payment must be a positive amount.
    if amt < 0 or (amt == 0 and not body.auto_debit):
        raise HTTPException(status_code=400, detail="Amount must be greater than zero")
    if body.auto_debit:
        case.auto_debit = True

    case.received_amount = (Decimal(case.received_amount or 0) + amt)
    if body.norm_stab:
        ns = body.norm_stab.upper()
        case.norm_stab = "ROLLBACK" if "ROLL" in ns else ("STAB" if "STAB" in ns else ("NORM" if "NORM" in ns else case.norm_stab))
    # Single source of truth: recompute PAID / PARTIAL / UNPAID, pending, status, follow-up.
    # A NORM/STAB case is PAID only once the settlement amount is reached; below it stays PARTIAL.
    # Auto-debit forces PAID even at ₹0 (cash stays 0, pending stays the full balance).
    from .. import paymath
    paymath.recompute(case)

    _mode = "Auto-debit" if body.auto_debit else body.mode
    note = (f"Auto-debit settlement" if (body.auto_debit and amt == 0) else f"₹{amt} via {_mode}") + (f" — {body.note}" if body.note else "")
    db.add(models.CallLog(case_id=case.id, caller_id=user.id,
                          disposition="PAYMENT", ptp_amount=amt, note=note))
    audit.record(db, user, "payment", case, new=str(amt),
                 detail=f"Collected ₹{amt} via {_mode}" + (f" ({body.note})" if body.note else ""))
    audit.stamp_case(case, user)
    from .notifications import notify_case_change
    notify_case_change(db, case, user,
                       f"Payment ₹{amt} via {_mode} → {case.paid_status}" + (f" · {body.note}" if body.note else ""),
                       ntype="payment")
    from .. import presence as _presence
    _presence.touch(db, user.id, active=True)   # recording a payment = active
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
    auto_debit: bool = False                 # auto-debit / e-NACH: mark PAID at ₹0, collect nothing


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
    _ensure_open(case, actor)   # locked for FOS/callers once escalated/closed
    amt = Decimal(str(body.amount)) if body.amount is not None else Decimal(0)
    if body.auto_debit:
        # Auto-debit / e-NACH: mark PAID at whatever was entered (₹0 allowed) — do NOT default to
        # the full outstanding. Cash = the entered amount (0), pending stays the full balance.
        case.auto_debit = True
        if amt < 0:
            amt = Decimal(0)
    else:
        if amt <= 0:                                # default to whatever is still outstanding
            amt = _pay_base_total(case) - Decimal(case.received_amount or 0)
        if amt <= 0:
            raise HTTPException(status_code=400, detail="Nothing outstanding to mark paid — enter an amount")
    case.received_amount = Decimal(case.received_amount or 0) + amt
    if body.norm_stab:
        ns = body.norm_stab.upper()
        case.norm_stab = "ROLLBACK" if "ROLL" in ns else ("STAB" if "STAB" in ns else ("NORM" if "NORM" in ns else case.norm_stab))
    # Recompute: a NORM/STAB case only becomes PAID at/above its settlement amount; below it is
    # recorded as PARTIAL (and excluded from cash collection). Plain cases PAID once outstanding is met.
    from .. import paymath
    new_status = paymath.recompute(case)
    credit_id = case.assigned_caller_id or case.assigned_fos_id or actor.id
    tag = f" ({case.norm_stab})" if case.norm_stab else ""
    db.add(models.CallLog(case_id=case.id, caller_id=credit_id,
                          disposition="PAID" if new_status == "PAID" else "PAYMENT", ptp_amount=amt,
                          note=f"{body.mode or 'DPR'}: customer paid ₹{amt}{tag}" + (f" — {body.note}" if body.note else "")))
    case.last_contacted_at = datetime.now(timezone.utc)
    audit.record(db, actor, "paid" if new_status == "PAID" else "payment", case, old="UNPAID", new=new_status,
                 detail=f"Marked {new_status} ₹{amt}{tag}")
    audit.stamp_case(case, actor)
    from .notifications import notify_case_change
    notify_case_change(db, case, actor, f"Marked {new_status} ₹{amt}{tag}" + (f" · {body.note}" if body.note else ""), ntype="paid")
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
    case.auto_debit = False           # reverting clears any auto-debit settlement
    case.follow_up_date = None
    if prev > 0:                                    # negative entry nets the caller's collected back down
        credit_id = case.assigned_caller_id or case.assigned_fos_id or actor.id
        db.add(models.CallLog(case_id=case.id, caller_id=credit_id, disposition="PAID", ptp_amount=(-prev),
                              note=f"Reversal: payment of ₹{prev} reverted (marked unpaid)"))
    case.last_contacted_at = datetime.now(timezone.utc)
    audit.record(db, actor, "unpaid", case, old="PAID", new="UNPAID",
                 detail=f"Marked UNPAID (reversed ₹{prev})" if prev > 0 else "Marked UNPAID")
    audit.stamp_case(case, actor)
    from .notifications import notify_case_change
    notify_case_change(db, case, actor, f"Marked UNPAID" + (f" (reversed ₹{prev})" if prev > 0 else ""), ntype="unpaid")
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
        if Decimal(case.received_amount or 0) <= 0:
            case.norm_stab = None          # nothing left collected → drop any settlement tag
            case.auto_debit = False
        # Single source of truth: a NORM/STAB case still at/above its settlement stays PAID; only
        # below it becomes PARTIAL (the old base-minus-received rule wrongly downgraded settled cases).
        from .. import paymath
        paymath.recompute(case)
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
    _ensure_open(case, actor)   # escalated/closed cases are read-only for FOS & callers
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

    # Alert everyone associated (assigned FOS/caller, team lead, manager, HO) of the new contact.
    parts = []
    if "phone" in changed and case.new_phone:
        parts.append(f"📞 New phone {case.new_phone}")
    if "address" in changed and case.new_address:
        parts.append(f"📍 New address {case.new_address}")
    from .notifications import notify_case_change
    notify_case_change(db, case, actor, " · ".join(parts), ntype="contact_update")

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
                   "recording_url": getattr(cl, "recording_url", None),
                   "ptp_date": cl.ptp_date.isoformat() if cl.ptp_date else None})

    # Every other mutation on this case — live-sheet cell edits, reassigns, DPR updates,
    # escalations, contact changes — from the audit trail, so History shows who did what.
    # (Visits/calls/payments already come from their own tables above; skip those actions.)
    _AUDIT_TITLES = {
        "cell_edit": "Live-sheet edit", "edit": "Edited", "field_edit": "Field updated",
        "dpr_update": "DPR update", "reassign": "Reassigned", "deallocate": "Deallocated",
        "transfer": "Transferred", "escalate": "Escalated", "restore": "Restored",
        "delete": "Removed", "unpaid": "Marked unpaid", "flag": "Flagged",
        "new_phone": "Phone updated", "new_address": "Address updated",
    }
    _AUDIT_SKIP = {"payment", "paid", "call", "visit", "import", "download", "login"}
    for a in db.query(models.AuditLog).filter(models.AuditLog.case_id == case_id).all():
        act = (a.action or "").lower()
        if act in _AUDIT_SKIP:
            continue
        if a.field and (a.old_value is not None or a.new_value is not None):
            detail = f"{a.field}: {a.old_value if a.old_value not in (None, '') else '—'} → " \
                     f"{a.new_value if a.new_value not in (None, '') else '—'}"
            if a.detail and a.detail not in detail:
                detail = a.detail
        else:
            detail = a.detail or act
        ev.append({"type": "edit", "at": a.at, "by": a.actor_name or users.get(a.actor_id),
                   "role": a.actor_role, "title": _AUDIT_TITLES.get(act, act.replace("_", " ").title() or "Change"),
                   "field": a.field, "old": a.old_value, "new": a.new_value, "detail": detail})

    from datetime import datetime, timezone
    ev.sort(key=lambda e: e["at"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return ev


# ============================ Case export (Excel / PDF) ============================
class CaseExportBody(BaseModel):
    ids: list[int] = []
    fmt: str = "xlsx"                 # "xlsx" | "pdf"
    title: str | None = None          # e.g. "AXIS · BL · Sep'26"


def _fnum(v) -> float:
    try:
        return float(v or 0)
    except Exception:
        return 0.0


def _cases_xlsx(cases, title: str) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    cols = [("#", 6), ("Account", 20), ("Card", 20), ("Customer", 26), ("Phone", 15),
            ("Alt Phone", 15), ("Bank", 12), ("Product", 16), ("Bucket", 10), ("Cycle", 8),
            ("Month", 10), ("TOS", 14), ("Pending", 14), ("Received", 14), ("NORM", 12),
            ("STAB", 12), ("N/S", 8), ("Status", 12), ("Address", 42), ("Address 2", 42)]
    wb = Workbook(); ws = wb.active; ws.title = "Cases"
    ws.append([c[0] for c in cols])
    hf = Font(bold=True, color="FFFFFF"); fill = PatternFill("solid", fgColor="0F2A4A")
    for cell in ws[1]:
        cell.font = hf; cell.fill = fill; cell.alignment = Alignment(horizontal="center")
    for i, c in enumerate(cases, 1):
        ws.append([i, c.account_no, c.card_no, c.customer_name, c.phone, c.alt_phone,
                   c.bank, c.product, c.bucket, c.cycle, c.month,
                   _fnum(c.total_outstanding), _fnum(c.pending_amount), _fnum(c.received_amount),
                   _fnum(c.norm_amount), _fnum(c.stab_amount), c.norm_stab,
                   (c.paid_status or c.status or ""), c.address, c.address2])
    ws.append(["", "", "", "TOTAL", "", "", "", "", "", "", "",
               sum(_fnum(c.total_outstanding) for c in cases),
               sum(_fnum(c.pending_amount) for c in cases),
               sum(_fnum(c.received_amount) for c in cases), "", "", "", "", "", ""])
    for cell in ws[ws.max_row]:
        cell.font = Font(bold=True)
    for i, (_, w) in enumerate(cols, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


def _cases_pdf(cases, title: str, user) -> bytes:
    """A readable account worksheet: one full-width CARD per case that GROWS to fit every detail —
    all phone numbers (phone / alt / new), all three addresses with their pincodes, the full money
    breakdown (TOS, NORM, STAB, N/S, pending, received), portfolio, disposition/PTP — plus a tick
    box + write-in 'Collected / Remarks' line the officer fills in the field. Nothing is truncated."""
    from fpdf import FPDF
    from datetime import datetime as _dt

    PAGE_W, PAGE_H, M = 210.0, 297.0, 10.0
    CARD_W = PAGE_W - 2 * M
    LHR, LHA = 4.4, 4.0                 # info-row and address-line heights
    GAP = 4.0

    def s1(v):
        return str(v if v is not None else "").strip().encode("latin-1", "replace").decode("latin-1")

    def g(c, a):
        v = getattr(c, a, None)
        return v if (v is not None and str(v).strip() != "") else None

    def status_of(c):
        st = (s1(getattr(c, "paid_status", "")) or s1(getattr(c, "status", ""))).upper()
        d = s1(getattr(c, "disposition", "")).upper()
        if st == "PAID":
            return "PAID", (22, 163, 74)
        if "PTP" in d or st == "PTP":
            return "PTP", (217, 119, 6)
        if st == "PARTIAL":
            return "PARTIAL", (202, 138, 4)
        return (st or "OPEN")[:12], (220, 38, 38)

    def addr_rows(c):
        rows = []
        for a, p, lbl in (("address", "pincode", "Address 1"), ("address2", "pincode2", "Address 2"),
                          ("address3", "pincode3", "Address 3")):
            av, pv = g(c, a), g(c, p)
            if av or pv:
                rows.append((lbl, (s1(av) + (f"  -  PIN {s1(pv)}" if pv else "")).strip()))
        if g(c, "new_address"):
            rows.append(("New address", s1(g(c, "new_address"))))
        return rows or [("Address", "-")]

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=False)
    pdf.set_title(f"RecoverIQ - {s1(title)}")

    def nlines(txt, w):
        try:
            return max(1, len(pdf.multi_cell(w, LHA, txt, dry_run=True, output="LINES")))
        except Exception:
            cpl = max(16, int(w / 1.65))
            return max(1, -(-len(txt) // cpl))

    def banner(first):
        pdf.add_page()
        pdf.set_fill_color(15, 42, 74); pdf.rect(0, 0, PAGE_W, 22, "F")
        pdf.set_xy(M, 5); pdf.set_font("Helvetica", "B", 15); pdf.set_text_color(255, 255, 255)
        pdf.cell(CARD_W, 7, s1(f"RecoverIQ  -  {title}")[:70])
        pdf.set_xy(M, 13.5); pdf.set_font("Helvetica", "", 8.5); pdf.set_text_color(205, 216, 232)
        pdf.cell(CARD_W, 5, f"{s1(user.name)[:44]}    {len(cases)} accounts    {_dt.now().strftime('%d-%b-%Y %H:%M')}")
        if first:
            pdf.set_xy(M, 24.5); pdf.set_font("Helvetica", "B", 9); pdf.set_text_color(15, 42, 74)
            pdf.cell(CARD_W, 6, f"Total pending  Rs {sum(_fnum(c.pending_amount) for c in cases):,.0f}"
                                f"        Total received  Rs {sum(_fnum(c.received_amount) for c in cases):,.0f}")
            return 33.0
        return 27.0

    def measure(c):
        pdf.set_font("Helvetica", "", 7.8)
        a = sum(nlines(f"{lbl}: {val}", CARD_W - 10) for lbl, val in addr_rows(c))
        return 9.0 + 4 * LHR + 1.2 + a * LHA + 4.0 + 6.5

    def card(y, idx, c):
        h = measure(c)
        label, col = status_of(c)
        pdf.set_draw_color(223, 229, 237); pdf.set_line_width(0.2)
        pdf.set_fill_color(249, 251, 253); pdf.rect(M, y, CARD_W, h, "DF")
        pdf.set_fill_color(*col); pdf.rect(M, y, 2.4, h, "F")                 # left accent
        pdf.rect(M + 2.4, y, CARD_W - 2.4, 7.4, "F")                          # header band
        pad, inner = M + 5, CARD_W - 10
        # header: name | status | pending
        pdf.set_xy(M + 5, y + 1.5); pdf.set_font("Helvetica", "B", 9.8); pdf.set_text_color(255, 255, 255)
        pdf.cell(CARD_W - 74, 4.6, s1(f"{idx}. {c.customer_name or '-'}")[:72])
        pdf.set_xy(M + CARD_W - 68, y + 1.6); pdf.set_font("Helvetica", "B", 7.6)
        pdf.cell(30, 4.4, s1(label)[:14], align="C")
        pdf.set_xy(M + CARD_W - 38, y + 1.5); pdf.set_font("Helvetica", "B", 8.6)
        pdf.cell(33, 4.6, f"Pend Rs {_fnum(c.pending_amount):,.0f}", align="R")
        yy = y + 9.0
        pdf.set_text_color(45, 45, 45)
        # numbers: account / card / phone / alt / new phone
        nums = [f"A/c {c.account_no or '-'}"]
        if g(c, "card_no"): nums.append(f"Card {s1(g(c, 'card_no'))}")
        nums.append(f"Ph {c.phone or '-'}")
        if g(c, "alt_phone"): nums.append(f"Alt {s1(g(c, 'alt_phone'))}")
        if g(c, "new_phone"): nums.append(f"New Ph {s1(g(c, 'new_phone'))}")
        pdf.set_xy(pad, yy); pdf.set_font("Helvetica", "", 7.8)
        pdf.cell(inner, LHR, s1("    ".join(nums))[:140]); yy += LHR
        # portfolio + month + status
        pdf.set_xy(pad, yy)
        pdf.cell(inner, LHR, s1(f"{c.bank or '-'} / {c.product or '-'}   |   Bkt {c.bucket or '-'}"
                                f"   |   Cyc {c.cycle or '-'}" + (f"   |   {s1(g(c,'month'))}" if g(c, "month") else "")
                                + f"   |   Status {s1(c.paid_status or c.status or '-')}")[:140]); yy += LHR
        # money breakdown
        pdf.set_xy(pad, yy); pdf.set_font("Helvetica", "B", 7.8); pdf.set_text_color(30, 30, 30)
        pdf.cell(inner, LHR, f"Pending Rs {_fnum(c.pending_amount):,.0f}   Received Rs {_fnum(c.received_amount):,.0f}"
                             f"   TOS {_fnum(c.total_outstanding):,.0f}   NORM {_fnum(g(c,'norm_amount')):,.0f}"
                             f"   STAB {_fnum(g(c,'stab_amount')):,.0f}   N/S {c.norm_stab or '-'}"); yy += LHR
        # FOS / caller / disposition / PTP
        _ptp = ""
        try:
            _ptp = f"   PTP {str(c.follow_up_date)[:10]}" if (c.follow_up_date and (c.disposition or '').upper() == 'PTP') else ""
        except Exception:
            _ptp = ""
        pdf.set_xy(pad, yy); pdf.set_font("Helvetica", "", 7.6); pdf.set_text_color(70, 70, 70)
        pdf.cell(inner, LHR, s1(f"FOS {c.fos_name or '-'}   Caller {g(c,'caller_name') or '-'}"
                                f"   Dispo {c.disposition or '-'}{_ptp}")[:140]); yy += LHR + 1.2
        # addresses (full, wrapped)
        pdf.set_font("Helvetica", "", 7.6); pdf.set_text_color(35, 35, 35)
        for lbl, val in addr_rows(c):
            pdf.set_xy(pad, yy)
            pdf.multi_cell(inner, LHA, f"{lbl}: {val}", align="L")
            yy = pdf.get_y()
        # action row: tick box + write-in collected + remarks
        ry = y + h - 6.2
        pdf.set_draw_color(205, 211, 219); pdf.set_line_width(0.2)
        pdf.line(M + 4, ry - 1.6, M + CARD_W - 4, ry - 1.6)
        pdf.set_draw_color(40, 40, 40); pdf.set_line_width(0.5)
        pdf.rect(pad, ry, 4.6, 4.6, "D")
        pdf.set_xy(pad + 6, ry - 0.3); pdf.set_font("Helvetica", "B", 8); pdf.set_text_color(25, 25, 25)
        pdf.cell(16, 5, "Visited")
        pdf.set_xy(pad + 26, ry - 0.3); pdf.set_font("Helvetica", "", 7.6); pdf.set_text_color(70, 70, 70)
        pdf.cell(66, 5, "Collected Rs ________________")
        pdf.set_xy(pad + 96, ry - 0.3); pdf.cell(inner - 96, 5, "Remarks ______________________")
        return h

    y = banner(True)
    for i, c in enumerate(cases, 1):
        h = measure(c)
        if y + h > PAGE_H - M:
            y = banner(False)
        card(y, i, c)
        y += h + GAP
    return bytes(pdf.output())


@router.post("/export")
def export_cases(body: CaseExportBody, db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)):
    """Export the given cases (already filtered client-side) as a styled Excel or PDF.
    Scoped to the caller's own visible cases — you can only export what you're allowed to see."""
    ids = (body.ids or [])[:5000]
    if not ids:
        raise HTTPException(status_code=400, detail="No cases selected to export")
    rows = _scope(db.query(models.Case), user).filter(models.Case.id.in_(ids)).all()
    cases = [c for c in rows if c.removed is not True]
    if not cases:
        raise HTTPException(status_code=404, detail="No accessible cases in the selection")
    order = {cid: i for i, cid in enumerate(ids)}          # preserve the on-screen order
    cases.sort(key=lambda c: order.get(c.id, 1 << 30))
    title = (body.title or "My Cases").strip()
    fmt = (body.fmt or "xlsx").lower()
    safe = "".join(ch for ch in title if ch.isalnum() or ch in " -_").strip().replace(" ", "_") or "Cases"
    try:
        if fmt == "pdf":
            data, media, ext = _cases_pdf(cases, title, user), "application/pdf", "pdf"
        else:
            data, media, ext = (_cases_xlsx(cases, title),
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx")
    except ImportError:
        raise HTTPException(status_code=503, detail="PDF export needs the 'fpdf2' package on the server "
                                                    "(pip install fpdf2). Excel export works without it.")
    audit.record(db, user, "download", None, entity_type="download",
                 detail=f"Exported {len(cases)} cases ({ext}) — {title}")
    db.commit()
    return StreamingResponse(io.BytesIO(data), media_type=media,
                             headers={"Content-Disposition": f'attachment; filename="{safe}.{ext}"'})
