"""Visit trust score — was this field visit really made at the customer's address?

Every visit gets a level:  ok (✅ Verified) · check (⚠️ Check) · suspicious (🚩 Suspicious)
plus human-readable reasons. Checks:

  1. Fake-GPS app (Android mock-location flag)                             → suspicious
  2. No GPS at all                                                          → suspicious
  3. Weak (> ±100 m) or stale (> 2 min old) fix                             → check
  4. Distance to the CHOSEN address's map pin, with a radius that depends on how precisely that
     address could be placed on the map (doorstep-confirmed 150 m … city-level 8 km)
        beyond radius → check · beyond 2× radius → suspicious
     If another of the customer's addresses IS near, it says so ("near Address 2, not Address 1").
  5. Pincode where the photo was taken vs the address's pincode (catches wrong area even when the
     address couldn't be pinned on the map)                                → check
  6. Live-tracking route: was the FOS's tracked route near this spot ±20 min?  > 2 km away → suspicious
  7. Batch-faking: visits to OTHER customers logged within 50 m in the last 30 min → check / suspicious
  8. Impossible travel from his previous visit (> 80 km/h over > 2 km)     → suspicious
"""
import json
import math
import re
from datetime import datetime, timedelta, timezone

from . import models

# How far a genuine doorstep photo can be from the address pin, by how the pin was obtained.
RADIUS_M = {"field": 150, "rooftop": 250, "street": 400, "locality": 1000, "pincode": 3000, "city": 8000}
LEVELS = {"ok": 0, "check": 1, "suspicious": 2}
LABEL = {"ok": "✅ Verified", "check": "⚠️ Check", "suspicious": "🚩 Suspicious"}
_PIN_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")


def haversine_m(a_lat, a_lng, b_lat, b_lng):
    r = 6371000.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dphi = math.radians(b_lat - a_lat)
    dl = math.radians(b_lng - a_lng)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _pin6(*texts):
    for t in texts:
        m = _PIN_RE.search(str(t or ""))
        if m:
            return m.group(1)
    return None


def address_slots(case):
    """The customer's addresses as slots: {'1': {...}, '2': {...}, '3': {...}, 'new': {...}}.
    Each: text, pincode, and the map pins we know (field-confirmed and/or geocoded) with precision."""
    out = {}
    s1_pins = []
    if case.latitude is not None and case.longitude is not None:
        prec = "field" if (case.location_source or "") == "field" else (case.geo_precision or "locality")
        s1_pins.append((case.latitude, case.longitude, prec))
    if case.geo_lat is not None and case.geo_lng is not None and (case.location_source or "") == "field":
        s1_pins.append((case.geo_lat, case.geo_lng, case.geo_precision or "locality"))
    if case.address or case.pincode:
        out["1"] = {"label": "Address 1", "text": case.address, "pincode": case.pincode or _pin6(case.address),
                    "pins": s1_pins}
    for n in ("2", "3"):
        txt, pin = getattr(case, f"address{n}", None), getattr(case, f"pincode{n}", None)
        lat, lng = getattr(case, f"latitude{n}", None), getattr(case, f"longitude{n}", None)
        if txt or pin:
            pins = [(lat, lng, getattr(case, f"geo_precision{n}", None) or "locality")] if lat is not None and lng is not None else []
            out[n] = {"label": f"Address {n}", "text": txt, "pincode": pin or _pin6(txt), "pins": pins}
    if case.new_address:
        out["new"] = {"label": "New address", "text": case.new_address, "pincode": _pin6(case.new_address), "pins": []}
    return out


def _dist_to_slot(slot, lat, lng):
    """(distance_m, allowed_radius_m, precision) to the slot's closest pin, or None when unpinned."""
    best = None
    for plat, plng, prec in slot.get("pins") or []:
        d = haversine_m(lat, lng, plat, plng)
        rad = RADIUS_M.get(prec, 1000)
        if best is None or d - rad < best[0] - best[1]:
            best = (d, rad, prec)
    return best


# ---------------------------------------------------------------- street / area name matching
# Words that say nothing about WHERE (house numbers, road types, filler, country/state names).
_GENERIC = {
    "road", "rd", "street", "st", "main", "cross", "lane", "ln", "marg", "path", "nagar", "colony",
    "near", "nr", "opp", "opposite", "beside", "behind", "back", "side", "front", "next", "to", "the",
    "and", "of", "at", "in", "on", "post", "po", "dist", "district", "mandal", "taluk", "tq", "village",
    "vill", "town", "city", "house", "flat", "plot", "door", "no", "dno", "hno", "floor", "block",
    "sector", "phase", "stage", "ward", "area", "layout", "extension", "extn", "apartment", "apartments",
    "apts", "residency", "building", "complex", "society", "india", "pin", "pincode", "west", "east",
    "north", "south", "new", "old", "upper", "lower", "first", "second", "third", "1st", "2nd", "3rd",
    "andhra", "pradesh", "telangana", "tamil", "nadu", "karnataka", "kerala", "maharashtra", "odisha",
    "state", "unnamed", "gate", "circle", "junction", "jn", "center", "centre", "bazar", "bazaar",
}


def _squash(t: str) -> str:
    """Spelling-tolerant form: Gunadhala / Gunadala / GUNNADALA → 'gunadala'."""
    t = re.sub(r"[^a-z]", "", (t or "").lower())
    t = t.replace("ee", "i").replace("oo", "u").replace("w", "v").replace("z", "j")
    t = re.sub(r"(?<=[bcdgjkpstr])h", "", t)        # aspirated consonants: dh→d, th→t, bh→b, sh→s …
    return re.sub(r"(.)\1+", r"\1", t)             # collapse double letters


def place_words(detected_address: str | None, city: str | None = None) -> list[str]:
    """Distinctive street/area/landmark words from the phone's detected address. Leaves out the
    state/pincode/country, the CITY (it would 'match' every customer in town) and generic words."""
    if not detected_address:
        return []
    parts = [p.strip() for p in re.sub(r"\d{6}", " ", detected_address).split(",") if p.strip()]
    if parts and parts[-1].lower() == "india":
        parts = parts[:-1]
    if parts:
        parts = parts[:-1]                          # "State PIN"
    city_sq = {_squash(w) for w in re.findall(r"[A-Za-z]{3,}", city or "")}
    if not city_sq and len(parts) >= 2:
        parts = parts[:-1]                          # no city given → assume the last part is the city
    out = []
    for p in parts:
        for w in re.findall(r"[A-Za-z]{4,}", p):
            lw = w.lower()
            if lw in _GENERIC:
                continue
            sq = _squash(lw)
            if len(sq) >= 4 and sq not in out and sq not in city_sq:
                out.append(sq)
    return out


def street_match(detected_address: str | None, customer_text: str | None, city: str | None = None) -> list[str]:
    """Which distinctive words of the detected address also appear in a customer address.
    Works on run-on upload text too ('VIZAGVISALAKSHINAGAR') because it matches inside the
    squashed address, not word-by-word."""
    if not detected_address or not customer_text:
        return []
    hay = _squash(customer_text)
    return [w for w in place_words(detected_address, city) if w in hay]


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def evaluate(db, case, officer_id, lat, lng, accuracy=None, slot_key="1", mock=False,
             fix_age_s=None, gps_pincode=None, at=None, exclude_visit_id=None, gps_address=None, gps_city=None):
    """Score one visit. Returns {level, reasons:[{sev,text}], distance_m, slot}."""
    at = _aware(at) or datetime.now(timezone.utc)
    reasons = []

    def add(sev, text, kind=None):
        reasons.append({"sev": sev, "text": text, **({"kind": kind} if kind else {})})

    slots = address_slots(case)
    slot_key = str(slot_key or "1")
    if slot_key not in slots:
        slot_key = "1" if "1" in slots else (next(iter(slots), "1"))
    slot = slots.get(slot_key) or {"label": "Address", "pins": [], "pincode": None}
    distance_m = None

    if mock:
        add("suspicious", "Fake-GPS app detected on the phone")
    if lat is None or lng is None:
        add("suspicious", "No GPS location on the visit")
        return _finish(reasons, None, slot_key)

    acc = float(accuracy) if accuracy is not None else None
    if acc is not None and acc > 100:
        add("check", f"Weak GPS (±{int(acc)} m)")
    if fix_age_s is not None and fix_age_s > 120:
        add("check", f"Old GPS fix ({int(fix_age_s // 60)} min old)")
    slack = min(acc or 0, 200)

    # 4. distance to the chosen address (+ hint if another address is the near one)
    near = _dist_to_slot(slot, lat, lng)
    if near:
        d, rad, prec = near
        distance_m = round(d, 1)
        alt = None
        if d > rad + slack:            # far from the chosen address — is he at one of the OTHER addresses?
            for k, s2 in slots.items():
                if k == slot_key:
                    continue
                o = _dist_to_slot(s2, lat, lng)
                if o and o[0] <= o[1] + slack:
                    alt = s2
                    break
        if alt is not None:            # genuine customer address, just the wrong one picked
            add("check", f"Photo is at {alt['label']}, but {slot['label']} was selected", "wrong_slot")
        elif d > 2 * rad + slack:
            add("suspicious", f"{_km(d)} from {slot['label']} (allowed ~{_km(rad)}, map pin: {prec})", "distance")
        elif d > rad + slack:
            add("check", f"{_km(d)} from {slot['label']} (allowed ~{_km(rad)}, map pin: {prec})", "distance")
        if prec in ("pincode", "city"):
            add("info", f"{slot['label']} is only mapped to {prec} level — distance check is rough")
    else:
        add("info", f"{slot['label']} isn't on the map yet — distance not checked")

    # 5. pincode
    want_pin = slot.get("pincode")
    if gps_pincode and want_pin and str(gps_pincode).strip() != str(want_pin).strip():
        sev = "check"
        if near is None:   # no map pin → pincode is our only area check
            sev = "check"
        add(sev, f"Photo taken in pincode {gps_pincode}, {slot['label']} is {want_pin}", "pincode")

    # 5b. street / area name: does the detected address's street or area appear in the customer's address?
    words = place_words(gps_address, gps_city)
    if words:
        hit = street_match(gps_address, slot.get("text"), gps_city)
        if hit:
            shown = []
            for w in re.findall(r"[A-Za-z]{4,}", gps_address or ""):   # show the phone's own spelling
                if _squash(w) in hit and w.title() not in shown:
                    shown.append(w.title())
            add("info", f"✓ Street/area matches {slot['label']}: {', '.join(shown[:3]) or ', '.join(hit[:3])}", "street_ok")
            # The map pin of an approximate (area / pincode / city-level) address can be far off;
            # a matching street name is stronger proof, so those distance/pincode doubts are cleared.
            approx = (near is None) or (near[2] in ("locality", "pincode", "city"))
            for r in reasons:
                if r.get("kind") in ("distance", "pincode") and (approx or r["sev"] == "check"):
                    r["sev"] = "info"
                    r["text"] += " — cleared: street matches"
        else:
            other = next(((k, s2) for k, s2 in slots.items() if k != slot_key and street_match(gps_address, s2.get("text"), gps_city)), None)
            if other:
                add("check", f"Street at photo matches {other[1]['label']}, but {slot['label']} was selected", "wrong_slot")
            else:
                pin_bad = any(r.get("kind") == "pincode" for r in reasons)
                add("suspicious" if pin_bad else "check",
                    f"Street/area at photo ({gps_address[:60]}) doesn't match any customer address"
                    + (" and pincode differs" if pin_bad else ""), "street_bad")

    # 6. live-tracking route near this spot?
    win = timedelta(minutes=20)
    pings = (db.query(models.LocationPing.latitude, models.LocationPing.longitude)
             .filter(models.LocationPing.officer_id == officer_id,
                     models.LocationPing.created_at >= at - win,
                     models.LocationPing.created_at <= at + win).all())
    if pings:
        closest = min(haversine_m(lat, lng, p[0], p[1]) for p in pings)
        if closest > 2000:
            add("suspicious", f"Live tracking shows him {_km(closest)} away at that time")
        elif closest > max(400, 2 * slack):
            add("check", f"Live tracking was {_km(closest)} from the photo spot")
    else:
        add("info", "No live-tracking points around the visit time")

    # 7 + 8. other visits by the same FOS
    q = (db.query(models.Visit).filter(models.Visit.officer_id == officer_id,
                                       models.Visit.created_at >= at - timedelta(hours=12),
                                       models.Visit.created_at <= at,
                                       models.Visit.latitude.isnot(None)))
    if exclude_visit_id:
        q = q.filter(models.Visit.id != exclude_visit_id)
    recent = q.order_by(models.Visit.created_at.desc()).all()
    same_spot = {v.case_id for v in recent
                 if v.case_id != case.id and _aware(v.created_at) >= at - timedelta(minutes=30)
                 and haversine_m(lat, lng, v.latitude, v.longitude) <= 50}
    if len(same_spot) >= 2:
        add("suspicious", f"{len(same_spot)} other customers' visits logged at this same spot in 30 min")
    elif same_spot:
        add("check", "Another customer's visit was logged at this same spot in the last 30 min")
    prev = recent[0] if recent else None
    if prev is not None:
        dist = haversine_m(lat, lng, prev.latitude, prev.longitude)
        mins = max((at - _aware(prev.created_at)).total_seconds() / 60.0, 0.5)
        kmh = dist / 1000.0 / (mins / 60.0)
        if dist > 2000 and kmh > 80:
            add("suspicious", f"Impossible travel: {_km(dist)} from previous visit in {int(mins)} min")

    return _finish(reasons, distance_m, slot_key)


def _finish(reasons, distance_m, slot_key):
    level = "ok"
    for r in reasons:
        if r["sev"] in LEVELS and LEVELS[r["sev"]] > LEVELS[level]:
            level = r["sev"]
    return {"level": level, "reasons": reasons, "distance_m": distance_m, "slot": slot_key}


def _km(m):
    return f"{m / 1000:.1f} km" if m >= 1000 else f"{int(m)} m"


def reasons_text(reasons, include_info=False):
    return " · ".join(r["text"] for r in (reasons or []) if include_info or r["sev"] != "info")


def dumps(reasons):
    return json.dumps(reasons, ensure_ascii=False)


def loads(s):
    try:
        return json.loads(s) if s else []
    except Exception:
        return []


def set_slot_pin(case, slot_key, lat, lng):
    """Make (lat,lng) the doorstep-confirmed pin of that address slot."""
    from . import digipin as _dp
    now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    if slot_key == "1":
        case.latitude, case.longitude = lat, lng
        case.location_source = "field"
        case.location_updated_at = now
        case.digipin = _dp.encode(lat, lng)
        return True
    if slot_key in ("2", "3"):
        setattr(case, f"latitude{slot_key}", lat)
        setattr(case, f"longitude{slot_key}", lng)
        setattr(case, f"geo_precision{slot_key}", "field")
        return True
    return False


def is_flagged(v, fallback_m=300):
    """A visit counts as 'off-location / flagged' when its trust score says Check or Suspicious;
    older visits without a score fall back to the plain distance geofence."""
    lv = getattr(v, "trust_level", None)
    if lv:
        return lv in ("check", "suspicious")
    d = getattr(v, "distance_from_case_m", None)
    return d is not None and float(d) > fallback_m
