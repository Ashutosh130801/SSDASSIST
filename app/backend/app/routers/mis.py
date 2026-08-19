"""MIS engine + API — the calculation core, computed live from case data per product.

Reproduces the agency's MIS pivots exactly:
  * % is ENR-based  →  paid ENR / total ENR   (ENR = End Net Receivables = EMI 0/S + CURR_BAL)
  * PAID / UNPAID from the paid_status field; VISITED from the visited flag
  * NORM / STAB is a given per-case attribute (norm_stab), not computed
  * AMOUNT (received_amount) = CASH COLL
  * Employee performance: TARGET % is manager-entered; everything else auto-calculates.
"""
import io
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import models
from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user, require_roles
from .cases import _scope

IST = timezone(timedelta(hours=5, minutes=30))
OBSTACLE = {"DISPUTE", "WRONG NUMBER", "WRONG_NUMBER", "RNR", "SWITCHED OFF", "SWITCHED_OFF",
            "NOT REACHABLE", "NOT_REACHABLE", "REFUSED", "NC", "NO_CONTACT", "NO CONTACT"}

router = APIRouter(prefix="/api/mis", tags=["mis"])

MIS_ROLES = ("admin", "manager", "backend", "headoffice", "teamlead")


def _f(x) -> float:
    return float(x or 0)


def _pct(part: float, whole: float) -> float:
    return round((part / whole * 100.0), 2) if whole else 0.0


def _is_paid(c) -> bool:
    return (c.paid_status or "").upper() == "PAID"


def _agg(rows: list) -> dict:
    """Core aggregation for a group of cases (ENR-based percentages)."""
    total_enr = sum(_f(c.enr) for c in rows)
    paid_rows = [c for c in rows if _is_paid(c)]
    unpaid_rows = [c for c in rows if not _is_paid(c)]
    paid_enr = sum(_f(c.enr) for c in paid_rows)
    unpaid_enr = sum(_f(c.enr) for c in unpaid_rows)
    # NORM / STAB is chosen at payment time (paid CC cases). Both % are over TOTAL ENR,
    # so norm% + stab% = total paid %.
    norm_paid_enr = sum(_f(c.enr) for c in paid_rows if (c.norm_stab or "").upper() == "NORM")
    stab_paid_enr = sum(_f(c.enr) for c in paid_rows if (c.norm_stab or "").upper() == "STAB")
    # ROLLBACK is a third paid category for 2/3/4 BKT products (mirrors NORM/STAB).
    rb_paid = [c for c in paid_rows if (c.norm_stab or "").upper() == "ROLLBACK"]
    rollback_paid_enr = sum(_f(c.enr) for c in rb_paid)
    rollback_collected = sum(_f(c.received_amount) for c in rb_paid)
    rollback_target = sum(_f(getattr(c, "rollback_amount", 0)) for c in rows)
    return {
        "count": len(rows),
        "paid": len(paid_rows),
        "unpaid": len(unpaid_rows),
        "enr": round(total_enr, 2),
        "paid_enr": round(paid_enr, 2),
        "unpaid_enr": round(unpaid_enr, 2),
        "pct": _pct(paid_enr, total_enr),                 # total PAID % = paid ENR / total ENR
        "norm_pct": _pct(norm_paid_enr, total_enr),       # ENR paid via NORM / total ENR
        "stab_pct": _pct(stab_paid_enr, total_enr),       # ENR paid via STAB / total ENR
        "norm_paid_enr": round(norm_paid_enr, 2),
        "stab_paid_enr": round(stab_paid_enr, 2),
        # Rollback analytics (mirror of NORM/STAB)
        "rollback_pct": _pct(rollback_paid_enr, total_enr),   # ENR paid via ROLLBACK / total ENR
        "rollback_paid_enr": round(rollback_paid_enr, 2),
        "rollback_collected": round(rollback_collected, 2),   # actual cash collected as rollback
        "rollback_target": round(rollback_target, 2),         # sum of rollback amounts on file
        "rollback_count": len(rb_paid),
        "amount": round(sum(_f(c.received_amount) for c in rows), 2),   # CASH COLL
        "pending": round(sum(_f(c.pending_amount) for c in rows), 2),   # outstanding still to collect
        "recovery_pct": _pct(sum(_f(c.received_amount) for c in rows), total_enr),  # cash collected / ENR
        "visited": sum(1 for c in rows if c.visited),
        "not_visited": sum(1 for c in rows if not c.visited),
    }


def _ist_date(dt):
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST).date()


def collection_windows(db: Session, case_ids: list, overall_received=None) -> dict:
    """Cash collected across comparison windows, from actual payment events (call-log PAYMENTs
    + field-visit collections), bucketed by IST date:
      FTD  = For The Day (today)      MTD  = Month Till Day (1st → today)
      LMTD = Last Month Till Day (same day-of-month last month)   Overall = lifetime.
    Overall defaults to the lifetime received_amount on the cases when supplied (most accurate)."""
    import calendar
    res = {"ftd": 0.0, "mtd": 0.0, "lmtd": 0.0, "overall": float(overall_received or 0.0)}
    if not case_ids:
        return {k: round(v, 2) for k, v in res.items()}
    today = datetime.now(IST).date()
    som = today.replace(day=1)
    lm_year, lm_month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    lm_days = calendar.monthrange(lm_year, lm_month)[1]
    lm_som = date(lm_year, lm_month, 1)
    lm_till = date(lm_year, lm_month, min(today.day, lm_days))

    calls = (db.query(models.CallLog.created_at, models.CallLog.ptp_amount)
             .filter(models.CallLog.case_id.in_(case_ids), models.CallLog.disposition == "PAYMENT").all())
    visits = (db.query(models.Visit.created_at, models.Visit.amount_collected)
              .filter(models.Visit.case_id.in_(case_ids), models.Visit.amount_collected > 0).all())
    events = [(c[0], float(c[1] or 0)) for c in calls] + [(v[0], float(v[1] or 0)) for v in visits]

    ev_overall = 0.0
    for dt, amt in events:
        d = _ist_date(dt)
        if d is None:
            continue
        ev_overall += amt
        if d == today:
            res["ftd"] += amt
        if som <= d <= today:
            res["mtd"] += amt
        if lm_som <= d <= lm_till:
            res["lmtd"] += amt
    if overall_received is None:
        res["overall"] = ev_overall
    return {k: round(v, 2) for k, v in res.items()}


def _group(cases: list, keyfn, idfn=None) -> list:
    buckets: dict[str, list] = {}
    ids: dict[str, int] = {}
    for c in cases:
        k = keyfn(c) or "—"
        buckets.setdefault(k, []).append(c)
        if idfn and k not in ids:               # capture a clickable user id for the bucket
            v = idfn(c)
            if v:
                ids[k] = v
    out = [{"label": k, "emp_id": ids.get(k), **_agg(v)} for k, v in buckets.items()]
    out.sort(key=lambda r: r["enr"], reverse=True)
    return out


def compute_mis(db: Session, user: models.User, bank: str, product: str,
                period: str | None = None, area: str | None = None, branch: str | None = None,
                cycles: list | None = None, fos_ids: list | None = None,
                caller_ids: list | None = None, paid: str | None = None) -> dict:
    from .cases import propensity as _prop
    from sqlalchemy import func as _func
    q = _scope(db.query(models.Case), user).filter(models.Case.bank == bank, models.Case.product == product)
    if branch:                          # branch-specific MIS (same product, different branches)
        q = q.filter(models.Case.branch == branch)
    if period:                          # month-wise MIS: this month vs next month
        q = q.filter(models.Case.period == period)
    if area:                            # full MIS scoped to a single AREA (team) code
        q = q.filter(models.Case.team == area)
    # ---- multi-select filters (all AND-combined) — analytics recompute on the filtered set ----
    if cycles:
        q = q.filter(_func.lower(_func.trim(_func.coalesce(models.Case.cycle, ""))).in_(
            [str(c).strip().lower() for c in cycles]))
    if fos_ids:
        q = q.filter(models.Case.assigned_fos_id.in_(fos_ids))
    if caller_ids:
        q = q.filter(models.Case.assigned_caller_id.in_(caller_ids))
    if paid:
        q = q.filter(models.Case.paid_status == paid)
    cases = q.all()
    for c in cases:                     # score is a transient attribute — set it for the insight tables
        c.propensity = _prop(c)

    targets = {t.emp_name: _f(t.target_pct) for t in
               db.query(models.MisTarget).filter(models.MisTarget.bank == bank,
                                                 models.MisTarget.product == product).all()}
    # ONE product-wide target % (manager/back-office sets it once) — same goal for every
    # FOS and caller, not per-person. Stored under the sentinel emp_name "*ALL*".
    product_target = targets.get("*ALL*", 0.0)

    def _leaderboard(groups):
        lb = []
        for r in groups:
            tgt = product_target
            tenr = round(r["enr"] * tgt / 100.0, 2)
            to_tgt = _pct(r["paid_enr"], tenr) if tenr else 0.0
            lb.append({
                "emp": r["label"], "emp_id": r.get("emp_id"), "count": r["count"], "unpaid": r["unpaid"], "paid": r["paid"],
                "enr": r["enr"], "target_pct": tgt, "target_enr": tenr,
                "achieved_pct": r["pct"], "achieved_enr": r["paid_enr"],
                "gap_enr": round(max(tenr - r["paid_enr"], 0), 2), "to_target_pct": to_tgt,
                "status": ("none" if not tenr else "green" if to_tgt >= 100 else "amber" if to_tgt >= 60 else "red"),
                "pending_visit": r["not_visited"], "cash_coll": r["amount"],
            })
        lb.sort(key=lambda x: x["achieved_enr"], reverse=True)
        return lb

    # Every FOS/caller in the MIS is shown by their REAL full name + employee ID when the case
    # is allocated to a system user (e.g. "Uday Kumar (FO007)"). When it isn't allocated we fall
    # back to the FOS/CALLER NAME printed in the upload sheet, so EVERY field officer associated
    # with the portfolio still appears in the analytics (not lumped into one "Unassigned" bucket).
    # Only truly blank rows show as "Unassigned".
    _ppl = {u.id: (u.name, u.emp_code) for u in db.query(models.User).all()}

    def _person_label(uid):
        if uid and uid in _ppl:
            nm, code = _ppl[uid]
            return f"{nm} ({code})" if code else (nm or None)
        return None

    # Some cases are CALLER-ONLY (no FOS in the sheet) — these are worked only by callers.
    # They still count in the portfolio; in the FOS-wise pivot they group under a clear
    # "No FOS (caller-only)" bucket instead of being mistaken for a mis-configured row.
    def _fos_label(c):
        return _person_label(c.assigned_fos_id) or (c.fos_name or "").strip() or "— No FOS (caller-only) —"

    def _caller_label(c):
        return _person_label(c.assigned_caller_id) or (c.caller_name or "").strip() or "— No caller —"

    by_fos = _group(cases, _fos_label, lambda c: c.assigned_fos_id)
    by_caller_g = _group(cases, _caller_label, lambda c: c.assigned_caller_id)
    leaderboard = _leaderboard(by_fos)                 # FOS performance vs the one target
    caller_leaderboard = _leaderboard(by_caller_g)     # caller performance vs the same target

    # ---- extra insights ----
    ids = [c.id for c in cases]
    calls = db.query(models.CallLog).filter(models.CallLog.case_id.in_(ids)).all() if ids else []
    visits = db.query(models.Visit).filter(models.Visit.case_id.in_(ids)).all() if ids else []
    users = {u.id: u.name for u in db.query(models.User).all()}
    gfence = _f(get_settings().geofence_metres) or 300.0

    def d_ist(dt):
        if not dt:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(IST).date()

    now_ist = datetime.now(IST)
    today = now_ist.date()
    month_start = today.replace(day=1)
    dim = monthrange(today.year, today.month)[1]

    pay_events = [(d_ist(cl.created_at), _f(cl.ptp_amount)) for cl in calls if (cl.disposition or "") == "PAYMENT"]
    pay_events += [(d_ist(v.created_at), _f(v.amount_collected)) for v in visits if _f(v.amount_collected) > 0]

    collected_mtd = round(sum(a for d, a in pay_events if d and d >= month_start), 2)
    target_total = round(sum(r["target_enr"] for r in leaderboard), 2)
    proj = round(collected_mtd / today.day * dim, 2) if today.day else 0.0
    projection = {"collected_mtd": collected_mtd, "target_enr": target_total,
                  "projected_month_end": proj,
                  "projected_pct": _pct(proj, target_total),
                  "achieved_pct": _pct(collected_mtd, target_total)}

    trend = []
    for i in range(29, -1, -1):
        dd = today - timedelta(days=i)
        trend.append({"date": dd.isoformat(), "collected": round(sum(a for d, a in pay_events if d == dd), 2)})

    contacted = [c for c in cases if c.last_contacted_at or c.visited]
    paid_contacted = [c for c in contacted if _is_paid(c)]
    ptp_cases = [c for c in cases if (c.disposition or "").upper() == "PTP"]   # RTP = refuse, excluded
    ptp_kept = [c for c in ptp_cases if _is_paid(c)]
    ptp_broken = [c for c in ptp_cases if not _is_paid(c) and c.follow_up_date and c.follow_up_date < today]
    untouched = [c for c in cases if not c.last_contacted_at and not c.visited]
    funnel = {
        "total": len(cases), "contacted": len(contacted), "paid_of_contacted": len(paid_contacted),
        "conversion_pct": _pct(len(paid_contacted), len(contacted)),
        "ptp_total": len(ptp_cases), "ptp_kept": len(ptp_kept), "ptp_broken": len(ptp_broken),
        "ptp_kept_pct": _pct(len(ptp_kept), len(ptp_cases)),
        "untouched": len(untouched), "untouched_pending": round(sum(_f(c.pending_amount) for c in untouched), 2),
    }

    from .cases import propensity as _prop

    def case_row(c):
        return {"customer": c.customer_name, "account": c.account_no, "pending": _f(c.pending_amount),
                "enr": _f(c.enr), "propensity": getattr(c, "propensity", None) or _prop(c),
                "fos": _fos_label(c), "caller": _caller_label(c),
                "contacted": bool(c.last_contacted_at or c.visited)}

    untouched_tbl = [case_row(c) for c in sorted(untouched, key=lambda x: _f(x.pending_amount), reverse=True)[:25]]

    def recency(c):
        d = d_ist(c.last_contacted_at)
        return None if d is None else (today - d).days
    ag = {"Today": [], "≤7 days": [], "≤30 days": [], ">30 days": [], "Never contacted": []}
    for c in cases:
        r = recency(c)
        key = ("Never contacted" if r is None else "Today" if r <= 0 else "≤7 days" if r <= 7
               else "≤30 days" if r <= 30 else ">30 days")
        ag[key].append(c)
    aging = [{"label": k, "count": len(v), "pending": round(sum(_f(x.pending_amount) for x in v), 2)} for k, v in ag.items()]

    unpaid = [c for c in cases if not _is_paid(c)]
    top_pending = [case_row(c) for c in sorted(unpaid, key=lambda x: _f(x.pending_amount), reverse=True)[:25]]
    priority = [case_row(c) for c in sorted(unpaid, key=lambda x: (x.propensity or 0) * _f(x.pending_amount), reverse=True)[:25]]

    obg: dict[str, dict] = {}
    for c in cases:
        k = _caller_label(c)
        o = obg.setdefault(k, {"caller": k, "total": 0, "obstacles": 0})
        o["total"] += 1
        if (c.disposition or "").upper() in OBSTACLE:
            o["obstacles"] += 1
    obstacles = sorted(({**o, "rate_pct": _pct(o["obstacles"], o["total"])} for o in obg.values()),
                       key=lambda x: x["obstacles"], reverse=True)

    calls_today: dict[int, int] = {}
    visits_today: dict[int, int] = {}
    for cl in calls:
        if d_ist(cl.created_at) == today:
            calls_today[cl.caller_id] = calls_today.get(cl.caller_id, 0) + 1
    for v in visits:
        if d_ist(v.created_at) == today:
            visits_today[v.officer_id] = visits_today.get(v.officer_id, 0) + 1
    emp_ids = set(calls_today) | set(visits_today) | {cl.caller_id for cl in calls} | {v.officer_id for v in visits}
    productivity = sorted(
        [{"emp": users.get(i, f"#{i}"), "calls_today": calls_today.get(i, 0),
          "visits_today": visits_today.get(i, 0),
          "idle": (calls_today.get(i, 0) + visits_today.get(i, 0)) == 0} for i in emp_ids if i],
        key=lambda x: x["calls_today"] + x["visits_today"], reverse=True)

    eff: dict[int, dict] = {}
    for v in visits:
        e = eff.setdefault(v.officer_id, {"visits": 0, "distance": 0.0, "off": 0, "collected": 0.0})
        e["visits"] += 1
        dm = _f(v.distance_from_case_m)
        e["distance"] += dm
        if dm > gfence:
            e["off"] += 1
        e["collected"] += _f(v.amount_collected)
    field_efficiency = sorted(
        [{"fos": users.get(i, f"#{i}"), "visits": e["visits"], "distance_km": round(e["distance"] / 1000.0, 1),
          "off_location": e["off"], "collected": round(e["collected"], 2)} for i, e in eff.items()],
        key=lambda x: x["collected"], reverse=True)

    norm_target_total = sum(_f(c.norm_amount) for c in cases)
    paid_cases = [c for c in cases if _is_paid(c)]
    stab_paid = [c for c in paid_cases if (c.norm_stab or "").upper() == "STAB"]
    norm_paid = [c for c in paid_cases if (c.norm_stab or "").upper() == "NORM"]
    stab_enr = sum(_f(c.enr) for c in stab_paid)
    norm_enr = sum(_f(c.enr) for c in norm_paid)
    collected_all = sum(_f(c.received_amount) for c in cases)
    # Rollback (2/3/4 BKT): target on file, cash actually collected, and % over total ENR.
    rb_target_total = sum(_f(getattr(c, "rollback_amount", 0)) for c in cases)
    rb_paid = [c for c in paid_cases if (c.norm_stab or "").upper() == "ROLLBACK"]
    rb_collected = sum(_f(c.received_amount) for c in rb_paid)
    rb_enr = sum(_f(c.enr) for c in rb_paid)
    total_enr_all = sum(_f(c.enr) for c in cases)
    settlement = {
        "collected": round(collected_all, 2),
        "norm_target": round(norm_target_total, 2),
        "realization_pct": _pct(collected_all, norm_target_total),
        "stab_enr": round(stab_enr, 2), "norm_enr": round(norm_enr, 2),
        "stab_share_pct": _pct(stab_enr, stab_enr + norm_enr),
        "norm_share_pct": _pct(norm_enr, stab_enr + norm_enr),
        "leakage": round(sum(max(_f(c.norm_amount) - _f(c.received_amount), 0) for c in stab_paid), 2),
        # Rollback block
        "rollback_target": round(rb_target_total, 2),
        "rollback_collected": round(rb_collected, 2),
        "rollback_count": len(rb_paid),
        "rollback_enr": round(rb_enr, 2),
        "rollback_pct": _pct(rb_enr, total_enr_all),               # rollback ENR / total ENR
        "rollback_realization_pct": _pct(rb_collected, rb_target_total),  # collected / rollback target
    }

    is_plbl = any((c.segment or "") == "PL/BL" for c in cases)
    return {
        "bank": bank, "product": product,
        "segment": "PL/BL" if is_plbl else (cases[0].segment if cases else None),
        "base_label": "TOS" if is_plbl else "ENR",   # PL/BL recovery base is Total Outstanding
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall": _agg(cases),
        # FTD / MTD / LMTD / Overall cash-collected comparison for this portfolio.
        "trends": collection_windows(db, ids, overall_received=sum(_f(c.received_amount) for c in cases)),
        "product_target": product_target,
        "caller_leaderboard": caller_leaderboard,
        "by_fos": by_fos,
        "by_caller": by_caller_g,
        "by_area": _group(cases, lambda c: c.team),
        "by_team_lead": _group(cases, lambda c: c.team_lead),
        "by_cat": _group(cases, lambda c: c.cat),
        "by_dpd": _group(cases, lambda c: c.bucket),
        "leaderboard": leaderboard,
        "projection": projection,
        "trend": trend,
        "funnel": funnel,
        "untouched_table": untouched_tbl,
        "aging": aging,
        "top_pending": top_pending,
        "priority": priority,
        "obstacles": obstacles,
        "productivity": productivity,
        "field_efficiency": field_efficiency,
        "settlement": settlement,
    }


def _period_for(month_bucket: str | None) -> str | None:
    """Map a 'current' / 'next' filter to a concrete 'YYYY-MM' period (None = all months)."""
    from .cases import _current_period, _next_period
    if month_bucket == "current":
        return _current_period()
    if month_bucket == "next":
        return _next_period()
    return None


def _csv_str(v):
    return [x.strip() for x in (v or "").split(",") if x.strip()]


def _csv_int(v):
    return [int(x) for x in (v or "").split(",") if x.strip().isdigit()]


@router.get("")
def mis(bank: str = Query(...), product: str = Query(...), month_bucket: str | None = None,
        area: str | None = None, branch: str | None = None,
        cycles: str | None = None, fos_ids: str | None = None, caller_ids: str | None = None,
        paid: str | None = None,
        db: Session = Depends(get_db), user: models.User = Depends(require_roles(*MIS_ROLES))):
    if not bank or not product:
        raise HTTPException(status_code=400, detail="bank and product are required")
    out = compute_mis(db, user, bank, product, period=_period_for(month_bucket),
                      area=area or None, branch=branch or None,
                      cycles=_csv_str(cycles), fos_ids=_csv_int(fos_ids),
                      caller_ids=_csv_int(caller_ids), paid=paid or None)
    out["table_names"] = TABLE_NAMES
    out["month_bucket"] = month_bucket or "all"
    out["area"] = area or ""
    out["branch"] = branch or ""
    return out


def _activity(db, uid, is_fos, ids):
    """Field/calling activity for one person over a set of cases, straight from the logs they
    submit. FOS → visits logged + how many of those visits recorded a payment + distinct cases
    visited. Caller → calls logged + distinct cases contacted."""
    if not ids:
        return {"visits": 0, "visits_paid": 0, "visited": 0} if is_fos else {"calls": 0, "contacted": 0}
    if is_fos:
        rows = db.query(models.Visit.case_id, models.Visit.paid, models.Visit.amount_collected).filter(
            models.Visit.officer_id == uid, models.Visit.case_id.in_(ids)).all()
        visited = {r[0] for r in rows}
        paid = sum(1 for r in rows if (r[1] or (float(r[2] or 0) > 0)))
        return {"visits": len(rows), "visits_paid": paid, "visited": len(visited)}
    rows = db.query(models.CallLog.case_id).filter(
        models.CallLog.caller_id == uid, models.CallLog.case_id.in_(ids)).all()
    return {"calls": len(rows), "contacted": len({r[0] for r in rows})}


def _perf_payload(db, target: models.User, is_fos: bool, month_bucket: str | None,
                  bank_f: str | None = None, product_f: str | None = None,
                  cycles: list | None = None):
    """Per-portfolio scorecard + leaderboard for ONE person (their own, or one a manager opens).
    Honors optional bank / product / cycle filters so the dashboard re-syncs to the selection."""
    from sqlalchemy import func as _func
    id_col = models.Case.assigned_fos_id if is_fos else models.Case.assigned_caller_id
    id_attr = "assigned_fos_id" if is_fos else "assigned_caller_id"
    period = _period_for(month_bucket)

    myq = db.query(models.Case).filter(id_col == target.id, models.Case.removed.isnot(True))
    if period:
        myq = myq.filter(models.Case.period == period)
    if bank_f:
        myq = myq.filter(models.Case.bank == bank_f)
    if product_f:
        myq = myq.filter(models.Case.product == product_f)
    if cycles:
        myq = myq.filter(_func.lower(_func.trim(_func.coalesce(models.Case.cycle, ""))).in_(
            [str(c).strip().lower() for c in cycles]))
    mine = myq.all()
    user = target

    ppl = {u.id: (u.name, u.emp_code) for u in db.query(models.User).all()}
    def _lbl(uid):
        if uid in ppl:
            nm, code = ppl[uid]
            return f"{nm} ({code})" if code else (nm or "—")
        return "Unassigned"

    targets = {(t.bank, t.product): _f(t.target_pct) for t in
               db.query(models.MisTarget).filter(models.MisTarget.emp_name == "*ALL*").all()}

    # my cases grouped into portfolios (bank + product + branch)
    buckets: dict[tuple, list] = {}
    for c in mine:
        buckets.setdefault((c.bank or "—", c.product or "—", c.branch or ""), []).append(c)

    cards = []
    for (bank, product, branch), rows in buckets.items():
        a = _agg(rows)
        tgt = targets.get((bank, product), 0.0)
        tenr = round(a["enr"] * tgt / 100.0, 2)

        # the whole portfolio (same bank/product/branch/month) — to rank me against peers
        pq = db.query(models.Case).filter(models.Case.bank == bank, models.Case.product == product,
                                          models.Case.removed.isnot(True), id_col.isnot(None))
        pq = pq.filter(models.Case.branch == branch) if branch else \
             pq.filter((models.Case.branch.is_(None)) | (models.Case.branch == ""))
        if period:
            pq = pq.filter(models.Case.period == period)
        if cycles:
            pq = pq.filter(_func.lower(_func.trim(_func.coalesce(models.Case.cycle, ""))).in_(
                [str(c).strip().lower() for c in cycles]))
        byp: dict[int, list] = {}
        for c in pq.all():
            byp.setdefault(getattr(c, id_attr), []).append(c)
        lb = []
        for pid, prows in byp.items():
            pa = _agg(prows)
            lb.append({"id": pid, "name": _lbl(pid), "you": (pid == user.id),
                       "count": pa["count"], "enr": pa["enr"], "paid_enr": pa["paid_enr"],
                       "achieved_pct": pa["pct"], "collected": pa["amount"]})
        lb.sort(key=lambda x: x["paid_enr"], reverse=True)
        for i, r in enumerate(lb):
            r["rank"] = i + 1
        my_rank = next((r["rank"] for r in lb if r["you"]), None)

        cards.append({
            "bank": bank, "product": product, "branch": branch,
            "label": f"{bank} {product}" + (f" · {branch}" if branch else ""),
            "count": a["count"], "paid": a["paid"], "unpaid": a["unpaid"],
            "enr": a["enr"], "paid_enr": a["paid_enr"], "pending": a["pending"],
            "collected": a["amount"], "achieved_pct": a["pct"],
            "norm_pct": a["norm_pct"], "stab_pct": a["stab_pct"],
            "target_pct": tgt, "target_enr": tenr,
            "to_target_pct": _pct(a["paid_enr"], tenr) if tenr else 0.0,
            "gap_enr": round(max(tenr - a["paid_enr"], 0), 2),
            "rank": my_rank, "field_size": len(lb),
            "trends": collection_windows(db, [c.id for c in rows], overall_received=a["amount"]),
            "activity": _activity(db, user.id, is_fos, [c.id for c in rows]),
            "leaderboard": lb,
        })
    cards.sort(key=lambda x: x["enr"], reverse=True)

    tot = _agg(mine)
    return {
        "month_bucket": month_bucket or "all",
        "as_fos": is_fos,
        "name": target.name, "emp_code": target.emp_code, "user_id": target.id,
        "totals": {"count": tot["count"], "paid": tot["paid"], "unpaid": tot["unpaid"],
                   "enr": tot["enr"], "paid_enr": tot["paid_enr"], "pending": tot["pending"],
                   "collected": tot["amount"], "achieved_pct": tot["pct"]},
        "activity": _activity(db, target.id, is_fos, [c.id for c in mine]),
        "trends": collection_windows(db, [c.id for c in mine], overall_received=tot["amount"]),
        "portfolios": cards,
    }


@router.get("/my-performance")
def my_performance(month_bucket: str | None = "current",
                   bank: str | None = None, product: str | None = None, cycles: str | None = None,
                   db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)):
    """The signed-in caller's/FOS's OWN scorecard — per-portfolio achievement + leaderboard rank,
    each portfolio kept separate per month. Honors optional bank / product / cycle filters."""
    return _perf_payload(db, user, (user.role == "fos"), month_bucket,
                         bank_f=bank or None, product_f=product or None, cycles=_csv_str(cycles))


@router.get("/performance")
def performance(emp_id: int, role: str | None = None, month_bucket: str | None = "current",
                bank: str | None = None, product: str | None = None, cycles: str | None = None,
                db: Session = Depends(get_db),
                actor: models.User = Depends(get_current_user)):
    """Any FOS/caller's performance screen — opened by clicking their name on a case, MIS row, or
    leaderboard. `role` = 'fos' or 'caller' picks which hat to score; defaults to the person's own
    role. Viewable by the person themselves or by managers / HO / admin / team leads / HR / back-office."""
    if actor.id != emp_id and actor.role not in ("admin", "manager", "headoffice", "teamlead", "hr", "backend"):
        raise HTTPException(status_code=403, detail="Not allowed")
    target = db.query(models.User).filter(models.User.id == emp_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    is_fos = (role == "fos") if role in ("fos", "caller") else (target.role == "fos")
    return _perf_payload(db, target, is_fos, month_bucket,
                         bank_f=bank or None, product_f=product or None, cycles=_csv_str(cycles))


@router.get("/employee-trends")
def employee_trends(user_id: int, db: Session = Depends(get_db),
                    actor: models.User = Depends(get_current_user)):
    """One person's achievement across FTD / MTD / LMTD / Overall — powers the trend strip on a
    FOS/caller's own profile and on the profile card managers / HO / admin / team leads open."""
    from sqlalchemy import or_, func
    # A person may view their own; managers / HO / admin / team leads / HR / back-office view others.
    if actor.id != user_id and actor.role not in ("admin", "manager", "headoffice", "teamlead", "hr", "backend"):
        raise HTTPException(status_code=403, detail="Not allowed")
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    own = or_(models.Case.assigned_fos_id == user_id, models.Case.assigned_caller_id == user_id)
    ids = [r[0] for r in db.query(models.Case.id)
           .filter(models.Case.removed.isnot(True), own).all()]
    overall = db.query(func.coalesce(func.sum(models.Case.received_amount), 0)) \
        .filter(models.Case.removed.isnot(True), own).scalar()
    return {
        "user_id": user_id,
        "name": target.name,
        "emp_code": target.emp_code,
        "cases": len(ids),
        "trends": collection_windows(db, ids, overall_received=float(overall or 0)),
    }


def _cycle_key(cyc: str):
    """Sort cycles numerically when they're numbers (1,2,5,10…), else alphabetically."""
    s = str(cyc or "").strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    return (0, int(digits)) if digits else (1, s.upper())


@router.get("/by-cycle")
def mis_by_cycle(month_bucket: str | None = "current",
                 db: Session = Depends(get_db),
                 user: models.User = Depends(require_roles(*MIS_ROLES, "fos", "telecaller"))):
    """Cycle-wise MIS — every portfolio broken down by its billing CYCLE, with the same
    ENR-based analytics per cycle. Scoped by role: MIS/managers/head office/back-office/team
    leads see all their cases; a FOS or caller sees ONLY their own (via _scope). This powers
    the 'Cycle-wise MIS' view for managers and the cycle breakdown on a caller/FOS scorecard."""
    period = _period_for(month_bucket)
    q = _scope(db.query(models.Case), user)
    if period:
        q = q.filter(models.Case.period == period)
    cases = q.all()

    targets = {(t.bank, t.product): _f(t.target_pct) for t in
               db.query(models.MisTarget).filter(models.MisTarget.emp_name == "*ALL*").all()}

    # portfolio (bank+product+branch) -> cycle -> [cases]
    portfolios: dict[tuple, dict] = {}
    for c in cases:
        pkey = (c.bank or "—", c.product or "—", c.branch or "")
        portfolios.setdefault(pkey, {}).setdefault((c.cycle or "—"), []).append(c)

    out = []
    for (bank, product, branch), cyc_map in portfolios.items():
        tgt = targets.get((bank, product), 0.0)
        cycles = []
        for cyc, rows in cyc_map.items():
            a = _agg(rows)
            tenr = round(a["enr"] * tgt / 100.0, 2)
            cycles.append({
                "cycle": cyc, "count": a["count"], "paid": a["paid"], "unpaid": a["unpaid"],
                "enr": a["enr"], "paid_enr": a["paid_enr"], "pct": a["pct"],
                "norm_pct": a["norm_pct"], "stab_pct": a["stab_pct"],
                "collected": a["amount"], "pending": a["pending"],
                "not_visited": a["not_visited"],
                "target_pct": tgt, "target_enr": tenr,
                "to_target_pct": _pct(a["paid_enr"], tenr) if tenr else 0.0,
            })
        cycles.sort(key=lambda x: _cycle_key(x["cycle"]))
        tot = _agg([c for rows in cyc_map.values() for c in rows])
        out.append({
            "bank": bank, "product": product, "branch": branch,
            "label": f"{bank} {product}" + (f" · {branch}" if branch else ""),
            "cycles": cycles,
            "totals": {"count": tot["count"], "enr": tot["enr"], "paid_enr": tot["paid_enr"],
                       "pct": tot["pct"], "collected": tot["amount"], "pending": tot["pending"]},
        })
    out.sort(key=lambda x: x["label"])
    return {"month_bucket": month_bucket or "all", "portfolios": out}


@router.put("/target")
def set_target(body: dict = Body(...), db: Session = Depends(get_db),
               user: models.User = Depends(require_roles("admin", "manager", "backend", "headoffice"))):
    """Set the ONE product-wide target % (applies to every FOS and caller for this
    bank+product). Set it to 85 and everyone's target becomes 85."""
    bank = (body.get("bank") or "").strip()
    product = (body.get("product") or "").strip()
    try:
        pct = float(body.get("target_pct") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="target_pct must be a number")
    if not (bank and product):
        raise HTTPException(status_code=400, detail="bank and product are required")
    row = (db.query(models.MisTarget)
           .filter(models.MisTarget.bank == bank, models.MisTarget.product == product,
                   models.MisTarget.emp_name == "*ALL*").first())
    if not row:
        row = models.MisTarget(bank=bank, product=product, emp_name="*ALL*")
        db.add(row)
    row.target_pct = pct
    db.commit()
    return {"ok": True, "target_pct": pct}


# ---- Download selected MIS tables as an Excel workbook ----
_GROUP = [("label", "NAME"), ("count", "COUNT"), ("paid", "PAID"), ("unpaid", "UNPAID"),
          ("enr", "ENR"), ("paid_enr", "PAID ENR"), ("pct", "PAID %"),
          ("norm_pct", "NORM %"), ("stab_pct", "STAB %"), ("rollback_pct", "ROLLBACK %"),
          ("rollback_collected", "ROLLBACK COLL"),
          ("amount", "CASH COLL"), ("visited", "VISITED"), ("not_visited", "NOT VISITED")]
_AREA = [("label", "AREA"), ("count", "COUNT"), ("paid", "PAID"), ("unpaid", "UNPAID"),
         ("enr", "ENR"), ("pending", "PENDING"), ("amount", "COLLECTED"), ("recovery_pct", "RECOVERY %"),
         ("pct", "PAID %"), ("norm_pct", "NORM %"), ("stab_pct", "STAB %")]
_CASELIST = [("customer", "Customer"), ("account", "Account"), ("pending", "Pending"),
             ("enr", "ENR"), ("propensity", "Score"), ("fos", "FOS"), ("caller", "Caller"), ("contacted", "Contacted")]
_TABLE_COLS = {
    "by_fos": _GROUP, "by_caller": _GROUP, "by_area": _AREA, "by_team_lead": _GROUP,
    "by_cat": _GROUP, "by_dpd": _GROUP,
    "leaderboard": [("emp", "EMP NAME"), ("count", "COUNT"), ("unpaid", "UNPAID"), ("paid", "PAID"),
                    ("enr", "ENR"), ("target_pct", "TARGET %"), ("target_enr", "TARGET ENR"),
                    ("achieved_pct", "ACHIEVED %"), ("achieved_enr", "ACHIEVED ENR"),
                    ("gap_enr", "GAP ENR"), ("to_target_pct", "TO TARGET %"), ("status", "STATUS"),
                    ("pending_visit", "PENDING VISIT"), ("cash_coll", "CASH COLL")],
    "aging": [("label", "Recency"), ("count", "Count"), ("pending", "Pending")],
    "untouched_table": _CASELIST, "top_pending": _CASELIST, "priority": _CASELIST,
    "obstacles": [("caller", "Caller"), ("total", "Total"), ("obstacles", "Obstacles"), ("rate_pct", "Rate %")],
    "productivity": [("emp", "Employee"), ("calls_today", "Calls today"), ("visits_today", "Visits today"), ("idle", "Idle")],
    "field_efficiency": [("fos", "FOS"), ("visits", "Visits"), ("distance_km", "Distance km"), ("off_location", "Off-location"), ("collected", "Collected")],
    "trend": [("date", "Date"), ("collected", "Collected")],
}
_KV = {"projection", "funnel", "settlement", "overall"}   # dict blocks -> key/value sheet

# Human table names (also used to build the on-screen index)
TABLE_NAMES = {
    "overall": "Overall summary", "leaderboard": "Employee performance & leaderboard",
    "by_fos": "FOS-wise", "by_caller": "Caller-wise", "by_area": "Area-wise recovery (pending · collected · %)",
    "by_team_lead": "Team-lead wise", "by_cat": "Category-wise", "by_dpd": "Bucket (DPD) recovery",
    "projection": "Month-end projection", "trend": "Collection trend (30d)",
    "funnel": "Conversion & PTP funnel", "untouched_table": "Untouched high-value cases",
    "aging": "Contact aging", "top_pending": "Top pending cases", "priority": "Propensity worklist",
    "obstacles": "Obstacle rates", "productivity": "Productivity (today)",
    "field_efficiency": "FOS field efficiency", "settlement": "Settlement leakage & realization",
}


@router.get("/download")
def download(bank: str = Query(...), product: str = Query(...),
             tables: str = Query(",".join(TABLE_NAMES.keys())), month_bucket: str | None = None,
             area: str | None = None, branch: str | None = None,
             cycles: str | None = None, fos_ids: str | None = None, caller_ids: str | None = None,
             paid: str | None = None,
             db: Session = Depends(get_db), user: models.User = Depends(require_roles(*MIS_ROLES))):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    HEAD = PatternFill("solid", fgColor="1D4ED8")
    HEADF = Font(bold=True, color="FFFFFF", size=11)
    ZEBRA = PatternFill("solid", fgColor="F5F8FE")
    GREEN = PatternFill("solid", fgColor="C6EFCE")
    AMBER = PatternFill("solid", fgColor="FFEB9C")
    RED = PatternFill("solid", fgColor="FFC7CE")
    _s = Side(style="thin", color="D6DEEA")
    THIN = Border(left=_s, right=_s, top=_s, bottom=_s)

    def _style(ws, first_col_bold=False):
        header = [str(c.value) if c.value is not None else "" for c in ws[1]]
        pct_idx = [i for i, h in enumerate(header) if "%" in h]
        for cell in ws[1]:
            cell.fill = HEAD; cell.font = HEADF
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = THIN
        ws.freeze_panes = "A2"
        for ri, row in enumerate(ws.iter_rows(min_row=2), start=2):
            for cell in row:
                cell.border = THIN
                if ri % 2 == 0:
                    cell.fill = ZEBRA
            if first_col_bold and row:
                row[0].font = Font(bold=True)
            for i in pct_idx:
                if i < len(row):
                    try:
                        v = float(row[i].value)
                    except (TypeError, ValueError):
                        continue
                    row[i].fill = GREEN if v >= 60 else AMBER if v >= 30 else RED
                    row[i].font = Font(bold=True)
        for col in ws.columns:
            w = max((len(str(c.value)) for c in col if c.value is not None), default=10)
            ws.column_dimensions[col[0].column_letter].width = min(max(w + 2, 12), 42)

    data = compute_mis(db, user, bank, product, period=_period_for(month_bucket),
                       area=area or None, branch=branch or None,
                       cycles=_csv_str(cycles), fos_ids=_csv_int(fos_ids),
                       caller_ids=_csv_int(caller_ids), paid=paid or None)
    wanted = [t.strip() for t in tables.split(",") if t.strip()]
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name in wanted:
        block = data.get(name)
        ws = wb.create_sheet(title=name[:31])
        if name in _KV and isinstance(block, dict):
            ws.append(["Metric", "Value"])
            for k, v in block.items():
                ws.append([k, v])
            _style(ws, first_col_bold=True)
        elif isinstance(block, list) and name in _TABLE_COLS:
            cols = _TABLE_COLS[name]
            ws.append([c[1] for c in cols])
            for r in block:
                ws.append([r.get(k) for k, _ in cols])
            _style(ws, first_col_bold=True)
    if not wb.sheetnames:
        wb.create_sheet(title="MIS")
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"MIS_{bank}_{product}.xlsx".replace(" ", "_").replace("/", "-")
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/highlights")
def highlights(db: Session = Depends(get_db), user: models.User = Depends(require_roles("admin", "manager", "headoffice"))):
    """A few headline MIS signals across everything the user can see — for the main dashboard."""
    cases = _scope(db.query(models.Case), user).all()
    today = datetime.now(IST).date()

    total_enr = sum(_f(c.enr) for c in cases)
    paid_enr = sum(_f(c.enr) for c in cases if _is_paid(c))
    collected = sum(_f(c.received_amount) for c in cases)
    norm_target = sum(_f(c.norm_amount) for c in cases)
    untouched = [c for c in cases if not c.last_contacted_at and not c.visited]
    ptp_broken = sum(1 for c in cases if (c.disposition or "").upper() == "PTP"
                     and not _is_paid(c) and c.follow_up_date and c.follow_up_date < today)

    # Target gap per (bank, product, FOS) using manager-entered targets.
    grp: dict[tuple, dict] = {}
    for c in cases:
        g = grp.setdefault((c.bank, c.product, c.fos_name), {"enr": 0.0, "paid": 0.0})
        g["enr"] += _f(c.enr)
        if _is_paid(c):
            g["paid"] += _f(c.enr)
    target_gap = 0.0
    behind = []
    emps_behind = emps_total = 0
    for t in db.query(models.MisTarget).all():
        g = grp.get((t.bank, t.product, t.emp_name))
        if not g:
            continue
        emps_total += 1
        tenr = g["enr"] * _f(t.target_pct) / 100.0
        gap = max(tenr - g["paid"], 0.0)
        target_gap += gap
        if gap > 0:
            emps_behind += 1
        behind.append({"emp": t.emp_name, "product": f"{t.bank} · {t.product}",
                       "gap_enr": round(gap, 2), "to_target_pct": _pct(g["paid"], tenr)})
    behind.sort(key=lambda x: x["gap_enr"], reverse=True)

    _ppl2 = {u.id: (u.name, u.emp_code) for u in db.query(models.User).all()}
    def _fos_lbl(c):
        if c.assigned_fos_id and c.assigned_fos_id in _ppl2:
            nm, code = _ppl2[c.assigned_fos_id]
            return f"{nm} ({code})" if code else (nm or "Unassigned")
        return "Unassigned"
    top_untouched = [{"customer": c.customer_name, "account": c.account_no,
                      "product": f"{c.bank or '—'} · {c.product or '—'}", "fos": _fos_lbl(c),
                      "pending": _f(c.pending_amount)}
                     for c in sorted(untouched, key=lambda x: _f(x.pending_amount), reverse=True)[:8]]

    return {
        "total_enr": round(total_enr, 2), "paid_enr": round(paid_enr, 2),
        "achieved_pct": _pct(paid_enr, total_enr), "collected": round(collected, 2),
        "realization_pct": _pct(collected, norm_target),
        "untouched": len(untouched), "untouched_pending": round(sum(_f(c.pending_amount) for c in untouched), 2),
        "ptp_broken": ptp_broken,
        "target_gap": round(target_gap, 2), "employees_behind": emps_behind, "employees_total": emps_total,
        "behind_targets": behind[:8], "top_untouched": top_untouched,
    }


@router.get("/overview")
def overview(db: Session = Depends(get_db), user: models.User = Depends(require_roles(*MIS_ROLES))):
    """Cross-product / cross-bank recovery comparison (ENR-based)."""
    cases = _scope(db.query(models.Case), user).all()

    def summarise(keyfn):
        g: dict[str, dict] = {}
        for c in cases:
            k = keyfn(c) or "—"
            d = g.setdefault(k, {"label": k, "count": 0, "enr": 0.0, "paid_enr": 0.0, "collected": 0.0, "pending": 0.0})
            d["count"] += 1
            d["enr"] += _f(c.enr)
            if _is_paid(c):
                d["paid_enr"] += _f(c.enr)
            d["collected"] += _f(c.received_amount)
            d["pending"] += _f(c.pending_amount)
        out = [{**d, "pct": _pct(d["paid_enr"], d["enr"]),
                "enr": round(d["enr"], 2), "paid_enr": round(d["paid_enr"], 2),
                "collected": round(d["collected"], 2), "pending": round(d["pending"], 2)} for d in g.values()]
        out.sort(key=lambda x: x["pct"], reverse=True)
        return out

    return {"by_product": summarise(lambda c: (c.bank or "—") + " · " + (c.product or "—")),
            "by_bank": summarise(lambda c: c.bank)}
