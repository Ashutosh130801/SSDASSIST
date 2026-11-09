"""AI Assist tools — the ONLY way the AI reads data.

Every tool runs with the asking user's identity and the same scoping the screens use:
  • cases  → routers.cases._scope (caller/FOS own, team lead team, manager branch, HO/admin all)
  • people → visible_staff() (self for agents, team for TL, branch for manager, all for HO/admin/HR)
So the AI can never see more than the user could on screen. Tools return rows with full values;
the router masks phone/account numbers before anything is sent to the AI provider, and builds
downloadable files from the unmasked, already-scoped rows.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, or_

from . import models

IST = timezone(timedelta(hours=5, minutes=30))
CASE_ROLES = ("admin", "headoffice", "manager", "teamlead", "fos", "telecaller", "backend", "techsupport", "it_support_view")
LEAD_ROLES = ("admin", "headoffice", "manager", "teamlead", "techsupport", "it_support_view")
PEOPLE_ALL = ("admin", "headoffice", "hr", "techsupport", "it_support_view")


class ToolError(Exception):
    pass


def _today():
    return datetime.now(IST).date()


def _f(x):
    return float(x or 0)


def visible_staff(db, user) -> list[int] | None:
    """None = everyone; else the user ids this user may see."""
    if user.role in PEOPLE_ALL:
        return None
    if user.role in ("teamlead", "manager"):
        from .routers.cases import _scope_user_ids
        ids = set(_scope_user_ids(db, user))
        if user.role == "teamlead":
            ids |= {u.id for u in db.query(models.User.id).filter(models.User.team_lead_id == user.id)}
        ids.add(user.id)
        return list(ids)
    return [user.id]


def _cases(db, user, bucket=None):
    if user.role not in CASE_ROLES:
        raise ToolError("Your role has no access to case data.")
    from .routers.cases import _scope
    b = bucket if bucket in ("last",) else None
    q = _scope(db.query(models.Case), user, bucket=b, all_periods=(bucket == "all" and user.role in ("admin", "headoffice")))
    if bucket == "current":
        from .routers.cases import _current_period
        q = q.filter(or_(models.Case.period.is_(None), models.Case.period == _current_period()))
    elif bucket == "next":
        from .routers.cases import _next_period
        q = q.filter(models.Case.period == _next_period())
    return q


ALL_MONTH_ROLES = ("admin", "headoffice", "techsupport", "it_support_view")


def _cases_for(db, user, args) -> tuple:
    """Scoped case query for a tool call + a note when the month had to be chosen automatically.
    month=YYYY-MM picks one month; bucket=current|next|last|all; nothing → this month, or — if this
    month has no data yet — the latest month that does (and says so)."""
    import re as _re
    from .routers.cases import _current_period, _last_period, _next_period
    month = str(args.get("month") or "").strip()
    bucket = (args.get("bucket") or "").strip().lower()
    if month:
        if not _re.fullmatch(r"\d{4}-\d{2}", month):
            raise ToolError("month must be YYYY-MM")
        if user.role in ALL_MONTH_ROLES:
            return _cases(db, user, "all").filter(models.Case.period == month), None
        if month == _last_period():
            return _cases(db, user, "last"), None
        if month in (_current_period(), _next_period()):
            return _cases(db, user).filter(models.Case.period == month), None
        raise ToolError(f"Your role can see {_last_period()}, {_current_period()} and {_next_period()} only.")
    if bucket in ("current", "next", "last", "all"):
        return _cases(db, user, bucket), None
    q = _cases(db, user, "current")
    if q.with_entities(models.Case.id).first():
        return q, None
    # nothing uploaded for this month yet → fall back to the latest month the user can see
    if user.role in ALL_MONTH_ROLES:
        latest = _cases(db, user, "all").with_entities(func.max(models.Case.period)).scalar()
        if latest:
            return _cases(db, user, "all").filter(models.Case.period == latest), \
                f"No cases for {_current_period()} yet — showing {latest}, the latest month with data."
    for b, label in (("next", _next_period()), ("last", _last_period())):
        q2 = _cases(db, user, b)
        if q2.with_entities(models.Case.id).first():
            return q2, f"No cases for {_current_period()} yet — showing {label}."
    return q, None


def _bank_filter(q, bank):
    """'Axis', 'AXIS BANK', 'axis bank ltd' all match AXIS."""
    b = str(bank or "").upper().replace(" LTD", "").replace(" LIMITED", "").replace(" BANK", "").strip()
    return q.filter(func.upper(models.Case.bank).like(f"%{b}%")) if b else q


def overview(db, user, compact=False) -> dict:
    """What data this user can see: months, banks/products with counts, buckets, branches, outcomes, staff."""
    if user.role not in CASE_ROLES:
        return {"cases": "no case access for this role"}
    from .routers.cases import _current_period
    base = _cases(db, user, "all" if user.role in ALL_MONTH_ROLES else None)
    rows = (base.with_entities(models.Case.period, models.Case.bank, models.Case.product, func.count(models.Case.id),
                               func.sum(func.cast(models.Case.paid_status == "PAID", models.Integer)),
                               func.coalesce(func.sum(models.Case.pending_amount), 0))
            .group_by(models.Case.period, models.Case.bank, models.Case.product).all())
    months = {}
    for per, bank, prod, n, paid, pend in rows:
        m = months.setdefault(per or "no month", {"month": per or "no month", "cases": 0, "paid": 0, "pending": 0.0, "portfolios": []})
        m["cases"] += int(n or 0); m["paid"] += int(paid or 0); m["pending"] += _f(pend)
        m["portfolios"].append(f"{bank or '?'} / {prod or '?'} ({int(n or 0)})")
    ms = sorted(months.values(), key=lambda m: m["month"], reverse=True)[:6]
    for m in ms:
        m["pending"] = round(m["pending"])
        m["portfolios"] = m["portfolios"][:25]
    def top(col, k=15):
        return [v for (v,) in base.with_entities(col).filter(col.isnot(None), col != "").group_by(col)
                .order_by(func.count(models.Case.id).desc()).limit(k).all()]
    out = {"current_month": _current_period(), "months": ms,
           "banks": top(models.Case.bank), "products": top(models.Case.product, 25), "buckets": top(models.Case.bucket),
           "branches": top(models.Case.branch), "dispositions": top(models.Case.disposition, 20),
           "paid_status_values": ["PAID", "PARTIAL", "UNPAID"]}
    staff = visible_staff(db, user)
    sq = db.query(models.User.name, models.User.role).filter(models.User.is_active.is_(True),
                                                             models.User.role.in_(("fos", "telecaller", "teamlead", "manager")))
    if staff is not None:
        sq = sq.filter(models.User.id.in_(staff or [0]))
    people = sq.order_by(models.User.role, models.User.name).limit(15 if compact else 80).all()
    out["staff"] = [f"{n} ({r})" for n, r in people]
    if compact:
        for m in out["months"]:
            m["portfolios"] = m["portfolios"][:8]
    return out


def _names(db, ids):
    ids = {i for i in ids if i}
    return {u.id: u.name for u in db.query(models.User.id, models.User.name).filter(models.User.id.in_(ids or {0}))}


def _period_bounds(period: str | None):
    t = _today()
    if not period or period == "this_month":
        return t.replace(day=1), t
    if period == "today":
        return t, t
    if period == "yesterday":
        return t - timedelta(days=1), t - timedelta(days=1)
    if period == "this_week":
        return t - timedelta(days=t.weekday()), t
    if period == "last_month":
        first = t.replace(day=1)
        prev = first - timedelta(days=1)
        return prev.replace(day=1), prev
    if period == "last_7_days":
        return t - timedelta(days=6), t
    if period == "last_30_days":
        return t - timedelta(days=29), t
    try:
        a, b = period.split("..")
        return date.fromisoformat(a), date.fromisoformat(b)
    except Exception:
        raise ToolError("period must be today / yesterday / this_week / this_month / last_month / last_7_days / last_30_days / YYYY-MM-DD..YYYY-MM-DD")


def _dt_range(a: date, b: date):
    s = datetime(a.year, a.month, a.day, tzinfo=IST).astimezone(timezone.utc)
    e = datetime(b.year, b.month, b.day, tzinfo=IST).astimezone(timezone.utc) + timedelta(days=1)
    return s, e


# ───────────────────────────────────────────────────────────── tools
def t_whoami(db, user, args):
    staff = visible_staff(db, user)
    return {"name": user.name, "role": user.role, "branch": user.branch, "emp_code": user.emp_code, "today": _today().isoformat(),
            "can_see": ("all cases and all staff" if staff is None and user.role in ("admin", "headoffice") else
                        "own cases only" if user.role in ("fos", "telecaller") else
                        "own team's cases and staff" if user.role == "teamlead" else
                        "own branch's cases and staff" if user.role == "manager" else "staff records (no case data)" if user.role == "hr" else "as per role")}


def t_portfolio_summary(db, user, args):
    q, note = _cases_for(db, user, args)
    if args.get("bank"):
        q = _bank_filter(q, args["bank"])
    if args.get("product"):
        q = q.filter(models.Case.product.ilike(f"%{args['product']}%"))
    rows = (q.with_entities(models.Case.bank, models.Case.product, models.Case.period,
                            func.count(models.Case.id),
                            func.sum(func.cast(models.Case.paid_status == "PAID", models.Integer)),
                            func.sum(func.cast(models.Case.paid_status == "PARTIAL", models.Integer)),
                            func.coalesce(func.sum(models.Case.total_outstanding), 0),
                            func.coalesce(func.sum(models.Case.received_amount), 0),
                            func.coalesce(func.sum(models.Case.pending_amount), 0))
            .group_by(models.Case.bank, models.Case.product, models.Case.period).all())
    out = []
    for bank, prod, per, n, paid, part, tos, rec, pend in rows:
        n, paid, part = int(n or 0), int(paid or 0), int(part or 0)
        out.append({"bank": bank, "product": prod, "month": per, "cases": n, "paid": paid, "partial": part,
                    "unpaid": n - paid - part, "paid_pct": round(100 * paid / n, 1) if n else 0,
                    "total_outstanding": round(_f(tos), 2), "received": round(_f(rec), 2), "pending": round(_f(pend), 2)})
    out.sort(key=lambda r: (-r["cases"]))
    tot = {k: sum(r[k] for r in out) for k in ("cases", "paid", "partial", "unpaid", "received", "pending", "total_outstanding")}
    tot["paid_pct"] = round(100 * tot["paid"] / tot["cases"], 1) if tot["cases"] else 0
    res = {"rows": out, "totals": tot}
    if note:
        res["note"] = note
    if not out:
        res["hint"] = "No cases matched. Call data_overview to see the months, banks and products that exist, then retry."
    return res


CASE_COLS = ["id", "customer", "account_no", "phone", "bank", "product", "month", "bucket", "status", "paid_status", "disposition",
             "total_outstanding", "received", "pending", "fos", "caller", "follow_up", "last_contacted", "remarks"]


def _case_row(c, names):
    return {"id": c.id, "customer": c.customer_name, "account_no": c.account_no, "phone": c.phone, "bank": c.bank, "product": c.product,
            "month": c.period, "bucket": c.bucket, "status": c.status, "paid_status": c.paid_status, "disposition": c.disposition,
            "total_outstanding": _f(c.total_outstanding), "received": _f(c.received_amount), "pending": _f(c.pending_amount),
            "fos": names.get(c.assigned_fos_id) or c.fos_name, "caller": names.get(c.assigned_caller_id) or c.caller_name,
            "follow_up": c.follow_up_date.isoformat() if c.follow_up_date else None,
            "last_contacted": c.last_contacted_at.strftime("%Y-%m-%d") if c.last_contacted_at else None, "remarks": (c.remarks or "")[:160]}


def t_search_cases(db, user, args):
    q, note = _cases_for(db, user, args)
    base_q = q
    text = (args.get("text") or "").strip()
    if text:
        like = f"%{text}%"
        q = q.filter(or_(models.Case.customer_name.ilike(like), models.Case.account_no.ilike(like), models.Case.card_no.ilike(like),
                         models.Case.phone.ilike(like), models.Case.vehicle_num.ilike(like)))
    if args.get("bank"):
        q = _bank_filter(q, args["bank"])
    if args.get("product"):
        q = q.filter(models.Case.product.ilike(f"%{args['product']}%"))
    st = (args.get("status") or "any").lower()
    st = {"pending": "unpaid", "not paid": "unpaid", "open": "unpaid", "settled": "paid", "closed": "paid",
          "promise": "ptp", "promised": "ptp", "part": "partial", "partially paid": "partial"}.get(st, st)
    if st in ("paid", "unpaid", "partial"):
        q = q.filter(models.Case.paid_status == st.upper())
    elif st == "ptp":
        q = q.filter(models.Case.disposition.ilike("%PTP%"))
    elif st == "follow_up_due":
        q = q.filter(models.Case.follow_up_date.isnot(None), models.Case.follow_up_date <= _today())
    elif st == "not_contacted":
        q = q.filter(models.Case.last_contacted_at.is_(None))
    if args.get("disposition"):
        q = q.filter(models.Case.disposition.ilike(f"%{args['disposition']}%"))
    if args.get("assigned_to"):
        ids = [u.id for u in db.query(models.User.id).filter(models.User.name.ilike(f"%{args['assigned_to']}%"))]
        q = q.filter(or_(models.Case.assigned_fos_id.in_(ids or [0]), models.Case.assigned_caller_id.in_(ids or [0])))
    if args.get("min_pending"):
        q = q.filter(models.Case.pending_amount >= float(args["min_pending"]))
    order = {"pending": models.Case.pending_amount.desc(), "outstanding": models.Case.total_outstanding.desc(),
             "follow_up": models.Case.follow_up_date.asc()}.get(args.get("sort") or "pending", models.Case.pending_amount.desc())
    total = q.count()
    lim = max(1, min(int(args.get("limit") or 50), int(args.get("_max", 200))))
    cs = q.order_by(order).limit(lim).all()
    names = _names(db, [c.assigned_fos_id for c in cs] + [c.assigned_caller_id for c in cs])
    res = {"total_matching": total, "returned": len(cs), "columns": CASE_COLS, "rows": [_case_row(c, names) for c in cs]}
    if note:
        res["note"] = note
    if total == 0:
        res["why_empty"] = _why_empty(db, user, base_q, args)
    return res


def _why_empty(db, user, base_q, args):
    """Which filter emptied the result, and what values actually exist — so the AI can retry correctly."""
    out = {"cases_in_scope_for_month": base_q.count()}
    if args.get("bank"):
        out["with_bank_only"] = _bank_filter(base_q, args["bank"]).count()
        out["banks_available"] = [b for (b,) in base_q.with_entities(models.Case.bank).distinct().limit(20) if b]
    if args.get("product"):
        out["with_product_only"] = base_q.filter(models.Case.product.ilike(f"%{args['product']}%")).count()
        out["products_available"] = [p for (p,) in base_q.with_entities(models.Case.product).distinct().limit(30) if p]
    if args.get("disposition"):
        out["dispositions_available"] = [d for (d,) in base_q.with_entities(models.Case.disposition).distinct().limit(25) if d]
    if args.get("assigned_to"):
        out["staff_matching_name"] = [n for (n,) in db.query(models.User.name).filter(models.User.name.ilike(f"%{args['assigned_to']}%")).limit(10)]
    if args.get("text"):
        out["note"] = "text matches customer name / account / card / phone / vehicle number only"
    out["advice"] = "Retry with values from the lists above, drop the filter that emptied the result, or call data_overview."
    return out


def t_case_detail(db, user, args):
    q = _cases(db, user, "all" if user.role in ("admin", "headoffice") else None)
    cid = args.get("case_id")
    c = None
    if cid:
        c = q.filter(models.Case.id == int(cid)).first()
    elif args.get("account_no"):
        c = q.filter(models.Case.account_no == str(args["account_no"]).strip()).first()
    if not c:
        raise ToolError("No such case in your scope.")
    names = _names(db, [c.assigned_fos_id, c.assigned_caller_id])
    row = _case_row(c, names)
    row.update({"address": c.address, "pincode": c.pincode, "alt_phone": c.alt_phone, "new_phone": c.new_phone, "new_address": c.new_address,
                "norm": _f(c.norm_amount), "stab": _f(c.stab_amount), "min_due": _f(c.min_amount_due), "cycle": c.cycle, "team_lead": c.team_lead})
    calls = (db.query(models.CallLog).filter(models.CallLog.case_id == c.id).order_by(models.CallLog.created_at.desc()).limit(5).all())
    visits = (db.query(models.Visit).filter(models.Visit.case_id == c.id).order_by(models.Visit.created_at.desc()).limit(5).all())
    cn = _names(db, [x.caller_id for x in calls] + [v.officer_id for v in visits])
    row["recent_calls"] = [{"date": x.created_at.strftime("%Y-%m-%d %H:%M") if x.created_at else None, "by": cn.get(x.caller_id),
                            "disposition": x.disposition, "ptp_amount": _f(x.ptp_amount),
                            "ptp_date": x.ptp_date.strftime("%Y-%m-%d") if x.ptp_date else None, "note": (x.note or "")[:200]} for x in calls]
    row["recent_visits"] = [{"date": v.created_at.strftime("%Y-%m-%d %H:%M") if v.created_at else None, "by": cn.get(v.officer_id),
                             "disposition": v.disposition, "paid": bool(v.paid), "amount": _f(v.amount_collected),
                             "note": (v.note or "")[:200], "trust": v.trust_level} for v in visits]
    return row


def t_ptp_list(db, user, args):
    seg = (args.get("segment") or "all").lower()
    from sqlalchemy import select
    cq, note = _cases_for(db, user, args)
    sub = cq.with_entities(models.Case.id).subquery()
    q = (db.query(models.CallLog).filter(models.CallLog.case_id.in_(select(sub.c.id)),
                                         models.CallLog.disposition.ilike("%PTP%"), models.CallLog.ptp_date.isnot(None)))
    t = _today()
    s, e = _dt_range(t, t)
    if seg == "overdue":
        q = q.filter(models.CallLog.ptp_date < s)
    elif seg == "today":
        q = q.filter(models.CallLog.ptp_date >= s, models.CallLog.ptp_date < e)
    elif seg == "upcoming":
        q = q.filter(models.CallLog.ptp_date >= e)
    logs = q.order_by(models.CallLog.ptp_date).limit(int(args.get("limit") or 100)).all()
    latest = {}
    for l in logs:                                        # one row per case: the latest promise
        if l.case_id not in latest or (l.created_at or datetime.min) > (latest[l.case_id].created_at or datetime.min):
            latest[l.case_id] = l
    cases = {c.id: c for c in db.query(models.Case).filter(models.Case.id.in_(list(latest) or [0]))}
    names = _names(db, [l.caller_id for l in latest.values()])
    rows = []
    for cid, l in latest.items():
        c = cases.get(cid)
        if not c or c.paid_status == "PAID":
            continue
        rows.append({"case_id": cid, "customer": c.customer_name, "account_no": c.account_no, "phone": c.phone, "bank": c.bank,
                     "product": c.product, "ptp_date": l.ptp_date.strftime("%Y-%m-%d"), "ptp_amount": _f(l.ptp_amount),
                     "pending": _f(c.pending_amount), "promised_to": names.get(l.caller_id), "note": (l.note or "")[:120]})
    rows.sort(key=lambda r: r["ptp_date"])
    return {"segment": seg, "count": len(rows), "promised_total": round(sum(r["ptp_amount"] for r in rows), 2), **({"note": note} if note else {}),
            "columns": ["case_id", "customer", "account_no", "phone", "bank", "product", "ptp_date", "ptp_amount", "pending", "promised_to", "note"],
            "rows": rows}


def t_team_performance(db, user, args):
    if user.role not in LEAD_ROLES + ("fos", "telecaller"):
        raise ToolError("Your role has no access to performance data.")
    a, b = _period_bounds(args.get("period") or "this_month")
    s, e = _dt_range(a, b)
    staff = visible_staff(db, user)
    uq = db.query(models.User).filter(models.User.is_active == True, models.User.role.in_(("fos", "telecaller", "teamlead")))  # noqa: E712
    if staff is not None:
        uq = uq.filter(models.User.id.in_(staff))
    if args.get("role") in ("fos", "telecaller"):
        uq = uq.filter(models.User.role == args["role"])
    users = uq.all()
    ids = [u.id for u in users]
    visits = dict(db.query(models.Visit.officer_id, func.count(models.Visit.id)).filter(models.Visit.officer_id.in_(ids or [0]),
                  models.Visit.created_at >= s, models.Visit.created_at < e).group_by(models.Visit.officer_id).all())
    vcoll = dict(db.query(models.Visit.officer_id, func.coalesce(func.sum(models.Visit.amount_collected), 0)).filter(
        models.Visit.officer_id.in_(ids or [0]), models.Visit.created_at >= s, models.Visit.created_at < e).group_by(models.Visit.officer_id).all())
    calls = dict(db.query(models.CallLog.caller_id, func.count(models.CallLog.id)).filter(models.CallLog.caller_id.in_(ids or [0]),
                 models.CallLog.created_at >= s, models.CallLog.created_at < e).group_by(models.CallLog.caller_id).all())
    ptps = dict(db.query(models.CallLog.caller_id, func.count(models.CallLog.id)).filter(models.CallLog.caller_id.in_(ids or [0]),
                models.CallLog.disposition.ilike("%PTP%"), models.CallLog.created_at >= s, models.CallLog.created_at < e)
                .group_by(models.CallLog.caller_id).all())
    from .routers.cases import _current_period
    cur = _current_period()
    fos_c = dict(db.query(models.Case.assigned_fos_id, func.count(models.Case.id)).filter(models.Case.assigned_fos_id.in_(ids or [0]),
                 models.Case.removed.isnot(True), models.Case.period == cur).group_by(models.Case.assigned_fos_id).all())
    tc_c = dict(db.query(models.Case.assigned_caller_id, func.count(models.Case.id)).filter(models.Case.assigned_caller_id.in_(ids or [0]),
                models.Case.removed.isnot(True), models.Case.period == cur).group_by(models.Case.assigned_caller_id).all())
    paid_f = dict(db.query(models.Case.assigned_fos_id, func.count(models.Case.id)).filter(models.Case.assigned_fos_id.in_(ids or [0]),
                  models.Case.paid_status == "PAID", models.Case.removed.isnot(True), models.Case.period == cur).group_by(models.Case.assigned_fos_id).all())
    paid_t = dict(db.query(models.Case.assigned_caller_id, func.count(models.Case.id)).filter(models.Case.assigned_caller_id.in_(ids or [0]),
                  models.Case.paid_status == "PAID", models.Case.removed.isnot(True), models.Case.period == cur).group_by(models.Case.assigned_caller_id).all())
    rows = []
    for u in users:
        n = (fos_c.get(u.id, 0) if u.role == "fos" else tc_c.get(u.id, 0))
        p = (paid_f.get(u.id, 0) if u.role == "fos" else paid_t.get(u.id, 0))
        rows.append({"name": u.name, "emp_code": u.emp_code, "role": u.role, "branch": u.branch, "cases_this_month": n, "paid_cases": p,
                     "paid_pct": round(100 * p / n, 1) if n else 0, "visits": visits.get(u.id, 0), "visit_collections": round(_f(vcoll.get(u.id)), 2),
                     "calls": calls.get(u.id, 0), "ptps": ptps.get(u.id, 0)})
    rows.sort(key=lambda r: (-r["paid_pct"], -r["visits"] - r["calls"]))
    return {"from": a.isoformat(), "to": b.isoformat(), "columns": list(rows[0].keys()) if rows else [], "rows": rows}


def t_activity(db, user, args):
    kind = (args.get("kind") or "visits").lower()
    a, b = _period_bounds(args.get("period") or "today")
    s, e = _dt_range(a, b)
    staff = visible_staff(db, user)
    if kind == "visits":
        q = db.query(models.Visit).filter(models.Visit.created_at >= s, models.Visit.created_at < e)
        if staff is not None:
            q = q.filter(models.Visit.officer_id.in_(staff))
        if args.get("person"):
            q = q.filter(models.Visit.officer_id.in_([u.id for u in db.query(models.User.id).filter(models.User.name.ilike(f"%{args['person']}%"))] or [0]))
        items = q.order_by(models.Visit.created_at.desc()).limit(int(args.get("limit") or 200)).all()
        names = _names(db, [v.officer_id for v in items])
        cases = {c.id: c for c in db.query(models.Case).filter(models.Case.id.in_({v.case_id for v in items} or {0}))}
        rows = [{"time": v.created_at.astimezone(IST).strftime("%Y-%m-%d %H:%M") if v.created_at else None, "by": names.get(v.officer_id),
                 "customer": (cases.get(v.case_id).customer_name if cases.get(v.case_id) else None), "case_id": v.case_id,
                 "disposition": v.disposition, "paid": bool(v.paid), "amount": _f(v.amount_collected), "trust": v.trust_level,
                 "note": (v.note or "")[:120]} for v in items]
    elif kind == "calls":
        q = db.query(models.CallLog).filter(models.CallLog.created_at >= s, models.CallLog.created_at < e)
        if staff is not None:
            q = q.filter(models.CallLog.caller_id.in_(staff))
        if args.get("person"):
            q = q.filter(models.CallLog.caller_id.in_([u.id for u in db.query(models.User.id).filter(models.User.name.ilike(f"%{args['person']}%"))] or [0]))
        items = q.order_by(models.CallLog.created_at.desc()).limit(int(args.get("limit") or 200)).all()
        names = _names(db, [x.caller_id for x in items])
        cases = {c.id: c for c in db.query(models.Case).filter(models.Case.id.in_({x.case_id for x in items} or {0}))}
        rows = [{"time": x.created_at.astimezone(IST).strftime("%Y-%m-%d %H:%M") if x.created_at else None, "by": names.get(x.caller_id),
                 "customer": (cases.get(x.case_id).customer_name if cases.get(x.case_id) else None), "case_id": x.case_id,
                 "disposition": x.disposition, "ptp_amount": _f(x.ptp_amount),
                 "ptp_date": x.ptp_date.strftime("%Y-%m-%d") if x.ptp_date else None, "note": (x.note or "")[:120]} for x in items]
    else:
        raise ToolError("kind must be visits or calls")
    return {"kind": kind, "from": a.isoformat(), "to": b.isoformat(), "count": len(rows),
            "columns": list(rows[0].keys()) if rows else [], "rows": rows}


def t_attendance(db, user, args):
    a, b = _period_bounds(args.get("period") or "today")
    staff = visible_staff(db, user)
    q = db.query(models.Attendance).filter(models.Attendance.date >= a, models.Attendance.date <= b)
    if staff is not None:
        q = q.filter(models.Attendance.user_id.in_(staff))
    if args.get("person"):
        q = q.filter(models.Attendance.user_id.in_([u.id for u in db.query(models.User.id).filter(models.User.name.ilike(f"%{args['person']}%"))] or [0]))
    per = {}
    for r in q.all():
        d = per.setdefault(r.user_id, {"days_checked_in": 0, "late": 0, "worked_hours": 0.0})
        if r.check_in_at:
            d["days_checked_in"] += 1
        d["late"] += 1 if r.late else 0
        d["worked_hours"] += round((r.worked_seconds or 0) / 3600, 2)
    uq = db.query(models.User).filter(models.User.is_active == True, ~models.User.role.in_(("techsupport", "it_support_view")))  # noqa: E712
    if staff is not None:
        uq = uq.filter(models.User.id.in_(staff))
    rows = []
    for u in uq.all():
        d = per.get(u.id, {"days_checked_in": 0, "late": 0, "worked_hours": 0.0})
        rows.append({"name": u.name, "emp_code": u.emp_code, "role": u.role, **{k: round(v, 2) if isinstance(v, float) else v for k, v in d.items()}})
    rows.sort(key=lambda r: r["name"] or "")
    return {"from": a.isoformat(), "to": b.isoformat(), "columns": list(rows[0].keys()) if rows else [], "rows": rows,
            "note": "days_checked_in counts days with a check-in; see Attendance for the full present/absent grid."}


def t_leave(db, user, args):
    from .routers.leaves import DEFAULT_ALLOWANCE, LEAVE_TYPES, _year_totals
    yr = _today().year
    tot = _year_totals(db, [user.id], yr).get(user.id, {})
    mine = [{"type": t, "allowance": DEFAULT_ALLOWANCE.get(t, 0), "used": tot.get(t, {}).get("approved", 0),
             "pending": tot.get(t, {}).get("pending", 0)} for t in LEAVE_TYPES]
    out = {"my_balance": mine}
    staff = visible_staff(db, user)
    if user.role in LEAD_ROLES + ("hr",):
        q = db.query(models.Leave).filter(models.Leave.status == "pending")
        if staff is not None:
            q = q.filter(models.Leave.user_id.in_(staff))
        lv = q.order_by(models.Leave.start_date).limit(100).all()
        names = _names(db, [l.user_id for l in lv])
        out["pending_requests"] = [{"name": names.get(l.user_id), "type": l.leave_type, "from": l.start_date.isoformat(),
                                    "to": l.end_date.isoformat(), "reason": (l.reason or "")[:100]} for l in lv]
    return out


def t_my_salary(db, user, args):
    from . import services as svc
    from .routers import payouts
    if payouts.SECTION_LOCKED or not svc.is_on(db, "salary"):
        raise ToolError("Salary & Payslips is not enabled.")
    rows = (db.query(models.PayrollLine, models.PayrollRun).join(models.PayrollRun, models.PayrollRun.id == models.PayrollLine.run_id)
            .filter(models.PayrollLine.user_id == user.id, models.PayrollLine.included == True, models.PayrollRun.released == True)  # noqa: E712
            .order_by(models.PayrollRun.period.desc()).limit(12).all())
    return {"payslips": [{"month": r.period, "gross": _f(l.gross), "deductions": _f(l.total_deductions), "net": _f(l.net),
                          "status": l.pay_status} for l, r in rows],
            "note": "Only your own released payslips. Download PDFs from My Payslips."}


def t_data_overview(db, user, args):
    return overview(db, user)


TOOLS = {
    "data_overview": (t_data_overview, "What data this user can see: months (with case counts and portfolios), banks, products, buckets, "
                      "branches, dispositions in use, and staff names. Call it when unsure of names/values, or after a search returns 0.", {}),
    "whoami": (t_whoami, "Who the user is, their role and what data they can see. Call first if unsure.", {}),
    "portfolio_summary": (t_portfolio_summary, "Portfolio totals by bank/product/month: cases, paid, partial, unpaid, paid %, outstanding, received, pending.",
                          {"bank": "string", "product": "string", "month": "YYYY-MM", "bucket": "current|next|last|all"}),
    "search_cases": (t_search_cases, "Find cases. All filters optional — start broad. Filters: text (name/account/phone/vehicle), bank (partial ok, e.g. 'axis'), product, status (paid|unpaid|partial|ptp|follow_up_due|not_contacted|any), disposition, assigned_to (staff name), min_pending, sort (pending|outstanding|follow_up), limit, bucket.",
                     {"text": "string", "bank": "string", "product": "string", "status": "string", "disposition": "string",
                      "assigned_to": "string", "min_pending": "number", "sort": "string", "limit": "integer",
                      "month": "YYYY-MM", "bucket": "current|next|last|all"}),
    "case_detail": (t_case_detail, "Full detail of one case incl. last 5 calls and visits.", {"case_id": "integer", "account_no": "string"}),
    "ptp_list": (t_ptp_list, "Promises to pay. segment = overdue|today|upcoming|all.", {"segment": "string", "limit": "integer", "month": "YYYY-MM", "bucket": "current|next|last|all"}),
    "team_performance": (t_team_performance, "Per FOS / caller: cases, paid %, visits, visit collections, calls, PTPs for a period.",
                         {"period": "string", "role": "fos|telecaller"}),
    "activity": (t_activity, "List visits or calls for a period (today, yesterday, this_week, this_month, last_month, last_7_days, YYYY-MM-DD..YYYY-MM-DD), optionally for one person.",
                 {"kind": "visits|calls", "period": "string", "person": "string", "limit": "integer"}),
    "attendance": (t_attendance, "Attendance per person for a period: days checked in, late marks, worked hours.", {"period": "string", "person": "string"}),
    "leave": (t_leave, "The user's leave balance; for approvers also pending leave requests.", {}),
    "my_salary": (t_my_salary, "The user's own released payslips (net, gross, deductions).", {}),
}


def run_tool(db, user, name: str, args: dict) -> dict:
    fn = TOOLS.get(name)
    if not fn:
        raise ToolError(f"Unknown tool {name}")
    return fn[0](db, user, args or {})


def mask_value(key: str, v):
    if v in (None, ""):
        return v
    s = str(v)
    k = key.lower()
    if k in ("phone", "alt_phone", "new_phone") or k.endswith("phone"):
        return "XXXXXX" + s[-4:] if len(s) > 4 else "XXXX"
    if k in ("account_no", "card_no", "account"):
        return "XXXX" + s[-4:] if len(s) > 4 else "XXXX"
    if k in ("address", "new_address"):
        return s[:25] + "…" if len(s) > 25 else s
    return v


def mask(obj):
    if isinstance(obj, dict):
        return {k: (mask(v) if isinstance(v, (dict, list)) else mask_value(k, v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [mask(x) for x in obj]
    return obj
