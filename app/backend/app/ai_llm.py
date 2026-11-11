"""LLM providers for AI Assist — one internal format, three back-ends:
  • local      — any OpenAI-compatible server on your machine (Ollama, vLLM, LM Studio): no data leaves the server
  • openrouter — OpenAI-compatible cloud router
  • gemini     — Google Gemini (key sent in a header, never in the URL)

Internal messages: {"role": "user"|"assistant"|"tool", "content": str,
                    "tool_calls": [{"id","name","args"}], "tool_call_id": str, "name": str}
call_llm(...) → {"content": str, "tool_calls": [{"id","name","args"}]}
"""
from __future__ import annotations

import json
import time
import uuid

import httpx

from .config import get_settings


class LLMError(Exception):
    pass


# Provider registry (opencode-style). Almost every provider speaks the OpenAI chat-completions format, so one
# connector + a base URL covers them; Gemini keeps its native adapter. `local` = data never leaves your server.
PROVIDERS = {
    "ollama":     {"label": "Ollama on your server", "base": "http://127.0.0.1:11434/v1", "local": True,
                   "default": "qwen3:4b", "key": None, "url_setting": True},
    "lmstudio":   {"label": "LM Studio on your server", "base": "http://127.0.0.1:1234/v1", "local": True,
                   "default": "", "key": None, "url_setting": True},
    "custom":     {"label": "Custom OpenAI-compatible server (vLLM, LocalAI, …)", "base": "", "local": None,
                   "default": "", "key": "custom_api_key", "url_setting": True},
    "gemini":     {"label": "Google Gemini", "base": "https://generativelanguage.googleapis.com/v1beta", "local": False,
                   "default": "gemini-3.8-flash", "key": "gemini_api_key", "native": "gemini"},
    "openai":     {"label": "OpenAI", "base": "https://api.openai.com/v1", "local": False, "default": "gpt-4o-mini", "key": "openai_api_key"},
    "anthropic":  {"label": "Anthropic (Claude)", "base": "https://api.anthropic.com/v1", "local": False, "default": "", "key": "anthropic_api_key"},
    "openrouter": {"label": "OpenRouter (hundreds of models, one key)", "base": "https://openrouter.ai/api/v1", "local": False,
                   "default": "openai/gpt-4o-mini", "key": "openrouter_api_key"},
    "groq":       {"label": "Groq (very fast)", "base": "https://api.groq.com/openai/v1", "local": False,
                   "default": "openai/gpt-oss-120b", "key": "groq_api_key"},
    "ovh":        {"label": "OVHcloud AI Endpoints (free, no key needed)", "base": "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1",
                   "local": False, "default": "gpt-oss-120b", "key": "ovh_api_key", "key_optional": True},
    "deepseek":   {"label": "DeepSeek", "base": "https://api.deepseek.com/v1", "local": False, "default": "deepseek-chat", "key": "deepseek_api_key"},
    "mistral":    {"label": "Mistral", "base": "https://api.mistral.ai/v1", "local": False, "default": "mistral-small-latest", "key": "mistral_api_key"},
}
ALIASES = {"local": "ollama"}           # settings saved before the registry existed
DEFAULT_MODELS = {k: v["default"] for k, v in PROVIDERS.items()}


def _prov(name):
    name = ALIASES.get(name or "", name or "ollama")
    return name if name in PROVIDERS else "ollama"


def _key(conf, prov):
    k = PROVIDERS[prov].get("key")
    if not k:
        return ""
    s = get_settings()
    return conf.get(k) or str(getattr(s, k, "") or "")


def _base(conf, prov):
    p = PROVIDERS[prov]
    if p.get("url_setting"):
        return (conf.get("local_url") if prov != "custom" else conf.get("custom_url")) or p["base"]
    return p["base"]


_GEMINI_RETIRED = ("gemini-1.0", "gemini-1.5", "gemini-2.0", "gemini-2.5-flash", "gemini-pro")
# Model ids the provider has shut down → use the provider's current default instead of failing.
_RETIRED = {"groq": ("llama-3.3-70b-versatile", "llama-3.1-8b-instant", "llama3-", "mixtral-8x7b", "gemma2-9b", "gemma-7b")}


def gemini_model_ok(m):
    """Google shut down the 1.x / 2.0 models — swap any saved old id for the current Flash."""
    m = (m or "").strip()
    if not m or m.lower().startswith(_GEMINI_RETIRED):
        return PROVIDERS["gemini"]["default"]
    return m


def _model(conf, prov, fallback=False):
    m = conf.get("fallback_model" if fallback else "model") or ""
    if prov == "gemini":
        return gemini_model_ok(m or get_settings().gemini_model)
    if m and m.lower().startswith(_RETIRED.get(prov, ())):
        m = ""
    if m:
        return m
    s = get_settings()
    if prov == "gemini":
        return s.gemini_model or PROVIDERS["gemini"]["default"]
    if prov == "openrouter":
        return s.openrouter_model or PROVIDERS["openrouter"]["default"]
    return PROVIDERS[prov]["default"]


def _is_qwen3(model):
    return "qwen3" in (model or "").lower()


def _schema(params: dict) -> dict:
    props = {}
    for k, t in params.items():
        typ = "number" if t == "number" else "integer" if t == "integer" else "string"
        props[k] = {"type": typ, "description": t if "|" in t else k.replace("_", " ")}
    return {"type": "object", "properties": props}


def tool_specs(tools: dict) -> list[dict]:
    return [{"name": n, "description": d, "parameters": _schema(p)} for n, (_, d, p) in tools.items()]


def _friendly_error(base: str, model: str, code: int, body: str) -> str:
    """Plain-language provider errors (free-tier limits, empty credits) instead of raw JSON."""
    who = "OpenRouter" if "openrouter" in (base or "") else "The AI provider"
    low = (body or "").lower()
    if code == 429 and "openrouter" in (base or ""):
        return ("OpenRouter's free-model limit was reached (free ':free' models allow 20 requests/minute and 50/day; "
                "1000/day once $10 of credits has ever been bought). Wait and retry, add credits, set a backup provider, "
                "or switch to your local model in ⚙️ Services → AI Assist.")
    if code == 429:
        return f"{who} is busy or rate-limiting ({model}). Please retry in a minute, or set a backup provider in ⚙️ Services."
    if code == 402 or "credit" in low or "insufficient" in low:
        return (f"{who} has no credits left for {model}. Add credits on the provider's website, pick a free model, "
                "or switch to the local model / backup provider in ⚙️ Services → AI Assist.")
    if code in (401, 403):
        return f"{who} rejected the API key ({code}). Re-enter the key in ⚙️ Services → AI Assist."
    if code == 404:
        return f"{who} doesn't know the model '{model}'. Pick another with ⟳ Load models in ⚙️ Services."
    return f"AI provider error {code}: {body[:200]}"


def _openai(base, key, model, system, messages, tools, timeout, think=None, max_tokens=None, local=False):
    if think is False and _is_qwen3(model):
        system = system + "\n/no_think"          # Qwen3 soft switch: answer directly, no long reasoning
    msgs = [{"role": "system", "content": system}]
    for m in messages:
        if m["role"] == "tool":
            msgs.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": m["content"]})
        elif m.get("tool_calls"):
            msgs.append({"role": "assistant", "content": m.get("content") or "",
                         "tool_calls": [{"id": c["id"], "type": "function",
                                         "function": {"name": c["name"], "arguments": json.dumps(c["args"])}} for c in m["tool_calls"]]})
        else:
            msgs.append({"role": m["role"], "content": m["content"]})
    body = {"model": model, "messages": msgs, "temperature": 0.2}
    if max_tokens:
        body["max_tokens"] = int(max_tokens)          # cap the answer length → bounded generation time
    if local:
        body["keep_alive"] = "30m"                     # Ollama: keep the model loaded between questions
    if tools:
        body["tools"] = [{"type": "function", "function": t} for t in tools]
    if think is False:
        body["think"] = False                     # Ollama: disable thinking (ignored by other servers)
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    r = httpx.post(base.rstrip("/") + "/chat/completions", json=body, headers=headers, timeout=timeout)
    if r.status_code >= 400:
        raise LLMError(_friendly_error(base, model, r.status_code, r.text))
    msg = r.json()["choices"][0]["message"]
    calls = []
    for c in msg.get("tool_calls") or []:
        try:
            args = json.loads(c["function"].get("arguments") or "{}")
        except ValueError:
            args = {}
        if not isinstance(args, dict):
            args = {}
        args = {k: v for k, v in args.items() if k}          # gpt-oss sometimes sends {"": {}} for no-arg tools
        calls.append({"id": c.get("id") or uuid.uuid4().hex[:12], "name": c["function"]["name"], "args": args})
    import re as _re
    text = _re.sub(r"<think>.*?</think>", "", msg.get("content") or "", flags=_re.S).strip()
    return {"content": text, "tool_calls": calls}


def _gemini(key, model, system, messages, tools, timeout):
    gem3 = (model or "").lower().startswith("gemini-3")
    contents = []
    for m in messages:
        if m["role"] == "user":
            contents.append({"role": "user", "parts": [{"text": m["content"]}]})
        elif m["role"] == "assistant":
            parts = [{"text": m["content"]}] if m.get("content") else []
            for i, c in enumerate(m.get("tool_calls") or []):
                fc = {"functionCall": {"name": c["name"], "args": c["args"]}}
                if gem3 and i == 0:
                    # Gemini 3 needs the thought signature it sent back with its function call; history from
                    # another provider has none, so use Google's documented "skip" value.
                    fc["thoughtSignature"] = c.get("sig") or "skip_thought_signature_validator"
                elif c.get("sig"):
                    fc["thoughtSignature"] = c["sig"]
                parts.append(fc)
            contents.append({"role": "model", "parts": parts or [{"text": ""}]})
        elif m["role"] == "tool":
            try:
                resp = json.loads(m["content"])
            except ValueError:
                resp = {"result": m["content"]}
            if not isinstance(resp, dict):
                resp = {"result": resp}
            contents.append({"role": "user", "parts": [{"functionResponse": {"name": m["name"], "response": resp}}]})
    body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents,
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 4096}}
    if (model or "").lower().startswith("gemini-3"):
        # Gemini 3.x: keep Google's default temperature, think lightly (faster), and leave room for thought tokens.
        body["generationConfig"] = {"maxOutputTokens": 8192, "thinkingConfig": {"thinkingLevel": "low"}}
    if tools:
        body["tools"] = [{"functionDeclarations": tools}]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    r = httpx.post(url, json=body, headers={"x-goog-api-key": key}, timeout=timeout)
    if r.status_code >= 400:
        raise LLMError(f"Gemini error {r.status_code}: {r.text[:200]}")
    cand = (r.json().get("candidates") or [{}])[0]
    text, calls = "", []
    for p in (cand.get("content") or {}).get("parts") or []:
        if "text" in p and not p.get("thought"):
            text += p["text"]
        if "functionCall" in p:
            call = {"id": uuid.uuid4().hex[:12], "name": p["functionCall"]["name"], "args": p["functionCall"].get("args") or {}}
            if p.get("thoughtSignature"):
                call["sig"] = p["thoughtSignature"]
            calls.append(call)
    return {"content": text, "tool_calls": calls}


def provider_status(conf: dict, fallback=False) -> dict:
    prov = _prov(conf.get("fallback_provider") if fallback else conf.get("provider"))
    p = PROVIDERS[prov]
    need_key = bool(p.get("key")) and prov != "custom" and not p.get("key_optional")
    ok = (not need_key or bool(_key(conf, prov))) and bool(_base(conf, prov))
    hint = None
    if not ok:
        hint = (f"add the {p['label']} API key in ⚙️ Services → AI Assist" if need_key else "set the server URL in ⚙️ Services → AI Assist")
    model = _model(conf, prov, fallback)
    if ok and not model:
        ok, hint = False, "pick a model in ⚙️ Services → AI Assist"
    out = {"provider": prov, "provider_label": p["label"], "configured": ok, "model": model, "hint": hint,
           "local": p["local"] if p["local"] is not None else _looks_local(_base(conf, prov))}
    if not fallback and conf.get("fallback_provider") and conf.get("fallback_provider") != "none":
        fb = provider_status(conf, fallback=True)
        out["fallback"] = {k: fb[k] for k in ("provider", "provider_label", "model", "configured", "local")}
    return out


def _looks_local(url):
    from urllib.parse import urlparse
    import ipaddress
    h = urlparse(url or "").hostname or ""
    if h in ("localhost",):
        return True
    try:
        ip = ipaddress.ip_address(h)
        return ip.is_private or ip.is_loopback
    except ValueError:
        return False


def _call_one(conf, st, system, messages, tools, timeout):
    prov = st["provider"]
    key = _key(conf, prov)
    if PROVIDERS[prov].get("native") == "gemini":
        return _gemini(key, st["model"], system, messages, tools, timeout)
    think = None if conf.get("local_thinking") else False
    return _openai(_base(conf, prov), key or None, st["model"], system, messages, tools, timeout,
                   think=think if PROVIDERS[prov]["local"] or prov == "custom" else None,
                   max_tokens=conf.get("_max_tokens"), local=bool(PROVIDERS[prov]["local"]))


def _try(conf, st, system, messages, tools, timeout):
    last = None
    for attempt in range(3):
        try:
            return _call_one(conf, st, system, messages, tools, timeout)
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            last = LLMError(f"{st['provider_label']} not reachable: {e}")
        except LLMError as e:
            last = e
            if not any(c in str(e) for c in ("429", "500", "502", "503")):
                break
        time.sleep(1.2 * (attempt + 1))
    raise last or LLMError("AI provider failed")


def call_llm(conf: dict, system: str, messages: list, tools: list, timeout: float = 90) -> dict:
    """Main provider; if it fails (down / limit / error) and a backup provider is set, the backup answers."""
    st = provider_status(conf)
    err = None
    if st["configured"]:
        try:
            res = _try(conf, st, system, messages, tools, timeout)
            res["provider_used"] = st["provider"]
            return res
        except LLMError as e:
            err = e
    fb = st.get("fallback")
    if fb and fb["configured"]:
        fst = provider_status(conf, fallback=True)
        res = _try(conf, fst, system, messages, tools, timeout)
        res["provider_used"] = fst["provider"]
        return res
    if err:
        raise err
    raise LLMError("AI Assist isn't set up: " + (st["hint"] or "check ⚙️ Services → AI Assist"))


def list_models(conf: dict, prov: str) -> list[str]:
    """Models the saved key / server offers (for the admin's dropdown)."""
    prov = _prov(prov)
    key = _key(conf, prov)
    try:
        if PROVIDERS[prov].get("native") == "gemini":
            r = httpx.get(PROVIDERS["gemini"]["base"] + "/models", headers={"x-goog-api-key": key}, params={"pageSize": 200}, timeout=15)
            r.raise_for_status()
            return sorted(m["name"].split("/", 1)[-1] for m in r.json().get("models", [])
                          if "generateContent" in (m.get("supportedGenerationMethods") or []))
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        if prov == "anthropic":
            headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        r = httpx.get(_base(conf, prov).rstrip("/") + "/models", headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        items = data.get("data") if isinstance(data, dict) else data
        return sorted({(m.get("id") or m.get("name")) for m in items or [] if isinstance(m, dict) and (m.get("id") or m.get("name"))})
    except httpx.HTTPStatusError as e:
        raise LLMError(f"{PROVIDERS[prov]['label']}: {e.response.status_code} — check the key / URL")
    except (httpx.HTTPError, ValueError) as e:
        raise LLMError(f"{PROVIDERS[prov]['label']} not reachable: {str(e)[:120]}")
