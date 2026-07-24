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

MIS_ROLES = ("admin", "manager", "backend")


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
        "amount": round(sum(_f(c.received_amount) for c in rows), 2),   # CASH COLL
        "visited": sum(1 for c in rows if c.visited),
        "not_visited": sum(1 for c in rows if not c.visited),
    }


def _group(cases: list, keyfn) -> list:
    buckets: dict[str, list] = {}
    for c in cases:
        k = keyfn(c) or "—"
        buckets.setdefault(k, []).append(c)
    out = [{"label": k, **_agg(v)} for k, v in buckets.items()]
    out.sort(key=lambda r: r["enr"], reverse=True)
    return out


def compute_mis(db: Session, user: models.User, bank: str, product: str) -> dict:
    q = _scope(db.query(models.Case), user).filter(models.Case.bank == bank, models.Case.product == product)
    cases = q.all()

    targets = {t.emp_name: _f(t.target_pct) for t in
               db.query(models.MisTarget).filter(models.MisTarget.bank == bank,
                                                 models.MisTarget.product == product).all()}

    by_fos = _group(cases, lambda c: c.fos_name)
    # Leaderboard / employee performance (FOS-based) with attainment gap + RAG status.
    leaderboard = []
    for r in by_fos:
        tgt = targets.get(r["label"], 0.0)
        tenr = round(r["enr"] * tgt / 100.0, 2)
        to_tgt = _pct(r["paid_enr"], tenr) if tenr else 0.0
        leaderboard.append({
            "emp": r["label"], "count": r["count"], "unpaid": r["unpaid"], "paid": r["paid"],
            "enr": r["enr"], "target_pct": tgt, "target_enr": tenr,
            "achieved_pct": r["pct"], "achieved_enr": r["paid_enr"],
            "gap_enr": round(max(tenr - r["paid_enr"], 0), 2), "to_target_pct": to_tgt,
            "status": ("none" if not tenr else "green" if to_tgt >= 100 else "amber" if to_tgt >= 60 else "red"),
            "pending_visit": r["not_visited"], "cash_coll": r["amount"],
        })
    leaderboard.sort(key=lambda x: x["achieved_enr"], reverse=True)

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
    ptp_cases = [c for c in cases if (c.disposition or "").upper() in ("PTP", "RTP")]
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

    def case_row(c):
        return {"customer": c.customer_name, "account": c.account_no, "pending": _f(c.pending_amount),
                "enr": _f(c.enr), "propensity": c.propensity or 0, "fos": c.fos_name, "caller": c.caller_name,
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
        k = c.caller_name or "—"
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
    settlement = {
        "collected": round(collected_all, 2),
        "norm_target": round(norm_target_total, 2),
        "realization_pct": _pct(collected_all, norm_target_total),
        "stab_enr": round(stab_enr, 2), "norm_enr": round(norm_enr, 2),
        "stab_share_pct": _pct(stab_enr, stab_enr + norm_enr),
        "norm_share_pct": _pct(norm_enr, stab_enr + norm_enr),
        "leakage": round(sum(max(_f(c.norm_amount) - _f(c.received_amount), 0) for c in stab_paid), 2),
    }

    return {
        "bank": bank, "product": product,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall": _agg(cases),
        "by_fos": by_fos,
        "by_caller": _group(cases, lambda c: c.caller_name),
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


@router.get("")
def mis(bank: str = Query(...), product: str = Query(...),
        db: Session = Depends(get_db), user: models.User = Depends(require_roles(*MIS_ROLES))):
    if not bank or not product:
        raise HTTPException(status_code=400, detail="bank and product are required")
    out = compute_mis(db, user, bank, product)
    out["table_names"] = TABLE_NAMES
    return out


@router.put("/target")
def set_target(body: dict = Body(...), db: Session = Depends(get_db),
               user: models.User = Depends(require_roles("admin", "manager"))):
    bank = (body.get("bank") or "").strip()
    product = (body.get("product") or "").strip()
    emp = (body.get("emp") or "").strip()
    try:
        pct = float(body.get("target_pct") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="target_pct must be a number")
    if not (bank and product and emp):
        raise HTTPException(status_code=400, detail="bank, product and emp are required")
    row = (db.query(models.MisTarget)
           .filter(models.MisTarget.bank == bank, models.MisTarget.product == product,
                   models.MisTarget.emp_name == emp).first())
    if not row:
        row = models.MisTarget(bank=bank, product=product, emp_name=emp)
        db.add(row)
    row.target_pct = pct
    db.commit()
    return {"ok": True, "emp": emp, "target_pct": pct}


# ---- Download selected MIS tables as an Excel workbook ----
_GROUP = [("label", "NAME"), ("count", "COUNT"), ("paid", "PAID"), ("unpaid", "UNPAID"),
          ("enr", "ENR"), ("paid_enr", "PAID ENR"), ("pct", "PAID %"),
          ("norm_pct", "NORM %"), ("stab_pct", "STAB %"),
          ("amount", "CASH COLL"), ("visited", "VISITED"), ("not_visited", "NOT VISITED")]
_CASELIST = [("customer", "Customer"), ("account", "Account"), ("pending", "Pending"),
             ("enr", "ENR"), ("propensity", "Score"), ("fos", "FOS"), ("caller", "Caller"), ("contacted", "Contacted")]
_TABLE_COLS = {
    "by_fos": _GROUP, "by_caller": _GROUP, "by_area": _GROUP, "by_team_lead": _GROUP,
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
    "by_fos": "FOS-wise", "by_caller": "Caller-wise", "by_area": "Area-wise (NORM/STAB)",
    "by_team_lead": "Team-lead wise", "by_cat": "Category-wise", "by_dpd": "Bucket (DPD) recovery",
    "projection": "Month-end projection", "trend": "Collection trend (30d)",
    "funnel": "Conversion & PTP funnel", "untouched_table": "Untouched high-value cases",
    "aging": "Contact aging", "top_pending": "Top pending cases", "priority": "Propensity worklist",
    "obstacles": "Obstacle rates", "productivity": "Productivity (today)",
    "field_efficiency": "FOS field efficiency", "settlement": "Settlement leakage & realization",
}


@router.get("/download")
def download(bank: str = Query(...), product: str = Query(...),
             tables: str = Query(",".join(TABLE_NAMES.keys())),
             db: Session = Depends(get_db), user: models.User = Depends(require_roles(*MIS_ROLES))):
    import openpyxl
    data = compute_mis(db, user, bank, product)
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
        elif isinstance(block, list) and name in _TABLE_COLS:
            cols = _TABLE_COLS[name]
            ws.append([c[1] for c in cols])
            for r in block:
                ws.append([r.get(k) for k, _ in cols])
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
def highlights(db: Session = Depends(get_db), user: models.User = Depends(require_roles("admin", "manager"))):
    """A few headline MIS signals across everything the user can see — for the main dashboard."""
    cases = _scope(db.query(models.Case), user).all()
    today = datetime.now(IST).date()

    total_enr = sum(_f(c.enr) for c in cases)
    paid_enr = sum(_f(c.enr) for c in cases if _is_paid(c))
    collected = sum(_f(c.received_amount) for c in cases)
    norm_target = sum(_f(c.norm_amount) for c in cases)
    untouched = [c for c in cases if not c.last_contacted_at and not c.visited]
    ptp_broken = sum(1 for c in cases if (c.disposition or "").upper() in ("PTP", "RTP")
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

    top_untouched = [{"customer": c.customer_name, "account": c.account_no,
                      "product": f"{c.bank or '—'} · {c.product or '—'}", "fos": c.fos_name,
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
