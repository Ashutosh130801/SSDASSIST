import os
import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user, require_roles
from ..storage import save_photo, resolve as resolve_photo
from .. import audit

router = APIRouter(prefix="/api/visits", tags=["visits"])


def _vt_loads(s):
    from .. import visit_trust as _vt
    return _vt.loads(s)
IST = timezone(timedelta(hours=5, minutes=30))


@router.post("", response_model=schemas.VisitOut)
async def create_visit(
    case_id: int = Form(...),
    latitude: float | None = Form(None),
    longitude: float | None = Form(None),
    gps_accuracy: float | None = Form(None),
    location_correct: bool | None = Form(None),
    person_moved: bool = Form(False),
    paid: bool = Form(False),
    amount_collected: str = Form("0"),
    norm_stab: str | None = Form(None),
    disposition: str | None = Form(None),
    ptp_date: str | None = Form(None),
    note: str | None = Form(None),
    address_slot: str | None = Form(None),      # '1' / '2' / '3' / 'new' — which address he visited
    gps_mock: bool | None = Form(None),         # phone says the location came from a fake-GPS app
    gps_fix_age_s: float | None = Form(None),   # age of the GPS fix at capture time
    gps_pincode: str | None = Form(None),       # pincode where the photo was taken
    gps_address: str | None = Form(None),       # address the phone detected at the photo spot
    gps_city: str | None = Form(None),          # city of that detected address
    photo: UploadFile | None = File(None),
    payment_photo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("fos", "admin")),
):
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    # A FOS may visit a case allocated to him OR one JOINTLY allocated to him (secondary FOS sent
    # to a new address). Either is allowed; anything else is blocked.
    _is_joint_fos = bool(user.role == "fos" and case.joint_fos_id == user.id and case.assigned_fos_id != user.id)
    if user.role == "fos" and case.assigned_fos_id != user.id and not _is_joint_fos:
        raise HTTPException(status_code=403, detail="This case is not assigned to you")
    # A field visit is proof-of-visit / an observation — always allow it, even when the case is
    # already PAID or has closed for the month (the FOS may still need to record a doorstep visit,
    # a PTP, an address correction, or a "door locked" note). Only an ESCALATED case (handed up to
    # the team lead / manager) stays locked for the field officer. The month-closed book is still
    # frozen for MONEY: a payment isn't posted on a closed case (guarded below), but the visit,
    # disposition, note, photo and GPS pin are recorded normally.
    # Escalated OR closed (cycle / month-end) cases are locked for the FOS & caller — no visits,
    # no logs, no changes. Admin / manager / head office can still record corrections.
    from .cases import _case_closed, _ensure_open
    _ensure_open(case, user)
    _closed = _case_closed(case)

    photo_path = None
    if photo is not None:
        content = await photo.read()
        photo_path = save_photo(content, photo.filename or "", photo.content_type or "image/jpeg")
    # Optional payment screenshot the customer shared (proof of payment), stored alongside the visit.
    payment_photo_path = None
    if payment_photo is not None:
        pcontent = await payment_photo.read()
        payment_photo_path = save_photo(pcontent, payment_photo.filename or "", payment_photo.content_type or "image/jpeg")

    # Trust score: was the photo really taken at the customer's (chosen) address?
    from .. import visit_trust as _vt
    slot = (address_slot or "1").strip().lower()
    if slot not in ("1", "2", "3", "new"):
        slot = "1"
    trust = _vt.evaluate(db, case, user.id, latitude, longitude, accuracy=gps_accuracy, slot_key=slot,
                         mock=bool(gps_mock), fix_age_s=gps_fix_age_s,
                         gps_pincode=(gps_pincode or "").strip()[:10] or None,
                         gps_address=(gps_address or "").strip()[:400] or None,
                         gps_city=(gps_city or "").strip()[:80] or None)
    slot = trust["slot"]
    dist_m = trust["distance_m"]

    amt = Decimal(str(amount_collected or "0"))
    if _closed and paid and amt > 0:
        # Closed-for-the-month book is frozen for money: keep the FOS's report in the note, but don't
        # store it as a collection — otherwise FTD/MTD/MIS would count cash that Received never got.
        note = ((note or "").strip() + f" [Reported paid ₹{amt} after case closed — not posted; the next DPR will reflect it if the bank confirms]").strip()
        paid, amt = False, Decimal("0")
    visit = models.Visit(
        case_id=case_id, officer_id=user.id, latitude=latitude, longitude=longitude,
        gps_accuracy=gps_accuracy, distance_from_case_m=dist_m, photo_path=photo_path,
        payment_photo_path=payment_photo_path,
        location_correct=location_correct, person_moved=person_moved, paid=paid,
        amount_collected=amt, disposition=disposition, note=note,
        address_slot=slot, gps_mock=bool(gps_mock), gps_fix_age_s=gps_fix_age_s,
        gps_pincode=(gps_pincode or "").strip()[:10] or None,
        gps_address=(gps_address or "").strip()[:400] or None,
        gps_city=(gps_city or "").strip()[:80] or None,
        trust_level=trust["level"], trust_reasons=_vt.dumps(trust["reasons"]),
    )
    db.add(visit)

    # roll the visit up into the case
    case.status = "in_progress"
    case.visited = True                       # FOS logged a visit → MIS "VISITED"
    if disposition:
        case.disposition = disposition
    if person_moved:
        case.disposition = "MOVED"
    if paid and amt > 0 and not _closed:          # closed-month book is frozen for money
        case.received_amount = (Decimal(case.received_amount or 0) + amt)
        if norm_stab:                         # credit-card: NORM or STAB paid
            ns = norm_stab.upper()
            case.norm_stab = "ROLLBACK" if "ROLL" in ns else ("STAB" if "STAB" in ns else ("NORM" if "NORM" in ns else case.norm_stab))
        # Single source of truth: PAID only when the NORM/STAB settlement (or full outstanding
        # for plain cases) is reached; below that it stays PARTIAL and is excluded from cash.
        from .. import paymath
        paymath.recompute(case)
        # Joint allocation: the moment the JOINT (secondary) FOS logs a paid visit, the collection
        # credit for this case moves to him. The case stays allocated to the primary FOS; from now
        # on collection_fos_id(case) returns the joint FOS, so the collected cash counts for him.
        if _is_joint_fos and case.joint_collected_at is None:
            case.joint_collected_at = datetime.now(IST)
    # Doorstep pin learning. The FOS's GPS becomes that address's confirmed pin ONLY when the visit is
    # trustworthy (no fake GPS, good fix, near the address, route agrees) — either because he ticked
    # "location correct", or automatically on a verified PAID visit (customer was there). A doubtful
    # visit never moves the pin, so a FOS can't "re-home" a customer to where he sits.
    _good_fix = latitude is not None and longitude is not None and not gps_mock and (gps_accuracy or 999) <= 50
    if _good_fix and trust["level"] == "ok" and (location_correct or (paid and amt > 0)):
        _vt.set_slot_pin(case, slot, latitude, longitude)
    elif location_correct and latitude and longitude:
        trust["reasons"].append({"sev": "info", "text": "‘Location correct’ not applied — visit not verified"})
        visit.trust_reasons = _vt.dumps(trust["reasons"])

    # Roll the case forward so it re-surfaces on the right day and sinks in today's view.
    try:
        pd = datetime.strptime(ptp_date, "%Y-%m-%d").date() if ptp_date else None
    except ValueError:
        pd = None
    if case.paid_status == "PAID":                              # settled (full or NORM/STAB) → out of the queue
        case.follow_up_date = None
    else:
        # unpaid / partial after a visit → carry to the promised date, else next working day
        case.follow_up_date = pd or (datetime.now(IST).date() + timedelta(days=1))
        if pd or (disposition or "").upper() == "PTP":       # RTP = Refuse to Pay, not a promise
            case.status = "ptp"
    audit.record(db, user, "visit", case, new=disposition,
                 detail=f"Field visit — {disposition or 'logged'}"
                        + (f", paid ₹{amt}" if (paid and amt > 0) else "")
                        + (f", {int(dist_m)}m from case" if dist_m else "")
                        + (f" · {_vt.LABEL[trust['level']]}" if trust["level"] != "ok" else ""))
    audit.stamp_case(case, user)
    from .notifications import notify_case_change
    notify_case_change(db, case, user,
                       f"Field visit — {disposition or 'logged'}" + (f" · paid ₹{amt}" if (paid and amt > 0) else "")
                       + (f" · Note: {note}" if (note or "").strip() else ""),
                       ntype="visit")
    if trust["level"] == "suspicious":
        _alert_suspicious(db, case, user, trust)
    from .. import presence as _presence
    _presence.touch(db, user.id, active=True)   # logging a visit = active
    db.commit()
    db.refresh(visit)
    from .realtime import notify_data_changed
    notify_data_changed(case.bank, case.product)
    visit.photo_path = resolve_photo(visit.photo_path)
    visit.payment_photo_path = resolve_photo(visit.payment_photo_path)
    return visit


def _supervisors(db, case):
    """Team lead of the case + branch manager(s) + head office + admins — never the FOS/caller."""
    from sqlalchemy import func, or_
    ids = set()
    tl = (case.team_lead or "").strip().lower()
    if tl:
        for (uid,) in db.query(models.User.id).filter(
                or_(func.lower(func.trim(models.User.name)) == tl, func.lower(func.trim(models.User.emp_code)) == tl)).all():
            ids.add(uid)
    conds = [models.User.role.in_(("headoffice", "admin"))]
    if case.branch:
        conds.append((models.User.role == "manager") & (models.User.branch == case.branch))
    for (uid,) in db.query(models.User.id).filter(models.User.is_active.is_(True), or_(*conds)).all():
        ids.add(uid)
    ids.discard(case.assigned_fos_id); ids.discard(case.assigned_caller_id)
    return ids


def _alert_suspicious(db, case, fos, trust):
    from .notifications import push
    from .. import visit_trust as _vt
    who = case.customer_name or case.account_no or f"Case #{case.id}"
    body = f"{fos.name} ({fos.emp_code or '-'}) · {who}\n" + _vt.reasons_text(trust["reasons"])
    for uid in _supervisors(db, case):
        try:
            push(db, uid, f"🚩 Suspicious visit — {fos.name}", body[:900], case_id=case.id,
                 ntype="suspicious_visit", by_name=fos.name)
        except Exception:
            pass


@router.get("/officer/{officer_id}/day")
def officer_day(officer_id: int, date: str | None = None, db: Session = Depends(get_db),
                actor: models.User = Depends(get_current_user)):
    """A field officer's visits for a given day (IST), each joined to its case with the
    payment collected and the full log — for the live-map tags and the day Excel view."""
    u = db.query(models.User).filter(models.User.id == officer_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Officer not found")
    if actor.role == "manager" and u.branch != actor.branch:
        raise HTTPException(status_code=403, detail="Not in your branch")
    if actor.role in ("fos", "telecaller", "backend") and actor.id != u.id:
        raise HTTPException(status_code=403, detail="Not allowed")

    try:
        d = date and datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        d = None
    if not d:
        d = datetime.now(IST).date()
    start = datetime.combine(d, time.min, tzinfo=IST).astimezone(timezone.utc)
    end = start + timedelta(days=1)

    visits = (db.query(models.Visit)
              .filter(models.Visit.officer_id == officer_id,
                      models.Visit.created_at >= start, models.Visit.created_at < end)
              .order_by(models.Visit.created_at.asc()).all())
    cids = [v.case_id for v in visits]
    cases = {c.id: c for c in db.query(models.Case).filter(models.Case.id.in_(cids)).all()} if cids else {}

    def as_ist(dt):
        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(IST).strftime("%H:%M") if dt else ""

    out = []
    for v in visits:
        c = cases.get(v.case_id)
        out.append({
            "id": v.id, "case_id": v.case_id, "time": as_ist(v.created_at),
            "lat": v.latitude, "lng": v.longitude,
            "customer": c.customer_name if c else None, "account": c.account_no if c else None,
            "bank": c.bank if c else None, "product": c.product if c else None,
            "phone": c.phone if c else None, "address": c.address if c else None,
            "disposition": v.disposition, "paid": bool(v.paid),
            "amount": float(v.amount_collected or 0), "norm_stab": (c.norm_stab if c else None),
            "person_moved": bool(v.person_moved),
            "location_correct": v.location_correct,
            "off_location": (v.trust_level in ("check", "suspicious")) if v.trust_level else
                            (v.distance_from_case_m is not None and v.distance_from_case_m > 300),
            "trust": v.trust_level, "trust_reasons": _vt_loads(v.trust_reasons),
            "address_slot": v.address_slot, "gps_accuracy": v.gps_accuracy,
            "review_status": v.review_status, "reviewed_by": v.reviewed_by,
            "distance_m": v.distance_from_case_m, "note": v.note,
            "photo": resolve_photo(v.photo_path),
            "payment_photo": resolve_photo(v.payment_photo_path),
        })
    return {"officer": {"id": u.id, "name": u.name, "branch": u.branch}, "date": d.isoformat(),
            "count": len(out), "collected": round(sum(x["amount"] for x in out), 2), "visits": out}


@router.get("/case/{case_id}", response_model=list[schemas.VisitOut])
def visits_for_case(case_id: int, db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)):
    q = db.query(models.Visit).filter(models.Visit.case_id == case_id)
    if user.role == "fos":
        q = q.filter(models.Visit.officer_id == user.id)
    rows = q.order_by(models.Visit.created_at.desc()).all()
    for v in rows:
        v.photo_path = resolve_photo(v.photo_path)
        v.payment_photo_path = resolve_photo(v.payment_photo_path)
    return rows


# ── Fake-visit detection: flagged-visit report, review, re-score ─────────────────────────────────
def _range(start, end):
    try:
        d1 = datetime.strptime(start, "%Y-%m-%d").date() if start else datetime.now(IST).date().replace(day=1)
        d2 = datetime.strptime(end, "%Y-%m-%d").date() if end else datetime.now(IST).date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")
    s = datetime.combine(d1, time.min, tzinfo=IST).astimezone(timezone.utc)
    e = datetime.combine(d2, time.min, tzinfo=IST).astimezone(timezone.utc) + timedelta(days=1)
    return d1, d2, s, e


_SLOT_LABEL = {"1": "Address 1", "2": "Address 2", "3": "Address 3", "new": "New address"}


@router.get("/flagged")
def flagged_visits(start: str | None = None, end: str | None = None, officer_id: int | None = None,
                   level: str = "flagged", format: str = "json", db: Session = Depends(get_db),
                   user: models.User = Depends(require_roles("admin", "headoffice", "manager", "teamlead", "it_support_view"))):
    """Visits flagged by the trust score in a date range (IST), within the viewer's scope, plus a
    per-FOS summary (total / verified / check / suspicious). level = flagged | suspicious | check | all."""
    from .cases import _scope
    from .. import visit_trust as _vt
    d1, d2, s, e = _range(start, end)
    from sqlalchemy import select
    case_ids = select(_scope(db.query(models.Case.id), user, include_removed=True, all_periods=True).subquery().c.id)
    q = (db.query(models.Visit).filter(models.Visit.created_at >= s, models.Visit.created_at < e,
                                       models.Visit.case_id.in_(case_ids)))
    if officer_id:
        q = q.filter(models.Visit.officer_id == officer_id)
    visits = q.order_by(models.Visit.created_at.desc()).all()
    users = {u.id: u for u in db.query(models.User).filter(
        models.User.id.in_({v.officer_id for v in visits} or {0})).all()}
    cases = {c.id: c for c in db.query(models.Case).filter(
        models.Case.id.in_({v.case_id for v in visits} or {0})).all()}

    summary = {}
    rows = []
    for v in visits:
        lv = v.trust_level or "unscored"
        u = users.get(v.officer_id)
        sm = summary.setdefault(v.officer_id, {"officer_id": v.officer_id, "name": u.name if u else "?",
                                               "emp_code": u.emp_code if u else None, "visits": 0,
                                               "ok": 0, "check": 0, "suspicious": 0, "unscored": 0})
        sm["visits"] += 1
        sm[lv if lv in sm else "unscored"] += 1
        keep = (level == "all" or (level == "flagged" and lv in ("check", "suspicious")) or level == lv)
        if not keep:
            continue
        c = cases.get(v.case_id)
        slot = v.address_slot or "1"
        addr = None
        if c:
            addr = {"1": c.address, "2": c.address2, "3": c.address3, "new": c.new_address}.get(slot)
        rows.append({
            "id": v.id, "case_id": v.case_id, "officer_id": v.officer_id,
            "officer": u.name if u else None, "emp_code": u.emp_code if u else None,
            "at": v.created_at.astimezone(IST).strftime("%d-%b-%Y %H:%M") if v.created_at else "",
            "customer": c.customer_name if c else None, "account": c.account_no if c else None,
            "bank": c.bank if c else None, "product": c.product if c else None,
            "address_slot": slot, "address_label": _SLOT_LABEL.get(slot, slot), "address": addr,
            "disposition": v.disposition, "paid": bool(v.paid), "amount": float(v.amount_collected or 0),
            "lat": v.latitude, "lng": v.longitude, "gps_accuracy": v.gps_accuracy,
            "distance_m": v.distance_from_case_m, "level": lv, "reasons": _vt.loads(v.trust_reasons),
            "gps_address": v.gps_address, "gps_pincode": v.gps_pincode,
            "photo": resolve_photo(v.photo_path),
            "review_status": v.review_status, "reviewed_by": v.reviewed_by, "review_note": v.review_note,
        })
    summ = sorted(summary.values(), key=lambda x: (-x["suspicious"], -x["check"], x["name"]))
    for sm in summ:
        scored = sm["visits"] - sm["unscored"]
        sm["flagged_pct"] = round(100.0 * (sm["check"] + sm["suspicious"]) / scored, 1) if scored else 0.0
    if format == "xlsx":
        return _flagged_xlsx(rows, summ, d1, d2)
    return {"start": d1.isoformat(), "end": d2.isoformat(), "summary": summ, "visits": rows}


def _flagged_xlsx(rows, summ, d1, d2):
    import io
    from fastapi.responses import StreamingResponse
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from .. import visit_trust as _vt
    wb = Workbook()
    ws = wb.active
    ws.title = "FOS summary"
    hdr = PatternFill("solid", fgColor="1F4E79")
    ws.append(["FOS", "Emp ID", "Visits", "✅ Verified", "⚠️ Check", "🚩 Suspicious", "Not scored", "Flagged %"])
    for sm in summ:
        ws.append([sm["name"], sm["emp_code"], sm["visits"], sm["ok"], sm["check"], sm["suspicious"],
                   sm["unscored"], sm["flagged_pct"]])
    ws2 = wb.create_sheet("Flagged visits")
    ws2.append(["Date/time", "FOS", "Emp ID", "Level", "Reasons", "Customer", "Account", "Bank", "Product",
                "Visited", "Customer address", "Detected at photo", "Photo PIN", "Outcome", "Paid ₹", "Distance m", "GPS ±m", "Map", "Photo",
                "Review", "Reviewed by", "Review note"])
    fills = {"suspicious": "F8CBAD", "check": "FFE699", "ok": "C6EFCE"}
    for r in rows:
        ws2.append([r["at"], r["officer"], r["emp_code"], _vt.LABEL.get(r["level"], r["level"]),
                    _vt.reasons_text(r["reasons"]), r["customer"], r["account"], r["bank"], r["product"],
                    r["address_label"], r["address"], r["gps_address"], r["gps_pincode"], r["disposition"], r["amount"] or None,
                    r["distance_m"], r["gps_accuracy"],
                    f"https://maps.google.com/?q={r['lat']},{r['lng']}" if r["lat"] is not None else None,
                    r["photo"], r["review_status"], r["reviewed_by"], r["review_note"]])
        f = fills.get(r["level"])
        if f:
            ws2.cell(ws2.max_row, 4).fill = PatternFill("solid", fgColor=f)
    for sh, widths in ((ws, [24, 12, 9, 12, 11, 14, 11, 11]),
                       (ws2, [17, 22, 11, 15, 60, 22, 18, 10, 12, 12, 40, 40, 10, 16, 10, 11, 9, 30, 30, 10, 16, 30])):
        for cell in sh[1]:
            cell.font = Font(bold=True, color="FFFFFF"); cell.fill = hdr
            cell.alignment = Alignment(wrap_text=True, vertical="center")
        for i, w in enumerate(widths, 1):
            sh.column_dimensions[sh.cell(1, i).column_letter].width = w
        sh.freeze_panes = "A2"
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    name = f"flagged_visits_{d1:%Y%m%d}_{d2:%Y%m%d}.xlsx"
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/{visit_id}/review")
def review_visit(visit_id: int, body: dict, db: Session = Depends(get_db),
                 user: models.User = Depends(require_roles("admin", "headoffice", "manager", "teamlead"))):
    """TL/HO marks a flagged visit as genuine or fake (with a note) after checking it."""
    from .cases import _scope
    v = db.query(models.Visit).filter(models.Visit.id == visit_id).first()
    if not v or not _scope(db.query(models.Case.id), user, include_removed=True, all_periods=True).filter(
            models.Case.id == v.case_id).first():
        raise HTTPException(status_code=404, detail="Visit not found")
    st = (body.get("status") or "").strip().lower()
    if st not in ("genuine", "fake", ""):
        raise HTTPException(status_code=400, detail="status must be genuine or fake")
    v.review_status = st or None
    v.review_note = (body.get("note") or "").strip()[:500] or None
    v.reviewed_by = user.name if st else None
    v.reviewed_at = datetime.now(IST) if st else None
    case = db.query(models.Case).filter(models.Case.id == v.case_id).first()
    audit.record(db, user, "visit_review", case, new=st or "cleared",
                 detail=f"Visit #{v.id} marked {st or 'unreviewed'}" + (f" · {v.review_note}" if v.review_note else ""))
    db.commit()
    return {"ok": True, "id": v.id, "review_status": v.review_status, "reviewed_by": v.reviewed_by}


@router.post("/rescore")
def rescore_visits(body: dict | None = None, db: Session = Depends(get_db),
                   user: models.User = Depends(require_roles("admin", "headoffice"))):
    """Score past visits (default: this month) with the trust checks. Phone-only signals (fake-GPS,
    fix age, pincode) exist only for visits logged with the new app; the rest are checked fully."""
    from .. import visit_trust as _vt
    body = body or {}
    _, _, s, e = _range(body.get("start"), body.get("end"))
    only_new = bool(body.get("only_unscored", False))
    q = db.query(models.Visit).filter(models.Visit.created_at >= s, models.Visit.created_at < e)
    if only_new:
        q = q.filter(models.Visit.trust_level.is_(None))
    counts = {"ok": 0, "check": 0, "suspicious": 0}
    cases = {}
    for v in q.all():
        c = cases.get(v.case_id) or db.query(models.Case).filter(models.Case.id == v.case_id).first()
        if not c:
            continue
        cases[c.id] = c
        t = _vt.evaluate(db, c, v.officer_id, v.latitude, v.longitude, accuracy=v.gps_accuracy,
                         slot_key=v.address_slot or "1", mock=bool(v.gps_mock), fix_age_s=v.gps_fix_age_s,
                         gps_pincode=v.gps_pincode, at=v.created_at, exclude_visit_id=v.id,
                         gps_address=v.gps_address, gps_city=v.gps_city)
        v.trust_level, v.trust_reasons = t["level"], _vt.dumps(t["reasons"])
        v.address_slot = t["slot"]
        v.distance_from_case_m = t["distance_m"]
        counts[t["level"]] += 1
    db.commit()
    return {"scored": sum(counts.values()), **counts}


@router.get("/geo-quality")
def geo_quality(db: Session = Depends(get_db),
                user: models.User = Depends(require_roles("admin", "headoffice", "it_support_view"))):
    """How precisely customer addresses are placed on the map (active cases), per address slot.
    field = FOS doorstep-confirmed · rooftop = building · locality = street/area ·
    pincode = pincode centre · city · none = not found · not_tried."""
    from sqlalchemy import func
    base = db.query(models.Case).filter(models.Case.removed.isnot(True))
    out = {}
    def tally(has_addr, prec_col, lat_col, extra_field=None):
        rows = (base.filter(has_addr)
                .with_entities(prec_col, lat_col.isnot(None), *( [extra_field] if extra_field is not None else []))
                .all())
        t = {}
        for r in rows:
            prec, pinned = r[0], r[1]
            src = r[2] if len(r) > 2 else None
            k = "field" if src == "field" else ((prec or "none") if pinned else "not_tried" if prec is None else (prec or "none"))
            t[k] = t.get(k, 0) + 1
        return t
    C = models.Case
    out["address1"] = tally((C.address.isnot(None)) | (C.pincode.isnot(None)), C.geo_precision, C.latitude, C.location_source)
    out["address2"] = tally((C.address2.isnot(None)) | (C.pincode2.isnot(None)), C.geo_precision2, C.latitude2)
    out["address3"] = tally((C.address3.isnot(None)) | (C.pincode3.isnot(None)), C.geo_precision3, C.latitude3)
    return out
