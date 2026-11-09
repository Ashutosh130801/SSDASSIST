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


DEFAULT_MODELS = {"gemini": "gemini-2.0-flash", "openrouter": "openai/gpt-4o-mini", "local": "qwen2.5:14b"}


def _schema(params: dict) -> dict:
    props = {}
    for k, t in params.items():
        typ = "number" if t == "number" else "integer" if t == "integer" else "string"
        props[k] = {"type": typ, "description": t if "|" in t else k.replace("_", " ")}
    return {"type": "object", "properties": props}


def tool_specs(tools: dict) -> list[dict]:
    return [{"name": n, "description": d, "parameters": _schema(p)} for n, (_, d, p) in tools.items()]


def _openai(base, key, model, system, messages, tools, timeout):
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
    body = {"model": model, "messages": msgs, "temperature": 0.2,
            "tools": [{"type": "function", "function": t} for t in tools]}
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    r = httpx.post(base.rstrip("/") + "/chat/completions", json=body, headers=headers, timeout=timeout)
    if r.status_code >= 400:
        raise LLMError(f"AI provider error {r.status_code}: {r.text[:200]}")
    msg = r.json()["choices"][0]["message"]
    calls = []
    for c in msg.get("tool_calls") or []:
        try:
            args = json.loads(c["function"].get("arguments") or "{}")
        except ValueError:
            args = {}
        calls.append({"id": c.get("id") or uuid.uuid4().hex[:12], "name": c["function"]["name"], "args": args})
    return {"content": msg.get("content") or "", "tool_calls": calls}


def _gemini(key, model, system, messages, tools, timeout):
    contents = []
    for m in messages:
        if m["role"] == "user":
            contents.append({"role": "user", "parts": [{"text": m["content"]}]})
        elif m["role"] == "assistant":
            parts = [{"text": m["content"]}] if m.get("content") else []
            parts += [{"functionCall": {"name": c["name"], "args": c["args"]}} for c in m.get("tool_calls") or []]
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
            "tools": [{"functionDeclarations": tools}], "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2048}}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    r = httpx.post(url, json=body, headers={"x-goog-api-key": key}, timeout=timeout)
    if r.status_code >= 400:
        raise LLMError(f"Gemini error {r.status_code}: {r.text[:200]}")
    cand = (r.json().get("candidates") or [{}])[0]
    text, calls = "", []
    for p in (cand.get("content") or {}).get("parts") or []:
        if "text" in p:
            text += p["text"]
        if "functionCall" in p:
            calls.append({"id": uuid.uuid4().hex[:12], "name": p["functionCall"]["name"], "args": p["functionCall"].get("args") or {}})
    return {"content": text, "tool_calls": calls}


def provider_status(conf: dict) -> dict:
    s = get_settings()
    prov = conf.get("provider") or "gemini"
    ok = (prov == "local") or (prov == "gemini" and bool(s.gemini_api_key)) or (prov == "openrouter" and bool(s.openrouter_api_key))
    return {"provider": prov, "configured": ok,
            "model": conf.get("model") or (s.gemini_model if prov == "gemini" else s.openrouter_model if prov == "openrouter" else DEFAULT_MODELS["local"]),
            "hint": None if ok else ("Add GEMINI_API_KEY to the server .env" if prov == "gemini" else "Add OPENROUTER_API_KEY to the server .env")}


def call_llm(conf: dict, system: str, messages: list, tools: list, timeout: float = 90) -> dict:
    s = get_settings()
    st = provider_status(conf)
    if not st["configured"]:
        raise LLMError("AI Assist isn't set up: " + st["hint"])
    last = None
    for attempt in range(3):
        try:
            if st["provider"] == "gemini":
                return _gemini(s.gemini_api_key, st["model"], system, messages, tools, timeout)
            if st["provider"] == "openrouter":
                return _openai("https://openrouter.ai/api/v1", s.openrouter_api_key, st["model"], system, messages, tools, timeout)
            return _openai(conf.get("local_url") or "http://127.0.0.1:11434/v1", None, st["model"], system, messages, tools, timeout)
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            last = LLMError(f"AI provider not reachable: {e}")
        except LLMError as e:
            last = e
            if not any(c in str(e) for c in ("429", "500", "503")):
                break
        time.sleep(1.2 * (attempt + 1))
    raise last or LLMError("AI provider failed")
