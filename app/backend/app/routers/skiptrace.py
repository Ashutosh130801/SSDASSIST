"""🔎 Skip tracing add-on — find other ways to reach an unreachable customer, ONLY from your own data:
   • the same customer's other loans/cards (same phone, same account, or same name + pincode) — their numbers and addresses
   • numbers / addresses your callers & FOS updated earlier (new_phone / new_address)
   • the address the FOS's phone detected at a visit (gps_address)
Nothing is fetched from outside sources. Applying a lead saves it as the case's new phone / new address (with history).
"""
from __future__ import annotations

import re
from collections import defaultdict

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import audit, models
from ..addons_common import CASE_WORKERS, case_or_404, need, scoped_cases
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/api/skiptrace", tags=["skiptrace"])
UNREACHABLE = ("RNR", "SWITCHED OFF", "SWITCH OFF", "NOT REACHABLE", "NR", "NC", "WRONG NO", "WRONG NUMBER", "NUMBER NOT IN USE", "SKIP")


def _digits(p):
    d = re.sub(r"\D", "", str(p or ""))
    return d[-10:] if len(d) >= 10 else ""


def leads_for(db, case) -> dict:
    phones0 = {_digits(case.phone), _digits(case.alt_phone), _digits(case.new_phone)} - {""}
    conds = []
    if phones0:
        conds += [models.Case.phone.in_(list(phones0)), models.Case.alt_phone.in_(list(phones0))]
        conds += [models.Case.phone.like(f"%{p}") for p in phones0]
    if case.account_no:
        conds.append(models.Case.account_no == case.account_no)
    if case.customer_name and case.pincode:
        conds.append((func.upper(models.Case.customer_name) == case.customer_name.upper()) & (models.Case.pincode == case.pincode))
    rel = db.query(models.Case).filter(models.Case.id != case.id, or_(*conds)).limit(200).all() if conds else []
    phones, addrs = defaultdict(set), defaultdict(set)
    for r in rel + [case]:
        src = "this case (updated by team)" if r.id == case.id else f"{r.bank or ''} {r.product or ''} {r.period or ''}".strip()
        for f in ("phone", "alt_phone", "new_phone"):
            d = _digits(getattr(r, f))
            if d and (r.id != case.id or f == "new_phone"):
                phones[d].add(src + ("" if f == "phone" else f" ({f.replace('_', ' ')})"))
        for f in ("address", "address2", "address3", "new_address"):
            a = (getattr(r, f) or "").strip()
            if a and (r.id != case.id or f == "new_address"):
                addrs[a].add(src)
    for v in db.query(models.Visit).filter(models.Visit.case_id.in_([r.id for r in rel] + [case.id]),
                                           models.Visit.gps_address.isnot(None)).limit(50).all():
        if v.gps_address and (v.person_moved or v.location_correct is False):
            addrs[v.gps_address.strip()].add("address where a FOS found the customer (visit GPS)")
    known = {_digits(case.phone)}
    bad = {_digits(case.phone)} if (case.disposition or "").upper() in ("WRONG NO", "WRONG NUMBER") else set()
    return {"phones": [{"value": p, "sources": sorted(s), "is_current": p in known, "wrong": p in bad} for p, s in phones.items()
                       if p not in known],
            "addresses": [{"value": a, "sources": sorted(s)} for a, s in addrs.items()
                          if a not in {(case.address or "").strip(), (case.address2 or "").strip(), (case.address3 or "").strip()}],
            "related_cases": [{"id": r.id, "bank": r.bank, "product": r.product, "period": r.period, "status": r.paid_status} for r in rel[:30]]}


@router.get("/case/{case_id}")
def for_case(case_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, CASE_WORKERS, "skip tracing")
    case = case_or_404(db, user, case_id)
    out = leads_for(db, case)
    # related cases outside the user's scope: keep the leads, hide the case links
    allowed = {i for (i,) in scoped_cases(db, user, all_periods=True).filter(
        models.Case.id.in_([r["id"] for r in out["related_cases"]] or [-1])).with_entities(models.Case.id)}
    out["related_cases"] = [r for r in out["related_cases"] if r["id"] in allowed]
    audit.record(db, user, "skiptrace.view", case, detail=f"{len(out['phones'])} phone, {len(out['addresses'])} address leads")
    db.commit()
    return out


@router.get("/unreachable")
def unreachable(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Unpaid cases whose last outcome says we can't reach them, with how many leads each has."""
    need(user, CASE_WORKERS, "skip tracing")
    q = scoped_cases(db, user).filter(func.upper(func.coalesce(models.Case.paid_status, "UNPAID")) != "PAID",
                                      func.upper(models.Case.disposition).in_(UNREACHABLE))
    rows = []
    for c in q.limit(500).all():
        l = leads_for(db, c)
        rows.append({"case_id": c.id, "customer": c.customer_name, "bank": c.bank, "product": c.product, "disposition": c.disposition,
                     "phone_leads": len(l["phones"]), "address_leads": len(l["addresses"])})
    rows.sort(key=lambda r: -(r["phone_leads"] + r["address_leads"]))
    return rows


@router.post("/case/{case_id}/apply")
def apply(case_id: int, body: dict = Body(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    need(user, CASE_WORKERS, "skip tracing")
    case = case_or_404(db, user, case_id)
    from .cases import _ensure_open
    _ensure_open(case, user)
    lead = leads_for(db, case)
    phone, addr = body.get("phone"), body.get("address")
    if phone:
        if phone not in {p["value"] for p in lead["phones"]}:
            raise HTTPException(400, "That number is not one of the leads")
        audit.record(db, user, "contact_update", case, field="new_phone", old=case.new_phone, new=phone, detail="Skip-trace lead applied")
        case.new_phone = phone
    if addr:
        if addr not in {a["value"] for a in lead["addresses"]}:
            raise HTTPException(400, "That address is not one of the leads")
        audit.record(db, user, "contact_update", case, field="new_address", old=case.new_address, new=addr, detail="Skip-trace lead applied")
        case.new_address = addr
    if not (phone or addr):
        raise HTTPException(400, "Pick a phone or an address")
    from datetime import datetime, timezone
    case.new_contact_by, case.new_contact_at = user.name, datetime.now(timezone.utc)
    audit.stamp_case(case, user)
    db.commit()
    return {"ok": True}
