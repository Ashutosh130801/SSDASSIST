"""🧠 Smart allocation & route plan add-on.

• Score: likelihood-to-pay 0–100 with the reasons shown (built on the existing propensity score plus the
  case's own call / PTP / payment history) and the best hour to call (hours when this customer — or, if no
  history, customers of the same bank — actually answered with PTP / payment / callback).
• Allocation suggestions: FOS by distance from their base (last GPS ping, else the centre of their current
  cases) within capacity; callers by load. The user reviews, then applies (uses the normal bulk-reassign,
  so scope, audit and notifications are the same as manual allocation).
• Route plan: today's visit order for a FOS — PTP-due first, then highest score, then nearest-next.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from .. import services as svc
from ..addons_common import IST, D, LEADS, need, now_ist, outstanding, scoped_cases
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/api/smart", tags=["smart"])
KEY = "smart_allocation"
GOOD = ("PTP", "PAID", "PAYMENT", "CALLBACK", "CB", "BPTP")


def km(a, b):
    (la1, lo1), (la2, lo2) = a, b
    p = math.pi / 180
    h = 0.5 - math.cos((la2 - la1) * p) / 2 + math.cos(la1 * p) * math.cos(la2 * p) * (1 - math.cos((lo2 - lo1) * p)) / 2
    return 12742 * math.asin(math.sqrt(max(h, 0)))


def _history(db, ids):
    out = defaultdict(list)
    if not ids:
        return out
    for i in range(0, len(ids), 800):
        for cid, disp, amt, pd, at in db.query(models.CallLog.case_id, models.CallLog.disposition, models.CallLog.ptp_amount,
                                               models.CallLog.ptp_date, models.CallLog.created_at) \
                .filter(models.CallLog.case_id.in_(ids[i:i + 800])).all():
            out[cid].append(((disp or "").upper(), D(amt), pd, at))
    return out


def score_case(c, hist) -> tuple[int, list[str]]:
    from .cases import propensity
    s = propensity(c)
    why = []
    ptps = [h for h in hist if h[0] in ("PTP", "BPTP")]
    pays = [h for h in hist if h[0] in ("PAID", "PAYMENT") and h[1] > 0]
    tries = [h for h in hist if h[0] not in ("PAID", "PAYMENT")]
    if pays:
        s += 8; why.append(f"paid {len(pays)}× before")
    if ptps:
        kept = 0
        for p in ptps:
            if p[2] and any(q[3] and q[3] >= p[3] for q in pays):
                kept += 1
        if kept:
            s += 10; why.append(f"kept {kept} of {len(ptps)} promises")
        elif len(ptps) >= 2:
            s -= 10; why.append(f"{len(ptps)} promises, none kept")
    if len(tries) >= 6 and not ptps and not pays:
        s -= 10; why.append(f"{len(tries)} attempts, no promise yet")
    if "PTP" in (c.disposition or "").upper():
        why.append("open promise")
    if (c.paid_status or "") == "PARTIAL":
        why.append("part paid")
    if any(x in (c.disposition or "").upper() for x in ("RTP", "WRONG", "SWITCH", "DISPUTE")):
        why.append(f"last outcome {c.disposition}")
    return max(1, min(99, int(s))), why


def best_hours(db, cases, hist):
    """Customer's own good-contact hours; fallback: same bank's good-contact hours."""
    bank_hours = defaultdict(Counter)
    banks = {c.bank for c in cases}
    since = datetime.now(timezone.utc) - timedelta(days=90)
    for bank, at in db.query(models.Case.bank, models.CallLog.created_at).join(models.CallLog, models.CallLog.case_id == models.Case.id) \
            .filter(models.Case.bank.in_(banks or {""}), models.CallLog.created_at >= since,
                    func.upper(models.CallLog.disposition).in_(GOOD)).limit(50000).all():
        if at:
            bank_hours[bank][(at if at.tzinfo else at.replace(tzinfo=timezone.utc)).astimezone(IST).hour] += 1
    out = {}
    for c in cases:
        own = Counter((h[3] if h[3].tzinfo else h[3].replace(tzinfo=timezone.utc)).astimezone(IST).hour
                      for h in hist.get(c.id, []) if h[3] and h[0] in GOOD)
        src = own or bank_hours.get(c.bank) or Counter()
        if src:
            hr = src.most_common(1)[0][0]
            out[c.id] = f"{hr:02d}:00–{hr + 1:02d}:00" + ("" if own else " (bank pattern)")
    return out


@router.get("/scores")
def scores(bank: str = "", product: str = "", limit: int = 200, db: Session = Depends(get_db), user=Depends(get_current_user)):
    q = scoped_cases(db, user).filter(func.upper(func.coalesce(models.Case.paid_status, "UNPAID")) != "PAID")
    if bank:
        q = q.filter(models.Case.bank == bank)
    if product:
        q = q.filter(models.Case.product == product)
    cases = q.limit(5000).all()
    hist = _history(db, [c.id for c in cases])
    hrs = best_hours(db, cases, hist)
    rows = []
    for c in cases:
        sc, why = score_case(c, hist.get(c.id, []))
        rows.append({"case_id": c.id, "customer": c.customer_name, "bank": c.bank, "product": c.product, "bucket": c.bucket,
                     "pending": float(outstanding(c)), "score": sc, "why": why, "best_time": hrs.get(c.id), "disposition": c.disposition})
    rows.sort(key=lambda r: (-r["score"], -r["pending"]))
    band = Counter("high" if r["score"] >= 70 else "medium" if r["score"] >= 45 else "low" for r in rows)
    return {"bands": dict(band), "rows": rows[:max(1, min(limit, 2000))], "total": len(rows)}


def _fos_bases(db, fos_ids):
    bases = {}
    since = datetime.now(timezone.utc) - timedelta(days=7)
    for uid in fos_ids:
        p = db.query(models.LocationPing).filter(models.LocationPing.officer_id == uid, models.LocationPing.created_at >= since) \
            .order_by(models.LocationPing.created_at.desc()).first()
        if p:
            bases[uid] = ((p.latitude, p.longitude), "last GPS")
            continue
        pts = db.query(models.Case.latitude, models.Case.longitude).filter(models.Case.assigned_fos_id == uid,
                                                                           models.Case.latitude.isnot(None)).limit(500).all()
        if pts:
            bases[uid] = ((sum(a for a, _ in pts) / len(pts), sum(b for _, b in pts) / len(pts)), "centre of his cases")
    return bases


@router.post("/allocate/preview")
def allocate_preview(body: dict = Body(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, LEADS, "smart allocation")
    kind = body.get("kind") or "fos"
    if kind not in ("fos", "caller"):
        raise HTTPException(400, "kind must be fos or caller")
    c = svc.settings_of(db, KEY)
    q = scoped_cases(db, user).filter(func.upper(func.coalesce(models.Case.paid_status, "UNPAID")) != "PAID")
    if body.get("bank"):
        q = q.filter(models.Case.bank == body["bank"])
    if body.get("product"):
        q = q.filter(models.Case.product == body["product"])
    col = models.Case.assigned_fos_id if kind == "fos" else models.Case.assigned_caller_id
    if body.get("only_unallocated", True):
        q = q.filter(col.is_(None))
    cases = q.filter(models.Case.escalated.isnot(True)).limit(3000).all()
    role = "fos" if kind == "fos" else "telecaller"
    staff_q = db.query(models.User).filter(models.User.role == role, models.User.is_active.is_(True))
    if user.role == "manager":
        staff_q = staff_q.filter(models.User.branch == user.branch)
    elif user.role == "teamlead":
        from ..ai_tools import visible_staff
        ids = visible_staff(db, user)
        staff_q = staff_q.filter(models.User.id.in_(ids or [-1]))
    if body.get("branch"):
        staff_q = staff_q.filter(func.upper(models.User.branch) == str(body["branch"]).upper())
    staff = staff_q.all()
    if not staff:
        raise HTTPException(400, f"No active {'FOS' if kind == 'fos' else 'callers'} in your scope")
    cap = int(c.get("fos_capacity" if kind == "fos" else "caller_capacity") or 0) or 10 ** 6
    load = dict(db.query(col, func.count()).filter(col.in_([s.id for s in staff]), models.Case.removed.isnot(True),
                                                    func.upper(func.coalesce(models.Case.paid_status, "UNPAID")) != "PAID")
                .group_by(col).all())
    hist = _history(db, [x.id for x in cases])
    cases.sort(key=lambda x: -score_case(x, hist.get(x.id, []))[0])
    bases = _fos_bases(db, [s.id for s in staff]) if kind == "fos" else {}
    out, skipped = [], 0
    for case in cases:
        free = [s for s in staff if load.get(s.id, 0) < cap]
        if not free:
            skipped += 1
            continue
        pick, why = None, ""
        if kind == "fos" and case.latitude is not None:
            near = [(km((case.latitude, case.longitude), bases[s.id][0]), s) for s in free if s.id in bases]
            if near:
                d, pick = min(near, key=lambda t: t[0])
                why = f"{d:.1f} km from {bases[pick.id][1]}"
        if not pick and kind == "fos" and case.branch:
            same = [s for s in free if (s.branch or "").upper() == (case.branch or "").upper()]
            if same:
                pick = min(same, key=lambda s: load.get(s.id, 0)); why = "same branch, lightest load"
        if not pick:
            pick = min(free, key=lambda s: load.get(s.id, 0)); why = "lightest load"
        load[pick.id] = load.get(pick.id, 0) + 1
        out.append({"case_id": case.id, "customer": case.customer_name, "pending": float(outstanding(case)),
                    "user_id": pick.id, "user": pick.name, "why": why})
    per = Counter(r["user"] for r in out)
    return {"kind": kind, "suggestions": out, "skipped_full": skipped, "per_user": dict(per), "capacity": None if cap == 10 ** 6 else cap}


@router.post("/allocate/apply")
def allocate_apply(body: dict = Body(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, LEADS, "smart allocation")
    kind = body.get("kind") or "fos"
    groups = defaultdict(list)
    for it in body.get("items") or []:
        groups[int(it["user_id"])].append(int(it["case_id"]))
    from .cases import BulkReassign, bulk_reassign
    n = 0
    for uid, ids in groups.items():
        u = db.get(models.User, uid)
        if not u or u.role != ("fos" if kind == "fos" else "telecaller"):
            raise HTTPException(400, f"User #{uid} is not a {'FOS' if kind == 'fos' else 'caller'}")
        args = {"case_ids": ids, ("assigned_fos_id" if kind == "fos" else "assigned_caller_id"): uid}
        r = bulk_reassign(BulkReassign(**args), db, user)
        n += (r or {}).get("updated", len(ids)) if isinstance(r, dict) else len(ids)
    return {"applied": n}


@router.get("/route")
def route(fos_id: int | None = None, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Ordered visit plan for today (FOS: own; leads: any FOS in scope)."""
    if user.role == "fos":
        fos_id = user.id
    else:
        need(user, LEADS, "route plans")
        if not fos_id:
            raise HTTPException(400, "Pick a FOS")
    fos = db.get(models.User, fos_id)
    if not fos:
        raise HTTPException(404, "FOS not found")
    stops = int(svc.settings_of(db, KEY).get("route_stops") or 15)
    q = scoped_cases(db, user).filter(models.Case.assigned_fos_id == fos_id, models.Case.latitude.isnot(None),
                                      func.upper(func.coalesce(models.Case.paid_status, "UNPAID")) != "PAID",
                                      models.Case.escalated.isnot(True))
    cases = q.limit(2000).all()
    if not cases:
        return {"fos": fos.name, "stops": [], "km": 0, "maps_url": None}
    hist = _history(db, [c.id for c in cases])
    today = now_ist().date()
    def pri(c):
        sc = score_case(c, hist.get(c.id, []))[0]
        due = any(h[0] in ("PTP", "BPTP") and h[2] and (h[2].astimezone(IST).date() if h[2].tzinfo else h[2].date()) <= today
                  for h in hist.get(c.id, []))
        return (1 if due else 0, sc, float(outstanding(c)))
    ranked = sorted(cases, key=pri, reverse=True)[:stops]
    base = _fos_bases(db, [fos_id]).get(fos_id)
    cur = base[0] if base else (ranked[0].latitude, ranked[0].longitude)
    order, left, total = [], list(ranked), 0.0
    while left:
        nxt = min(left, key=lambda c: km(cur, (c.latitude, c.longitude)))
        d = km(cur, (nxt.latitude, nxt.longitude)); total += d
        p = pri(nxt)
        order.append({"case_id": nxt.id, "customer": nxt.customer_name, "address": nxt.address_clean or nxt.address,
                      "lat": nxt.latitude, "lng": nxt.longitude, "km_from_prev": round(d, 1), "ptp_due": bool(p[0]),
                      "score": p[1], "pending": p[2]})
        cur = (nxt.latitude, nxt.longitude); left.remove(nxt)
    pts = [f"{s['lat']},{s['lng']}" for s in order]
    url = ("https://www.google.com/maps/dir/" + "/".join(([f"{base[0][0]},{base[0][1]}"] if base else []) + pts[:24])) if pts else None
    return {"fos": fos.name, "start": base[1] if base else "first stop", "stops": order, "km": round(total, 1), "maps_url": url}
