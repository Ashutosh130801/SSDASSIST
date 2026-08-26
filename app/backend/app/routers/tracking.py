import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from openpyxl import Workbook

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user, require_roles

router = APIRouter(prefix="/api/tracking", tags=["tracking"])

# Roles allowed to view a field officer's route history / map.
HISTORY_ROLES = ("admin", "manager", "headoffice", "teamlead")


def _authorize_officer_view(db: Session, viewer: models.User, officer_id: int):
    """Managers may only view officers in their branch; team leads only their own
    team members. Admin, head office & tech-support see everyone. Raises 403 otherwise."""
    if viewer.role in ("admin", "headoffice", "techsupport"):
        return
    if viewer.role == "manager":
        off = db.query(models.User).filter(models.User.id == officer_id).first()
        if not off or off.branch != viewer.branch:
            raise HTTPException(status_code=403, detail="Not in your branch")
        return
    if viewer.role == "teamlead":
        from .cases import _scope_user_ids
        if officer_id not in set(_scope_user_ids(db, viewer)):
            raise HTTPException(status_code=403, detail="Not one of your team members")
        return
    raise HTTPException(status_code=403, detail="Not allowed")


@router.post("/ping", response_model=schemas.PingOut)
def ping(body: schemas.PingCreate, db: Session = Depends(get_db),
         user: models.User = Depends(require_roles("fos", "admin"))):
    p = models.LocationPing(
        officer_id=user.id, latitude=body.latitude, longitude=body.longitude,
        accuracy=body.accuracy, speed=body.speed, active_case_id=body.active_case_id,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _extract_coords(obj):
    """Pull {latitude, longitude, accuracy, speed} out of a Transistor location object,
    which may be shaped as {coords:{...}} or nested under {location:{coords:{...}}}."""
    if not isinstance(obj, dict):
        return None
    c = obj.get("coords") or (obj.get("location") or {}).get("coords") or obj
    lat, lng = c.get("latitude"), c.get("longitude")
    if lat is None or lng is None:
        return None
    return dict(latitude=float(lat), longitude=float(lng),
                accuracy=c.get("accuracy"), speed=c.get("speed"))


@router.post("/ping-native")
async def ping_native(request: Request, db: Session = Depends(get_db),
                      user: models.User = Depends(require_roles("fos", "admin"))):
    """Receives locations POSTed directly by the native Android background-geolocation
    service (Transistor auto-sync). Accepts a single location or a batch, in the plugin's
    default shape. Stores each as a LocationPing for the authenticated officer."""
    try:
        data = await request.json()
    except Exception:
        data = None
    items = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        loc = data.get("location", data)
        items = loc if isinstance(loc, list) else [loc]
    stored = 0
    for it in items:
        c = _extract_coords(it)
        if not c:
            continue
        db.add(models.LocationPing(officer_id=user.id, **c))
        stored += 1
    db.commit()
    return {"stored": stored}


@router.get("/live", response_model=list[schemas.OfficerLocation])
def live(minutes: int = 30, db: Session = Depends(get_db),
         viewer: models.User = Depends(require_roles("admin", "manager", "headoffice"))):
    """Latest known position of every field officer seen in the last N minutes.
    A branch manager only sees officers in their own branch."""
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    sub = (
        db.query(models.LocationPing.officer_id,
                 func.max(models.LocationPing.created_at).label("mx"))
        .filter(models.LocationPing.created_at >= since)
        .group_by(models.LocationPing.officer_id)
        .subquery()
    )
    q = (
        db.query(models.LocationPing, models.User.name, models.User.branch, models.User.banks)
        .join(sub, (models.LocationPing.officer_id == sub.c.officer_id) &
              (models.LocationPing.created_at == sub.c.mx))
        .join(models.User, models.User.id == models.LocationPing.officer_id)
    )
    if viewer.role == "manager":
        q = q.filter(models.User.branch == viewer.branch)
    rows = q.all()
    return [
        schemas.OfficerLocation(
            officer_id=p.officer_id, name=name, latitude=p.latitude, longitude=p.longitude,
            accuracy=p.accuracy, active_case_id=p.active_case_id, last_seen=p.created_at,
            branch=branch, banks=banks or [],
        )
        for p, name, branch, banks in rows
    ]


@router.get("/officer/{officer_id}/trail", response_model=list[schemas.PingOut])
def trail(officer_id: int, minutes: int = 240, db: Session = Depends(get_db),
          viewer: models.User = Depends(require_roles(*HISTORY_ROLES))):
    _authorize_officer_view(db, viewer, officer_id)
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    return (
        db.query(models.LocationPing)
        .filter(models.LocationPing.officer_id == officer_id,
                models.LocationPing.created_at >= since)
        .order_by(models.LocationPing.created_at.asc())
        .all()
    )


# ---------------- 90-day (3-month) route history ----------------
IST = timezone(timedelta(hours=5, minutes=30))   # India Standard Time


def _ist_today():
    return datetime.now(IST).date()
RETENTION_DAYS = 90


def _as_utc(dt: datetime) -> datetime:
    """Normalise a possibly-naive stored datetime to aware UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def prune_old_pings(db: Session, days: int = RETENTION_DAYS) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    deleted = (
        db.query(models.LocationPing)
        .filter(models.LocationPing.created_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted


def _haversine_km(a, b):
    import math
    r = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dphi = math.radians(b[0] - a[0])
    dl = math.radians(b[1] - a[1])
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def clean_route(pings, max_accuracy_m=80.0, max_speed_kmh=140.0):
    """Drop GPS junk so a stationary/slow officer doesn't draw spikes across the map:
      * fixes with poor reported accuracy (drift, indoor, cold start), and
      * 'teleport' outliers — a big jump in a tiny time gap (impossible speed).
    Keeps chronological order; compares each candidate to the last KEPT good point."""
    kept = []
    for p in pings:
        if p.latitude is None or p.longitude is None:
            continue
        if p.accuracy is not None and p.accuracy > max_accuracy_m:
            continue                                  # low-accuracy fix
        if kept:
            prev = kept[-1]
            dist_km = _haversine_km((prev.latitude, prev.longitude), (p.latitude, p.longitude))
            dt = 0.0
            if p.created_at and prev.created_at:
                dt = (_as_utc(p.created_at) - _as_utc(prev.created_at)).total_seconds()
            if dt > 0 and dist_km > 0.15 and (dist_km / (dt / 3600.0)) > max_speed_kmh:
                continue                              # impossible jump → bad fix
        kept.append(p)
    return kept


@router.get("/officer/{officer_id}/history-dates")
def history_dates(officer_id: int, days: int = RETENTION_DAYS,
                  db: Session = Depends(get_db),
                  viewer: models.User = Depends(require_roles(*HISTORY_ROLES))):
    """Days (IST) in the last `days` (default 90 = 3 months) on which this officer has recorded a route."""
    _authorize_officer_view(db, viewer, officer_id)
    prune_old_pings(db)  # keep only the last 90 days (3 months)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    pings = (
        db.query(models.LocationPing)
        .filter(models.LocationPing.officer_id == officer_id,
                models.LocationPing.created_at >= since)
        .order_by(models.LocationPing.created_at.asc())
        .all()
    )
    pings = clean_route(pings)             # de-jitter so per-day distance isn't inflated
    by_day = {}
    for p in pings:
        local = _as_utc(p.created_at).astimezone(IST)
        key = local.strftime("%Y-%m-%d")
        d = by_day.setdefault(key, {"date": key, "points": 0, "first": None, "last": None, "coords": []})
        d["points"] += 1
        d["last"] = local
        if d["first"] is None:
            d["first"] = local
        d["coords"].append((p.latitude, p.longitude))
    out = []
    for key in sorted(by_day, reverse=True):
        d = by_day[key]
        dist = 0.0
        for i in range(1, len(d["coords"])):
            dist += _haversine_km(d["coords"][i - 1], d["coords"][i])
        out.append({
            "date": d["date"],
            "points": d["points"],
            "distance_km": round(dist, 2),
            "first_seen": d["first"].strftime("%H:%M"),
            "last_seen": d["last"].strftime("%H:%M"),
        })
    return out


@router.get("/officer/{officer_id}/route", response_model=list[schemas.PingOut])
def route_for_date(officer_id: int, date: str, db: Session = Depends(get_db),
                   viewer: models.User = Depends(require_roles(*HISTORY_ROLES))):
    """Full ordered route for one IST calendar day (date = 'YYYY-MM-DD')."""
    _authorize_officer_view(db, viewer, officer_id)
    try:
        y, m, d = (int(x) for x in date.split("-"))
        start_ist = datetime(y, m, d, 0, 0, tzinfo=IST)
    except Exception:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    start_utc = start_ist.astimezone(timezone.utc)
    end_utc = start_utc + timedelta(days=1)
    pings = (
        db.query(models.LocationPing)
        .filter(models.LocationPing.officer_id == officer_id,
                models.LocationPing.created_at >= start_utc,
                models.LocationPing.created_at < end_utc)
        .order_by(models.LocationPing.created_at.asc())
        .all()
    )
    return clean_route(pings)             # strip GPS jitter so the drawn route isn't spiky


@router.get("/roster")
def fos_roster(date: str | None = None, db: Session = Depends(get_db),
               user: models.User = Depends(require_roles("admin", "manager", "headoffice", "teamlead"))):
    """All field officers split into ACTIVE (shared location on the day) vs INACTIVE (no
    tracking that day), for today or any past date (date='YYYY-MM-DD'). Powers the live-map popup."""
    if date:
        try:
            y, m, d = (int(x) for x in date.split("-"))
            day = datetime(y, m, d, tzinfo=IST).date()
        except Exception:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    else:
        day = _ist_today()
    start_utc = datetime(day.year, day.month, day.day, tzinfo=IST).astimezone(timezone.utc)
    end_utc = start_utc + timedelta(days=1)

    q = db.query(models.User).filter(models.User.role == "fos", models.User.is_active.isnot(False))
    if user.role == "manager" and user.branch:
        q = q.filter(models.User.branch == user.branch)
    elif user.role == "teamlead":
        q = q.filter(models.User.team_lead_id == user.id)
    foses = q.order_by(models.User.name).all()
    ids = [u.id for u in foses]

    pings = []
    if ids:
        pings = (db.query(models.LocationPing)
                 .filter(models.LocationPing.officer_id.in_(ids),
                         models.LocationPing.created_at >= start_utc,
                         models.LocationPing.created_at < end_utc)
                 .order_by(models.LocationPing.created_at.asc()).all())
    by_officer: dict = {}
    for p in pings:
        by_officer.setdefault(p.officer_id, []).append(p)

    def _info(u):
        base = {"id": u.id, "name": u.name, "emp_code": u.emp_code, "branch": u.branch,
                "location": u.location, "phone": u.phone, "active": u.id in by_officer}
        ps = by_officer.get(u.id)
        if ps:
            cleaned = clean_route(ps) or ps
            dist = 0.0
            for a, b in zip(cleaned, cleaned[1:]):
                dist += _haversine_km((a.latitude, a.longitude), (b.latitude, b.longitude))
            base.update({
                "pings": len(ps),
                "first_seen": _as_utc(ps[0].created_at).isoformat(),
                "last_seen": _as_utc(ps[-1].created_at).isoformat(),
                "distance_km": round(dist, 2),
            })
        return base

    active = [_info(u) for u in foses if u.id in by_officer]
    inactive = [_info(u) for u in foses if u.id not in by_officer]
    return {
        "date": day.isoformat(),
        "is_today": day == _ist_today(),
        "total": len(foses), "active_count": len(active), "inactive_count": len(inactive),
        "active": active, "inactive": inactive,
    }


@router.get("/distance-report")
def distance_report(start: str, end: str, officer_id: int | None = None,
                    db: Session = Depends(get_db),
                    admin: models.User = Depends(require_roles("admin", "manager"))):
    """Excel attendance/distance report: per-officer per-day km travelled and active hours
    across an inclusive IST date range (start & end = 'YYYY-MM-DD')."""
    try:
        sy, sm, sd = (int(x) for x in start.split("-"))
        ey, em, ed = (int(x) for x in end.split("-"))
        start_utc = datetime(sy, sm, sd, 0, 0, tzinfo=IST).astimezone(timezone.utc)
        end_utc = (datetime(ey, em, ed, 0, 0, tzinfo=IST) + timedelta(days=1)).astimezone(timezone.utc)
    except Exception:
        raise HTTPException(status_code=400, detail="start and end must be YYYY-MM-DD")
    if end_utc <= start_utc:
        raise HTTPException(status_code=400, detail="end date must be on or after start date")

    q = db.query(models.LocationPing).filter(
        models.LocationPing.created_at >= start_utc, models.LocationPing.created_at < end_utc)
    if officer_id:
        q = q.filter(models.LocationPing.officer_id == officer_id)
    pings = q.order_by(models.LocationPing.officer_id, models.LocationPing.created_at.asc()).all()

    names = {u.id: u.name for u in db.query(models.User).all()}
    groups = {}
    for p in pings:
        local = _as_utc(p.created_at).astimezone(IST)
        key = (p.officer_id, local.strftime("%Y-%m-%d"))
        g = groups.setdefault(key, {"coords": [], "first": local, "last": local})
        g["coords"].append((p.latitude, p.longitude))
        if local < g["first"]:
            g["first"] = local
        if local > g["last"]:
            g["last"] = local

    daily, per_officer = [], {}
    for (oid, date), g in sorted(groups.items(), key=lambda kv: (names.get(kv[0][0], ""), kv[0][1])):
        dist = sum(_haversine_km(g["coords"][i - 1], g["coords"][i]) for i in range(1, len(g["coords"])))
        active_h = round((g["last"] - g["first"]).total_seconds() / 3600, 2)
        daily.append([names.get(oid, str(oid)), date, len(g["coords"]), round(dist, 2),
                      g["first"].strftime("%H:%M"), g["last"].strftime("%H:%M"), active_h])
        po = per_officer.setdefault(oid, {"days": 0, "dist": 0.0, "active": 0.0})
        po["days"] += 1; po["dist"] += dist; po["active"] += active_h

    wb = Workbook()
    ws = wb.active; ws.title = "Daily"
    ws.append(["Officer", "Date", "GPS Points", "Distance (km)", "First Seen", "Last Seen", "Active Hours"])
    for r in daily:
        ws.append(r)
    ws2 = wb.create_sheet("Summary")
    ws2.append(["Officer", "Active Days", "Total Distance (km)", "Total Active Hours", "Avg km/day"])
    for oid, po in sorted(per_officer.items(), key=lambda kv: names.get(kv[0], "")):
        ws2.append([names.get(oid, str(oid)), po["days"], round(po["dist"], 2), round(po["active"], 2),
                    round(po["dist"] / po["days"], 2) if po["days"] else 0])
    for sheet in (ws, ws2):
        for cell in sheet[1]:
            cell.font = cell.font.copy(bold=True)
        sheet.freeze_panes = "A2"
        for col in sheet.columns:
            width = max((len(str(c.value)) for c in col if c.value is not None), default=10)
            sheet.column_dimensions[col[0].column_letter].width = min(max(width + 2, 12), 40)

    out = io.BytesIO(); wb.save(out)
    fname = f"SSD_Attendance_{start}_to_{end}.xlsx"
    return StreamingResponse(
        io.BytesIO(out.getvalue()),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


@router.get("/officer/{officer_id}/route.csv")
def route_csv(officer_id: int, date: str, db: Session = Depends(get_db),
              viewer: models.User = Depends(require_roles(*HISTORY_ROLES))):
    """Download a field officer's full GPS route for one IST day as CSV
    (sequence, timestamp, latitude, longitude, accuracy, speed)."""
    _authorize_officer_view(db, viewer, officer_id)
    try:
        y, m, d = (int(x) for x in date.split("-"))
        start_utc = datetime(y, m, d, 0, 0, tzinfo=IST).astimezone(timezone.utc)
    except Exception:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    end_utc = start_utc + timedelta(days=1)
    pings = (db.query(models.LocationPing)
             .filter(models.LocationPing.officer_id == officer_id,
                     models.LocationPing.created_at >= start_utc,
                     models.LocationPing.created_at < end_utc)
             .order_by(models.LocationPing.created_at.asc()).all())
    officer = db.query(models.User).filter(models.User.id == officer_id).first()
    name = officer.name if officer else str(officer_id)

    import csv
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["officer", "date", "seq", "timestamp_ist", "latitude", "longitude", "accuracy_m", "speed"])
    for i, p in enumerate(pings, start=1):
        ts = _as_utc(p.created_at).astimezone(IST).strftime("%Y-%m-%d %H:%M:%S")
        w.writerow([name, date, i, ts, p.latitude, p.longitude, p.accuracy or "", p.speed or ""])

    safe = "".join(ch for ch in name if ch.isalnum() or ch in "-_") or str(officer_id)
    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=route_{safe}_{date}.csv"},
    )


@router.get("/me/today")
def my_today(db: Session = Depends(get_db),
             user: models.User = Depends(require_roles("fos", "admin"))):
    """The logged-in field officer's own GPS route for today (IST) — points + distance,
    for the FO's live map."""
    today = _ist_today()
    start_utc = datetime(today.year, today.month, today.day, 0, 0, tzinfo=IST).astimezone(timezone.utc)
    end_utc = start_utc + timedelta(days=1)
    pings = (db.query(models.LocationPing)
             .filter(models.LocationPing.officer_id == user.id,
                     models.LocationPing.created_at >= start_utc,
                     models.LocationPing.created_at < end_utc)
             .order_by(models.LocationPing.created_at.asc()).all())
    pings = clean_route(pings)                         # strip GPS jitter/outliers
    pts = [{"lat": p.latitude, "lng": p.longitude,
            "at": _as_utc(p.created_at).astimezone(IST).strftime("%H:%M")} for p in pings]
    coords = [(p.latitude, p.longitude) for p in pings]
    dist = sum(_haversine_km(coords[i - 1], coords[i]) for i in range(1, len(coords)))
    return {"count": len(pts), "distance_km": round(dist, 2), "points": pts}
