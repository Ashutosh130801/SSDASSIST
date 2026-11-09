"""📊 Advanced analytics add-on — all figures limited to the cases the user may see.

• Resolution by bank / product / bucket (count + amount)
• Roll-back / stabilise / roll-forward: same account last month vs this month by bucket
• Contactability & promise-to-pay quality (PTP kept ratio)
• Agent productivity (attempts, connects, PTPs, visits, collected per working day)
• Best hours (connect rate by hour of day)
• Month-end forecast = collected so far + run-rate + open PTPs × kept ratio
"""
from __future__ import annotations

import calendar
import re
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from ..addons_common import IST, D, LEADS, need, now_ist, scoped_cases
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/api/insights", tags=["insights"])
NO_CONNECT = ("RNR", "SWITCHED OFF", "SWITCH OFF", "NOT REACHABLE", "NR", "NC", "WRONG NO", "WRONG NUMBER", "BUSY", "NO ANSWER", "DND")
PAY = ("PAID", "PAYMENT")


def bucket_rank(b):
    s = (b or "").upper()
    if not s:
        return None
    if s.startswith("X") or "CURRENT" in s:
        return 0
    m = re.search(r"(\d+)", s)
    if not m:
        return None
    n = int(m.group(1))
    return n if n < 30 else (n // 30)       # "60+" / "90 DPD" style → bucket number


def _ist(dt):
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(IST)


@router.get("")
def insights(db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, LEADS, "advanced analytics")
    from .cases import _current_period, _last_period
    now = now_ist()
    per, last = _current_period(), _last_period()
    cur = scoped_cases(db, user).filter(models.Case.period == per).all()
    ids = [c.id for c in cur]

    # 1. resolution
    res = defaultdict(lambda: {"cases": 0, "paid": 0, "partial": 0, "received": D(0), "pending": D(0)})
    for c in cur:
        k = (c.bank or "—", c.product or "—", c.bucket or "—")
        r = res[k]; r["cases"] += 1
        st = (c.paid_status or "").upper()
        r["paid"] += st == "PAID"; r["partial"] += st == "PARTIAL"
        r["received"] += D(c.received_amount); r["pending"] += max(D(c.pending_amount), D(0))
    resolution = []
    for (bank, prod, bkt), r in sorted(res.items()):
        tot = r["received"] + r["pending"]
        resolution.append({"bank": bank, "product": prod, "bucket": bkt, "cases": r["cases"], "paid": r["paid"], "partial": r["partial"],
                           "resolution_pct": round(100 * r["paid"] / r["cases"], 1) if r["cases"] else 0,
                           "received": float(r["received"]), "collection_pct": round(float(100 * r["received"] / tot), 1) if tot else 0})

    # 2. roll rates (same account, last month → this month)
    prev = {}
    for acc, bkt in scoped_cases(db, user, all_periods=True).filter(models.Case.period == last) \
            .with_entities(models.Case.account_no, models.Case.bucket).all():
        if acc:
            prev[acc] = bkt
    roll = Counter(); matrix = Counter()
    for c in cur:
        if c.account_no in prev:
            a, b = bucket_rank(prev[c.account_no]), bucket_rank(c.bucket)
            if a is None or b is None:
                continue
            roll["rolled_back" if b < a else "stabilised" if b == a else "rolled_forward"] += 1
            matrix[(prev[c.account_no], c.bucket)] += 1
    rolls = {"counts": dict(roll), "total": sum(roll.values()),
             "matrix": [{"from": f, "to": t, "cases": n} for (f, t), n in sorted(matrix.items(), key=lambda x: -x[1])[:40]]}

    # 3–5. call quality, productivity, hours
    start = datetime(now.year, now.month, 1, tzinfo=IST).astimezone(timezone.utc)
    calls = []
    for i in range(0, len(ids), 800):
        calls += db.query(models.CallLog).filter(models.CallLog.case_id.in_(ids[i:i + 800]), models.CallLog.created_at >= start).all()
    visits = []
    for i in range(0, len(ids), 800):
        visits += db.query(models.Visit).filter(models.Visit.case_id.in_(ids[i:i + 800]), models.Visit.created_at >= start).all()
    attempts = [c for c in calls if (c.disposition or "").upper() not in PAY]
    connected = [c for c in attempts if (c.disposition or "").upper() not in NO_CONNECT]
    ptps = [c for c in calls if (c.disposition or "").upper() == "PTP" and c.ptp_date]
    pays_by_case = defaultdict(list)
    for c in calls:
        if (c.disposition or "").upper() in PAY and D(c.ptp_amount) > 0:
            pays_by_case[c.case_id].append(_ist(c.created_at))
    for v in visits:
        if v.paid and D(v.amount_collected) > 0:
            pays_by_case[v.case_id].append(_ist(v.created_at))
    today = now.date()
    due = [p for p in ptps if _ist(p.ptp_date).date() <= today]
    kept = [p for p in due if any(_ist(p.created_at) <= t <= _ist(p.ptp_date) + timedelta(days=3) for t in pays_by_case.get(p.case_id, []))]
    kept_ratio = (len(kept) / len(due)) if due else 0.0
    quality = {"attempts": len(attempts), "connected": len(connected),
               "connect_rate": round(100 * len(connected) / len(attempts), 1) if attempts else 0,
               "ptps": len(ptps), "ptp_due": len(due), "ptp_kept": len(kept), "kept_ratio": round(100 * kept_ratio, 1)}

    hours = defaultdict(lambda: [0, 0])
    for c in attempts:
        h = _ist(c.created_at).hour
        hours[h][0] += 1; hours[h][1] += (c.disposition or "").upper() not in NO_CONNECT
    best_hours = [{"hour": f"{h:02d}:00", "attempts": a, "connect_rate": round(100 * k / a, 1) if a else 0} for h, (a, k) in sorted(hours.items())]

    names = {u.id: (u.name, u.role) for u in db.query(models.User).all()}
    agents = defaultdict(lambda: {"attempts": 0, "connected": 0, "ptps": 0, "visits": 0, "collected": D(0), "days": set()})
    for c in calls:
        a = agents[c.caller_id]; d = (c.disposition or "").upper()
        a["days"].add(_ist(c.created_at).date())
        if d in PAY:
            a["collected"] += D(c.ptp_amount)
        else:
            a["attempts"] += 1; a["connected"] += d not in NO_CONNECT; a["ptps"] += d == "PTP"
    for v in visits:
        a = agents[v.officer_id]; a["visits"] += 1; a["days"].add(_ist(v.created_at).date())
        if v.paid:
            a["collected"] += D(v.amount_collected)
    productivity = []
    for uid, a in agents.items():
        nd = max(len(a["days"]), 1)
        nm, role = names.get(uid, ("—", ""))
        productivity.append({"user_id": uid, "name": nm, "role": role, "days": len(a["days"]), "attempts": a["attempts"],
                             "per_day": round((a["attempts"] + a["visits"]) / nd, 1), "connect_rate": round(100 * a["connected"] / a["attempts"], 1) if a["attempts"] else 0,
                             "ptps": a["ptps"], "visits": a["visits"], "collected": float(a["collected"]),
                             "collected_per_day": round(float(a["collected"]) / nd, 0)})
    productivity.sort(key=lambda r: -r["collected"])

    # 6. forecast
    collected = sum(float(c["collected"]) for c in productivity)
    days_in = calendar.monthrange(now.year, now.month)[1]
    elapsed = max(now.day, 1)
    run_rate = collected / elapsed * days_in
    open_ptps = [p for p in ptps if _ist(p.ptp_date).date() > today and not pays_by_case.get(p.case_id)]
    ptp_value = sum(float(D(p.ptp_amount)) for p in open_ptps)
    pending = sum(float(max(D(c.pending_amount), D(0))) for c in cur)
    forecast = {"collected_so_far": round(collected, 0), "run_rate_month_end": round(run_rate, 0),
                "open_ptp_value": round(ptp_value, 0), "expected_from_ptps": round(ptp_value * kept_ratio, 0),
                "forecast_month_end": round(collected + max(run_rate - collected, 0) * 0.5 + ptp_value * kept_ratio, 0),
                "pending_book": round(pending, 0), "days_left": days_in - now.day,
                "method": "collected so far + half of the remaining run-rate + open PTPs × kept ratio"}
    return {"period": per, "resolution": resolution, "rolls": rolls, "quality": quality, "hours": best_hours,
            "productivity": productivity[:200], "forecast": forecast}
