"""AI Assist — the rest of the app's data (Audit Log, MIS, DPR history, legal, settlements, payment
links, notices, devices, team leads). Each group can be switched off in ⚙️ Services → AI Assist.

Every tool reuses the SAME scoping the screens use, so the AI never sees more than the user could:
  • case-linked records  → only rows whose case is in the user's case scope (routers.cases._scope)
  • Audit Log / DPR      → routers.audit_log._scope (admin/HO all · manager branch · team lead own cases)
  • devices              → admin / tech support all · manager own branch
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select

from . import models
from .ai_tools import (IST, LEAD_ROLES, ToolError, _cases, _cases_for, _bank_filter, _dt_range, _f, _names,
                       _period_bounds, _today, visible_staff)

# group key → (Services setting key, label shown in Services)
GROUPS = {
    "audit": ("data_audit", "Audit Log & DPR upload history"),
    "mis": ("data_mis", "MIS breakdowns & collection trends"),
    "legal": ("data_legal", "Litigation & legal notices"),
    "payments": ("data_payments", "Settlements & payment links"),
    "team": ("data_team", "Team leads & portfolios"),
    "admin": ("data_admin", "Devices (login approvals)"),
}


def _case_ids_sel(db, user):
    """SQL selectable of the case ids this user may see (all months they're allowed)."""
    q = _cases(db, user, "all" if user.role in ("admin", "headoffice", "techsupport", "it_support_view") else None)
    return select(q.with_entities(models.Case.id).subquery().c.id)


def _ist(dt):
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST).strftime("%Y-%m-%d %H:%M")


def _rows_out(rows, **extra):
    return {"count": len(rows), "columns": list(rows[0].keys()) if rows else [], "rows": rows, **extra}


# ─────────────────────────────────────────── Audit Log / DPR
def t_audit_log(db, user, args):
    from .routers import audit_log as al
    if user.role not in al.VIEW_ROLES:
        raise ToolError("Your role can't see the Audit Log.")
    a, b = _period_bounds(args.get("period") or "last_7_days")
    s, e = _dt_range(a, b)
    q = al._scope(db.query(models.AuditLog), user, db).filter(models.AuditLog.at >= s, models.AuditLog.at < e)
    if args.get("case_id"):
        q = q.filter(models.AuditLog.case_id == int(args["case_id"]))
    else:
        q = q.filter((models.AuditLog.entity_type.is_(None)) | (models.AuditLog.entity_type != "batch_item"),
                     models.AuditLog.action != "dpr_update")
    if args.get("action"):
        q = q.filter(models.AuditLog.action.ilike(f"%{args['action']}%"))
    if args.get("person"):
        q = q.filter(models.AuditLog.actor_name.ilike(f"%{args['person']}%"))
    if args.get("text"):
        like = f"%{args['text']}%"
        q = q.filter(models.AuditLog.detail.ilike(like) | models.AuditLog.new_value.ilike(like) | models.AuditLog.field.ilike(like))
    total = q.count()
    rows = q.order_by(models.AuditLog.at.desc()).limit(min(int(args.get("limit") or 100), int(args.get("_max", 500)))).all()
    cust = dict(db.query(models.Case.id, models.Case.customer_name).filter(
        models.Case.id.in_({r.case_id for r in rows if r.case_id} or {0})).all())
    by_action = dict(q.with_entities(models.AuditLog.action, func.count(models.AuditLog.id)).group_by(models.AuditLog.action).all())
    out = [{"time": _ist(r.at), "by": r.actor_name, "role": r.actor_role, "action": r.action, "case_id": r.case_id,
            "customer": cust.get(r.case_id), "bank": r.bank, "product": r.product, "field": r.field,
            "before": (r.old_value or "")[:60], "after": (r.new_value or "")[:60], "detail": (r.detail or "")[:160]} for r in rows]
    return _rows_out(out, total_matching=total, **{"from": a.isoformat(), "to": b.isoformat()},
                     by_action=dict(sorted(by_action.items(), key=lambda x: -x[1])[:25]))


def t_dpr_uploads(db, user, args):
    from .routers import audit_log as al
    if user.role not in al.VIEW_ROLES:
        raise ToolError("Your role can't see DPR upload history.")
    a, b = _period_bounds(args.get("period") or "this_month")
    s, e = _dt_range(a, b)
    q = al._scope(db.query(models.AuditLog), user, db).filter(models.AuditLog.action == "dpr_upload",
                                                              models.AuditLog.at >= s, models.AuditLog.at < e)
    if args.get("bank"):
        q = q.filter(models.AuditLog.bank.ilike(f"%{args['bank']}%"))
    own = al._own_case_ids(db, user) if user.role == "teamlead" else None
    rows = []
    for r in q.order_by(models.AuditLog.at.desc()).limit(100).all():
        m = al._light_meta(al._trim_for(db, user, r.meta or {}, own))
        rows.append({"id": r.id, "time": _ist(r.at), "by": r.actor_name, "bank": m.get("bank") or r.bank,
                     "product": m.get("product") or r.product, "file": m.get("file"), "month": m.get("month"),
                     "rows_in_file": m.get("rows_in_file"), "paid": m.get("paid"), "unpaid": m.get("unpaid"),
                     "unmatched": m.get("unmatched"), "collected": m.get("collected"), "changes": m.get("changes_count")})
    return _rows_out(rows, **{"from": a.isoformat(), "to": b.isoformat()},
                     tip="Open Audit Log and click a DPR line to see every case it changed.")


# ─────────────────────────────────────────── MIS
_GROUP_COLS = {
    "bank": lambda: models.Case.bank, "product": lambda: models.Case.product, "bucket": lambda: models.Case.bucket,
    "branch": lambda: models.Case.branch, "cycle": lambda: models.Case.cycle, "month": lambda: models.Case.period,
    "disposition": lambda: models.Case.disposition, "team_lead": lambda: models.Case.team_lead,
    "paid_status": lambda: models.Case.paid_status, "fos": lambda: models.Case.assigned_fos_id,
    "caller": lambda: models.Case.assigned_caller_id,
}


def t_mis_breakdown(db, user, args):
    by = (args.get("group_by") or "bank").lower().strip()
    if by not in _GROUP_COLS:
        raise ToolError("group_by must be one of " + ", ".join(_GROUP_COLS))
    q, note = _cases_for(db, user, args)
    if args.get("bank"):
        q = _bank_filter(q, args["bank"])
    if args.get("product"):
        q = q.filter(models.Case.product.ilike(f"%{args['product']}%"))
    col = _GROUP_COLS[by]()
    rows = (q.with_entities(col, func.count(models.Case.id),
                            func.sum(func.cast(models.Case.paid_status == "PAID", models.Integer)),
                            func.coalesce(func.sum(models.Case.enr), 0),
                            func.coalesce(func.sum(models.Case.received_amount), 0),
                            func.coalesce(func.sum(models.Case.pending_amount), 0),
                            func.coalesce(func.sum(models.Case.total_outstanding), 0))
            .group_by(col).all())
    names = _names(db, [r[0] for r in rows]) if by in ("fos", "caller") else {}
    out = []
    for key, n, paid, enr, rec, pend, tos in rows:
        n, paid = int(n or 0), int(paid or 0)
        label = names.get(key, "Unassigned" if key is None else key) if by in ("fos", "caller") else (key or "—")
        out.append({by: label, "cases": n, "paid": paid, "unpaid": n - paid, "paid_pct": round(100 * paid / n, 1) if n else 0,
                    "enr": round(_f(enr)), "received": round(_f(rec)), "pending": round(_f(pend)), "outstanding": round(_f(tos))})
    out.sort(key=lambda r: -r["cases"])
    tot = {k: sum(r[k] for r in out) for k in ("cases", "paid", "unpaid", "enr", "received", "pending", "outstanding")}
    tot["paid_pct"] = round(100 * tot["paid"] / tot["cases"], 1) if tot["cases"] else 0
    return _rows_out(out[:int(args.get("limit") or 60)], group_by=by, totals=tot, **({"note": note} if note else {}))


def t_collection_trend(db, user, args):
    from .routers.mis import PAY_DISPOSITIONS
    a, b = _period_bounds(args.get("period") or "this_month")
    s, e = _dt_range(a, b)
    ids = _case_ids_sel(db, user)
    calls = (db.query(models.CallLog.created_at, models.CallLog.ptp_amount)
             .filter(models.CallLog.case_id.in_(ids), models.CallLog.disposition.in_(PAY_DISPOSITIONS),
                     models.CallLog.created_at >= s, models.CallLog.created_at < e).all())
    visits = (db.query(models.Visit.created_at, models.Visit.amount_collected)
              .filter(models.Visit.case_id.in_(ids), models.Visit.amount_collected > 0,
                      models.Visit.created_at >= s, models.Visit.created_at < e).all())
    days: dict = {}
    for src, items in (("calls", calls), ("visits", visits)):
        for dt, amt in items:
            d = (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(IST).date().isoformat()
            r = days.setdefault(d, {"date": d, "via_calls": 0.0, "via_visits": 0.0, "payments": 0})
            r["via_" + src] += _f(amt)
            r["payments"] += 1
    rows = []
    for d in sorted(days):
        r = days[d]
        r["total"] = round(r["via_calls"] + r["via_visits"], 2)
        r["via_calls"], r["via_visits"] = round(r["via_calls"], 2), round(r["via_visits"], 2)
        rows.append(r)
    return _rows_out(rows, **{"from": a.isoformat(), "to": b.isoformat()},
                     total_collected=round(sum(r["total"] for r in rows), 2),
                     note="Cash logged on calls (PAYMENT/PAID) and field visits; bank DPR uploads are in dpr_uploads.")


# ─────────────────────────────────────────── legal
def t_legal_cases(db, user, args):
    q = db.query(models.LegalCase)
    if user.role in ("admin", "headoffice", "techsupport", "it_support_view"):
        pass
    elif user.role == "manager":
        q = q.filter((models.LegalCase.branch == user.branch) | models.LegalCase.case_id.in_(_case_ids_sel(db, user)))
    else:
        q = q.filter(models.LegalCase.case_id.in_(_case_ids_sel(db, user)))
    if args.get("status"):
        q = q.filter(models.LegalCase.status == args["status"].lower())
    if args.get("matter_type"):
        q = q.filter(models.LegalCase.matter_type.ilike(f"%{args['matter_type']}%"))
    if args.get("hearing_within_days"):
        t = _today()
        from datetime import timedelta
        q = q.filter(models.LegalCase.next_hearing_date >= t,
                     models.LegalCase.next_hearing_date <= t + timedelta(days=int(args["hearing_within_days"])))
    rows = [{"id": r.id, "case_id": r.case_id, "borrower": r.borrower_name, "bank": r.bank, "matter": r.matter_type,
             "court": r.court, "case_number": r.case_number, "stage": r.stage, "status": r.status,
             "filed": r.filed_date.isoformat() if r.filed_date else None,
             "next_hearing": r.next_hearing_date.isoformat() if r.next_hearing_date else None, "amount": _f(r.amount)}
            for r in q.order_by(models.LegalCase.next_hearing_date.asc()).limit(int(args.get("limit") or 100)).all()]
    by_status: dict = {}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    return _rows_out(rows, by_status=by_status)


def t_legal_notices(db, user, args):
    q = (db.query(models.LegalNotice, models.NoticeBatch)
         .join(models.NoticeBatch, models.NoticeBatch.id == models.LegalNotice.batch_id)
         .filter(models.LegalNotice.case_id.in_(_case_ids_sel(db, user))))
    if args.get("status"):
        q = q.filter(models.LegalNotice.status == args["status"].lower())
    items = q.order_by(models.LegalNotice.created_at.desc()).limit(int(args.get("limit") or 200)).all()
    cust = dict(db.query(models.Case.id, models.Case.customer_name).filter(
        models.Case.id.in_({n.case_id for n, _ in items} or {0})).all())
    rows = [{"ref_no": n.ref_no, "case_id": n.case_id, "customer": cust.get(n.case_id), "batch": b.name, "kind": b.kind,
             "status": n.status, "mode": n.mode, "tracking_no": n.tracking_no,
             "dispatched": n.dispatched_at.isoformat() if n.dispatched_at else None,
             "delivered": n.delivered_at.isoformat() if n.delivered_at else None} for n, b in items]
    by_status: dict = {}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    return _rows_out(rows, by_status=by_status)


# ─────────────────────────────────────────── settlements & payment links
def t_settlements(db, user, args):
    q = db.query(models.SettlementOffer).filter(models.SettlementOffer.case_id.in_(_case_ids_sel(db, user)))
    if args.get("status"):
        q = q.filter(models.SettlementOffer.status == args["status"].lower())
    items = q.order_by(models.SettlementOffer.created_at.desc()).limit(int(args.get("limit") or 100)).all()
    cust = dict(db.query(models.Case.id, models.Case.customer_name).filter(
        models.Case.id.in_({o.case_id for o in items} or {0})).all())
    names = _names(db, [o.created_by for o in items] + [o.approved_by for o in items])
    rows = [{"id": o.id, "case_id": o.case_id, "customer": cust.get(o.case_id), "outstanding": _f(o.outstanding),
             "offer": _f(o.offer_amount), "waiver_pct": _f(o.waiver_pct), "status": o.status, "needs": o.needs_role,
             "instalments": len(o.installments or []), "raised_by": names.get(o.created_by),
             "approved_by": names.get(o.approved_by), "created": _ist(o.created_at)} for o in items]
    return _rows_out(rows, offered_total=round(sum(r["offer"] for r in rows), 2))


def t_payment_links(db, user, args):
    q = db.query(models.PaymentLink).filter(models.PaymentLink.case_id.in_(_case_ids_sel(db, user)))
    if args.get("status"):
        q = q.filter(models.PaymentLink.status == args["status"].lower())
    items = q.order_by(models.PaymentLink.created_at.desc()).limit(int(args.get("limit") or 100)).all()
    cust = dict(db.query(models.Case.id, models.Case.customer_name).filter(
        models.Case.id.in_({l.case_id for l in items} or {0})).all())
    rows = [{"case_id": l.case_id, "customer": cust.get(l.case_id), "amount": _f(l.amount), "status": l.status,
             "paid": _f(l.paid_amount), "provider": l.provider, "created": _ist(l.created_at), "paid_at": _ist(l.paid_at)}
            for l in items]
    return _rows_out(rows, paid_total=round(sum(r["paid"] for r in rows), 2))


# ─────────────────────────────────────────── team leads & portfolios
def t_team_leads(db, user, args):
    if user.role not in LEAD_ROLES:
        raise ToolError("Only team leads and managers can see team-lead summaries.")
    q, note = _cases_for(db, user, args)
    if args.get("bank"):
        q = _bank_filter(q, args["bank"])
    rows = (q.with_entities(models.Case.team_lead, models.Case.bank, models.Case.product, func.count(models.Case.id),
                            func.sum(func.cast(models.Case.paid_status == "PAID", models.Integer)),
                            func.coalesce(func.sum(models.Case.received_amount), 0),
                            func.coalesce(func.sum(models.Case.pending_amount), 0),
                            func.count(func.distinct(models.Case.assigned_fos_id)),
                            func.count(func.distinct(models.Case.assigned_caller_id)))
            .group_by(models.Case.team_lead, models.Case.bank, models.Case.product).all())
    out = []
    for tl, bank, prod, n, paid, rec, pend, nf, nc in rows:
        n, paid = int(n or 0), int(paid or 0)
        out.append({"team_lead": tl or "—", "bank": bank, "product": prod, "cases": n, "paid": paid,
                    "paid_pct": round(100 * paid / n, 1) if n else 0, "received": round(_f(rec)), "pending": round(_f(pend)),
                    "fos": int(nf or 0), "callers": int(nc or 0)})
    out.sort(key=lambda r: (r["team_lead"], -r["cases"]))
    return _rows_out(out, **({"note": note} if note else {}),
                     scope=("your own cases only — use Portfolios to view other leads read-only" if user.role == "teamlead" else "all you can see"))


# ─────────────────────────────────────────── devices
def t_devices(db, user, args):
    if user.role not in ("admin", "techsupport", "it_support_view", "manager", "headoffice"):
        raise ToolError("Your role can't see devices.")
    q = db.query(models.Device, models.User).join(models.User, models.User.id == models.Device.user_id)
    if user.role == "manager":
        q = q.filter(models.User.branch == user.branch)
    st = (args.get("status") or "pending").lower()
    if st == "pending":
        q = q.filter(models.Device.approved.isnot(True))
    elif st == "approved":
        q = q.filter(models.Device.approved.is_(True))
    rows = [{"person": u.name, "role": u.role, "branch": u.branch, "device": (d.label or "")[:80],
             "approved": bool(d.approved), "last_seen": _ist(d.last_seen), "added": _ist(d.created_at)}
            for d, u in q.order_by(models.Device.created_at.desc()).limit(200).all()]
    return _rows_out(rows, status=st)


TOOLS = {
    "audit_log": ("audit", t_audit_log, "Audit Log: who did what and when (edits, payments, reassignments, uploads, logins, approvals…). "
                  "Filters: period (today|yesterday|this_week|this_month|last_month|last_7_days|last_30_days|YYYY-MM-DD..YYYY-MM-DD), "
                  "action (e.g. payment, reassign, edit, bulk_, login, dpr_upload), person (actor name), case_id, text.",
                  {"period": "string", "action": "string", "person": "string", "case_id": "integer", "text": "string", "limit": "integer"}),
    "dpr_uploads": ("audit", t_dpr_uploads, "Bank DPR uploads: when, by whom, which bank/product/month, rows, paid/unpaid/unmatched, collected.",
                    {"period": "string", "bank": "string"}),
    "mis_breakdown": ("mis", t_mis_breakdown, "MIS pivot: cases, paid, paid %, ENR, received, pending grouped by one field. "
                      "group_by = bank|product|bucket|branch|cycle|month|disposition|team_lead|paid_status|fos|caller. "
                      "Optional bank, product, month (YYYY-MM), bucket (current|next|last|all).",
                      {"group_by": "string", "bank": "string", "product": "string", "month": "YYYY-MM", "bucket": "current|next|last|all", "limit": "integer"}),
    "collection_trend": ("mis", t_collection_trend, "Day-by-day cash collected (via calls and via field visits) for a period — ideal for a line chart.",
                         {"period": "string"}),
    "legal_cases": ("legal", t_legal_cases, "Litigation tracker: matters, court, stage, status, next hearing. status = open|closed|won|lost|settled; "
                    "hearing_within_days = upcoming hearings.", {"status": "string", "matter_type": "string", "hearing_within_days": "integer", "limit": "integer"}),
    "legal_notices": ("legal", t_legal_notices, "Legal notices sent: ref no, batch, status (generated|dispatched|delivered|returned), tracking.",
                      {"status": "string", "limit": "integer"}),
    "settlements": ("payments", t_settlements, "Settlement / OTS offers: outstanding, offer, waiver %, status (pending|approved|rejected|accepted|completed), approver.",
                    {"status": "string", "limit": "integer"}),
    "payment_links": ("payments", t_payment_links, "Payment links sent to customers: amount, status (created|paid|partial|expired), paid amount.",
                      {"status": "string", "limit": "integer"}),
    "team_leads": ("team", t_team_leads, "Per team lead and portfolio: cases, paid %, received, pending, FOS and caller counts.",
                   {"bank": "string", "month": "YYYY-MM", "bucket": "current|next|last|all"}),
    "devices": ("admin", t_devices, "Login devices: pending approvals or approved devices per person. status = pending|approved|all.",
                {"status": "string"}),
}


def register(target: dict):
    """Add the tools to ai_tools.TOOLS as (fn, description, params) — the same shape as the built-in ones."""
    for name, (_g, fn, desc, params) in TOOLS.items():
        target[name] = (fn, desc, params)


def disabled_tools(conf: dict) -> set:
    """Tool names switched off in ⚙️ Services → AI Assist (each group defaults ON)."""
    off = set()
    for name, (g, *_rest) in TOOLS.items():
        key = GROUPS[g][0]
        if conf.get(key) is False:
            off.add(name)
    return off
