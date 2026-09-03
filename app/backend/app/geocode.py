"""Turn a messy case address into lat/long via LocationIQ, with an offline-friendly cleaner
and a tiered fallback so we always get *something* mappable.

Upload addresses are unpunctuated and run-on with an embedded pincode, e.g.
  "AR HQ, VISALAKSHINAGAR, NEAR PETROL PUMP, VIZAGVISALAKSHINAGAR, VIZAGVISAKHAPATNAMVISAKHAPATNAM530043"
We (1) pull the 6-digit pincode out, (2) split on separators, (3) drop duplicate segments, then
geocode in tiers: full cleaned address -> pincode-only centroid. Precision is recorded so the map
can show exact vs approximate pins.

Geocoder is intentionally isolated here so it can be swapped to Google later (memory note) by
changing only this file. Reads LOCATIONIQ_KEY from settings.
"""
import json
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
    return bool(settings.locationiq_key)


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
                timeout=45)
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
                           timeout=45)
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
                out[int(rid)] = clean
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
