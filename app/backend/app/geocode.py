"""Turn a messy case address into lat/long via LocationIQ, with an offline-friendly cleaner
and a tiered fallback so we always get *something* mappable.

Upload addresses are unpunctuated and run-on with an embedded pincode, e.g.
  "AR HQ, VISALAKSHINAGAR, NEAR PETROL PUMP, VIZAGVISALAKSHINAGAR, VIZAGVISAKHAPATNAMVISAKHAPATNAM530043"
We (1) pull the 6-digit pincode out, (2) split on separators, (3) drop duplicate segments, then
geocode in tiers: full cleaned address -> pincode-only centroid. Precision is recorded so the map
can show exact vs approximate pins.

Provider: Google Geocoding when GOOGLE_GEOCODING_KEY is set (best for Indian addresses), else
LocationIQ (LOCATIONIQ_KEY). Precision scale: rooftop (building) · street · locality (area) ·
pincode (pincode centre) · city.
"""
import json
import os
import re
import time

import httpx

from .config import get_settings

settings = get_settings()

_ENDPOINT = "https://us1.locationiq.com/v1/search"
_PIN_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")

# Map LocationIQ result "type" to how precise the pin is.
_PRECISION = {
    "house": "rooftop", "building": "rooftop", "residential": "rooftop",
    "road": "locality", "neighbourhood": "locality", "suburb": "locality",
    "hamlet": "locality", "quarter": "locality",
    "postcode": "pincode",
    "city": "city", "town": "city", "village": "city", "state": "city",
}


def has_key() -> bool:
    return bool(settings.google_geocoding_key or settings.locationiq_key)


def provider() -> str:
    """'google' when GOOGLE_GEOCODING_KEY is set, else 'locationiq'."""
    return "google" if settings.google_geocoding_key else "locationiq"


def pace_seconds() -> float:
    """Gap between lookups: Google allows ~50/s, LocationIQ free tier ~2/s."""
    return 0.05 if provider() == "google" else 0.5


# ---------------------------------------------------------------- Google Geocoding
_G_ENDPOINT = "https://maps.googleapis.com/maps/api/geocode/json"
_G_BUILDING = {"premise", "subpremise", "establishment", "point_of_interest"}
_G_STREET = {"street_address", "route", "intersection", "plus_code"}
_G_AREA = {"sublocality", "sublocality_level_1", "sublocality_level_2", "sublocality_level_3",
           "neighborhood", "colloquial_area"}
_G_PIN = {"postal_code"}


def _google_precision(r) -> str:
    """Map Google's location_type + result types to our precision scale."""
    lt = (r.get("geometry") or {}).get("location_type", "")
    types = set(r.get("types") or [])
    if lt == "ROOFTOP":
        prec = "rooftop"
    elif lt == "RANGE_INTERPOLATED":
        prec = "street"
    elif types & _G_BUILDING:
        prec = "rooftop"
    elif types & _G_STREET:
        prec = "street"
    elif types & _G_AREA:
        prec = "locality"
    elif types & _G_PIN:
        prec = "pincode"
    else:
        prec = "city"
    if r.get("partial_match") and prec == "rooftop":
        prec = "street"                       # Google only partly matched the text — don't over-trust
    return prec


def _google_query(client: httpx.Client, address: str | None, pin: str | None):
    params = {"key": settings.google_geocoding_key, "region": "in", "language": "en"}
    comps = ["country:IN"] + ([f"postal_code:{pin}"] if pin else [])
    params["components"] = "|".join(comps)
    if address:
        params["address"] = address
    try:
        r = client.get(_G_ENDPOINT, params=params)
        if r.status_code == 200:
            data = r.json()
            if data.get("status") == "OK" and data.get("results"):
                top = data["results"][0]
                loc = top["geometry"]["location"]
                return float(loc["lat"]), float(loc["lng"]), _google_precision(top), top.get("formatted_address", "")
    except Exception:
        pass
    return None


def extract_pincode(text, existing=None):
    """Prefer an explicit pincode column; else pull the last 6-digit run out of the text."""
    if existing and re.fullmatch(r"\d{6}", str(existing).strip() or ""):
        return str(existing).strip()
    if not text:
        return None
    found = _PIN_RE.findall(str(text))
    return found[-1] if found else None


def clean_address(address, address2=None, pincode=None) -> dict:
    """Best-effort cleanup → {'clean': readable string, 'pincode': '530043'|None}.
    Deterministic and offline (no dictionary needed): strips the pincode, splits on
    separators, collapses whitespace, and drops duplicate segments."""
    parts = [str(p).strip() for p in (address, address2) if p and str(p).strip()]
    raw = ", ".join(parts)
    pin = extract_pincode(raw, pincode)
    text = _PIN_RE.sub(" ", raw)                       # remove pincode digits from the text
    segs = re.split(r"[,/\\|;]+", text)                # split on common separators
    out, seen = [], set()
    for s in segs:
        t = re.sub(r"\s+", " ", s).strip(" .-")
        if not t:
            continue
        key = t.upper()
        if key in seen:                                # drop repeated segments (VIZAG, VIZAG)
            continue
        seen.add(key)
        out.append(t)
    cleaned = ", ".join(out)
    display = cleaned.title() if cleaned else ""
    return {"clean": display, "pincode": pin}


def llm_available() -> bool:
    return bool(settings.openrouter_api_key or settings.gemini_api_key)


def _llm_call(prompt: str) -> str | None:
    """Send one prompt to whichever LLM is configured (OpenRouter preferred, else Gemini).
    Returns the raw text reply, or None on any error."""
    # OpenRouter — OpenAI-compatible chat completions.
    if settings.openrouter_api_key:
        try:
            r = httpx.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.openrouter_api_key}",
                         "Content-Type": "application/json",
                         "X-Title": "RecoverIQ Geocoder"},
                json={"model": settings.openrouter_model,
                      "messages": [{"role": "user", "content": prompt}],
                      "temperature": 0.1},
                timeout=15)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception:
            return None
    # Gemini fallback.
    if settings.gemini_api_key:
        try:
            url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{settings.gemini_model}:generateContent?key={settings.gemini_api_key}")
            r = httpx.post(url, json={"contents": [{"parts": [{"text": prompt}]}],
                                      "generationConfig": {"temperature": 0.1, "maxOutputTokens": 4096}},
                           timeout=15)
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            return None
    return None


_LLM_PROMPT = (
    "You normalize messy Indian postal addresses so a map geocoder can find them. For EACH item, "
    "rewrite the address into a clean, standard, geocodable form:\n"
    "- Split run-together words (e.g. 'VIZAGVISAKHAPATNAM' -> 'Vizag Visakhapatnam').\n"
    "- Expand/standardize well-known short forms to the OFFICIAL name (e.g. 'Vizag' -> "
    "'Visakhapatnam', 'Hyd' -> 'Hyderabad', 'Bangalore' -> 'Bengaluru').\n"
    "- Remove duplicated tokens and vague landmarks that don't help geocoding (e.g. 'near petrol "
    "pump', repeated area names, house/door numbers).\n"
    "- Keep the real locality/area, city, state and the 6-digit PIN code.\n"
    "- Do NOT invent any location detail that isn't present or clearly implied.\n"
    "Return ONLY a JSON array of objects {\"id\": <id>, \"clean\": \"<address>\"} and nothing else.\n"
    "Items:\n"
)


def llm_clean_batch(items: list[dict]) -> dict:
    """Clean many raw addresses in one Gemini call. `items` = [{'id', 'raw'}]. Returns {id: clean}.
    Best-effort: on any error returns {} so the caller falls back to the deterministic cleaner."""
    if not items or not llm_available():
        return {}
    payload_items = [{"id": it["id"], "raw": (it.get("raw") or "")[:500]} for it in items]
    prompt = _LLM_PROMPT + json.dumps(payload_items, ensure_ascii=False)
    text = _llm_call(prompt)
    if not text:
        return {}
    try:
        text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
        arr = json.loads(text)
        out = {}
        for row in arr:
            rid, clean = row.get("id"), (row.get("clean") or "").strip()
            if rid is not None and clean:
                # Keep ids as STRINGS — they can be composite (e.g. "123-1" = case 123, address slot 1),
                # so int() would throw and drop the whole batch, silently forcing local-only cleaning.
                out[str(rid)] = clean
        return out
    except Exception:
        return {}


def _precision_from(typ, cls):
    return _PRECISION.get((typ or "").lower()) or _PRECISION.get((cls or "").lower()) or "locality"


def _query(client: httpx.Client, q: str):
    try:
        r = client.get(_ENDPOINT, params={
            "key": settings.locationiq_key, "q": q, "format": "json",
            "limit": 1, "countrycodes": "in", "normalizeaddress": 1,
        })
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data:
                d0 = data[0]
                return float(d0["lat"]), float(d0["lon"]), d0.get("type"), d0.get("class")
    except Exception:
        pass
    return None


# ---------------------------------------------------------------- Google: geocode + Places backup
_RANK = {"none": 0, "city": 1, "pincode": 2, "locality": 3, "street": 4, "rooftop": 5}
_WEAK = {"none", "city", "pincode", "locality"}           # not good enough to find the door
_PLACES_ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
_PLACES_COUNT_FILE = os.path.join(os.path.dirname(__file__), "..", ".places_daily_count.json")


def _places_budget_ok() -> bool:
    """Daily cap on Places lookups (persists across restarts in a tiny JSON file)."""
    cap = int(getattr(settings, "google_places_daily_cap", 0) or 0)
    if cap <= 0:
        return False
    today = time.strftime("%Y-%m-%d")
    try:
        with open(_PLACES_COUNT_FILE) as f:
            d = json.load(f)
    except Exception:
        d = {}
    if d.get("date") != today:
        d = {"date": today, "count": 0}
    if d["count"] >= cap:
        return False
    d["count"] += 1
    try:
        with open(_PLACES_COUNT_FILE, "w") as f:
            json.dump(d, f)
    except Exception:
        pass
    return True


def places_used_today() -> dict:
    try:
        with open(_PLACES_COUNT_FILE) as f:
            d = json.load(f)
        if d.get("date") == time.strftime("%Y-%m-%d"):
            return {"used": d.get("count", 0), "cap": settings.google_places_daily_cap}
    except Exception:
        pass
    return {"used": 0, "cap": settings.google_places_daily_cap}


def _places_query(client: httpx.Client, text: str, pin: str | None):
    """Google Places text search (like typing into Google Maps). Accepted only when the result is
    in the same pincode as the case (so 'Durga temple' can't jump to another town)."""
    if not text or not _places_budget_ok():
        return None
    try:
        r = client.post(_PLACES_ENDPOINT, json={
            "textQuery": f"{text}{', ' + pin if pin else ''}, India",
            "regionCode": "IN", "languageCode": "en", "pageSize": 1,
        }, headers={"X-Goog-Api-Key": settings.google_geocoding_key,
                    "X-Goog-FieldMask": "places.location,places.formattedAddress,places.types"})
        if r.status_code != 200:
            return None
        places = (r.json() or {}).get("places") or []
        if not places:
            return None
        top = places[0]
        addr = top.get("formattedAddress") or ""
        if pin and pin not in addr:
            return None                                  # different area — don't trust it
        loc = top.get("location") or {}
        types = set(top.get("types") or [])
        prec = "rooftop" if types & {"premise", "subpremise", "street_address"} else "street"
        return float(loc["latitude"]), float(loc["longitude"]), prec
    except Exception:
        return None


def _google_geocode(client, address, address2, pincode, pre_clean, result):
    """1) lightly-tidied ORIGINAL address (landmarks kept) within its pincode → 2) if that only finds
    the area/pincode: Places text search (capped/day) → 3) the AI-cleaned text (with, then without,
    the pincode) → 4) pincode centre. Keeps the most precise hit."""
    tidy = clean_address(address, address2, pincode)
    light, pin = tidy["clean"], tidy["pincode"] or result.get("pincode")
    best = None                                          # (lat, lng, precision, source)

    def consider(res, source):
        nonlocal best
        if res and (best is None or _RANK.get(res[2], 0) > _RANK.get(best[2], 0)):
            best = (res[0], res[1], res[2], source)

    if light:
        consider(_google_query(client, light, pin), "geocode")
    if (best is None or best[2] in _WEAK) and light:
        consider(_places_query(client, light, pin), "places")
    if best is None or best[2] in _WEAK:
        alt = result.get("clean")
        if alt and alt != light:
            consider(_google_query(client, alt, pin), "geocode-clean")
        if (best is None or best[2] in _WEAK) and (alt or light) and pin:
            res = _google_query(client, alt or light, None)
            if res and pin in (res[3] or ""):              # searched India-wide: must still be the same pincode
                consider(res, "geocode-nopin")
    if best is None and pin:
        res = _google_query(client, None, pin)
        if res:
            best = (res[0], res[1], "pincode", "pincode")
    if best:
        result.update({"lat": best[0], "lng": best[1], "precision": best[2], "source": best[3]})
    return result


def geocode_one(client: httpx.Client, address, address2=None, pincode=None,
                pace_seconds: float = 1.0, pre_clean: str | None = None) -> dict:
    """Geocode a single case. Returns dict with lat/lng/precision + the cleaned address & pincode.
    Tiers: full cleaned address (+pincode) → pincode-only centroid. `precision='none'` on total miss.
    `pre_clean` (an LLM-cleaned address) is used as the query base when provided; the pincode is
    still taken from the case/text so the fallback centroid always works."""
    if pre_clean:
        pin = extract_pincode(pre_clean, pincode) or extract_pincode(
            ", ".join(str(p) for p in (address, address2) if p), pincode)
        clean = _PIN_RE.sub(" ", pre_clean).strip(" ,.-") or pre_clean
    else:
        info = clean_address(address, address2, pincode)
        clean, pin = info["clean"], info["pincode"]
    result = {"lat": None, "lng": None, "precision": "none", "clean": clean, "pincode": pin}

    if provider() == "google":
        return _google_geocode(client, address, address2, pincode, pre_clean, result)

    tiers = []
    if clean and pin:
        tiers.append((f"{clean}, {pin}, India", None))
    elif clean:
        tiers.append((f"{clean}, India", None))
    if pin:
        tiers.append((f"{pin}, India", "pincode"))     # last-resort area centroid

    for i, (q, forced) in enumerate(tiers):
        if i:
            time.sleep(pace_seconds)                   # respect rate limits between retries
        res = _query(client, q)
        if res:
            lat, lon, typ, cls = res
            result.update({"lat": lat, "lng": lon,
                           "precision": forced or _precision_from(typ, cls)})
            break
    return result
