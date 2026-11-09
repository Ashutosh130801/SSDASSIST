"""Service registry — every feature of RecoverIQ as a switchable "service".

Admin turns services on/off and sets their options in ⚙️ Services (top-right). A service that is off:
  • disappears from every user's menu (the web/app read GET /api/services), and
  • its API answers 423 "Service turned off by your administrator" (middleware in main.py).

Core services that the app cannot work without are marked `required` and cannot be switched off.
Add-ons live under 🧩 Add-ons. `reminder` services are planned and shown as "coming soon".
Settings for each service are declared here (schema) so the admin form is generated, and stored as
JSON in app_settings["services"].
"""
from __future__ import annotations

import json
import time

from sqlalchemy.orm import Session

from . import models

# field types: bool | number | text | select | list | time | secret_hint (shows which .env key is used)
SERVICES: list[dict] = [
    # ───────── core ─────────
    {"key": "accounts", "name": "Accounts & Portfolios", "group": "core", "required": True, "icon": "🗂️",
     "desc": "Portfolios, uploads, allocation, case drawer, corrections, joint allocation.",
     "nav": ["cases", "portfolios", "fcases", "jointcases"], "api": ["/api/cases", "/api/import", "/api/catalog"]},
    {"key": "live_sheet", "name": "Live Sheet", "group": "core", "icon": "📊", "desc": "Spreadsheet view callers work in, live-synced.",
     "nav": ["sheet"], "api": ["/api/sheet"]},
    {"key": "calling", "name": "Calling queue & call logs", "group": "core", "icon": "📞", "desc": "Caller queue, dispositions, call history.",
     "nav": ["queue"], "api": ["/api/calls"]},
    {"key": "ptp", "name": "PTP Tracker & reminders", "group": "core", "icon": "🤝", "desc": "Promises to pay — overdue / today / upcoming.",
     "nav": ["ptp"], "api": ["/api/reminders"]},
    {"key": "escalations", "name": "Escalations", "group": "core", "icon": "🚩", "desc": "Pull cases from FOS / callers for review.", "nav": ["escalations"]},
    {"key": "field", "name": "Field visits & GPS tracking", "group": "core", "icon": "📍",
     "desc": "FOS visits with GPS photos, live map, route history, fake-visit trust score.", "nav": ["map", "fmap"], "api": ["/api/tracking", "/api/visits"]},
    {"key": "mis", "name": "MIS & reports", "group": "core", "icon": "📈", "desc": "Live MIS, cycle MIS, MIS pivot Excel, targets.",
     "nav": ["mis", "myperf"], "api": ["/api/mis", "/api/analytics"]},
    {"key": "feedback", "name": "Bank feedback sheet", "group": "core", "icon": "🏦", "desc": "Per-portfolio feedback for banks.", "nav": ["feedback"], "api": ["/api/feedback"]},
    {"key": "dpr", "name": "DPR bulk updates", "group": "core", "icon": "🔄", "desc": "Daily progress report uploads from banks.", "api": ["/api/dpr"]},
    {"key": "legal", "name": "Litigation tracker", "group": "core", "icon": "⚖️", "desc": "Legal matters, hearings.", "nav": ["legal"], "api": ["/api/legal"]},
    {"key": "archive", "name": "Monthly archive", "group": "core", "icon": "🗄️", "desc": "Closed months.", "nav": ["archive"], "api": ["/api/archive"]},
    {"key": "team", "name": "Team, Manpower & HR letters", "group": "core", "required": True, "icon": "👥",
     "desc": "Staff, roles, manpower records, documents, offer letters, change requests.",
     "nav": ["staff", "manpower", "preqs", "tldash", "profile"], "api": ["/api/team", "/api/users", "/api/manpower"]},
    {"key": "attendance", "name": "Attendance & presence", "group": "core", "icon": "🕐", "desc": "Check-in/out, late, half day, salary-cycle sheets.",
     "nav": ["attendance"], "api": ["/api/attendance"]},
    {"key": "leave", "name": "Leave", "group": "core", "icon": "🌴", "desc": "Apply / approve leave, balances.", "nav": ["leave"], "api": ["/api/leaves"]},
    {"key": "communication", "name": "Message templates", "group": "core", "icon": "💬", "desc": "WhatsApp / SMS templates and campaigns.",
     "nav": ["templates"], "api": ["/api/templates"]},
    {"key": "chat", "name": "Team chat & voice calls", "group": "core", "icon": "🗨️", "desc": "In-app chat, broadcasts, WebRTC voice calls.",
     "api": ["/api/chat", "/api/rtc"]},
    {"key": "work_tools", "name": "To-Do, RTSB & Live Monitor", "group": "core", "icon": "📋", "desc": "Work queue, target vs achievement, live monitor.",
     "api": ["/api/todo", "/api/monitor", "/api/liner"]},
    {"key": "dialer", "name": "Dialer integration (ViciDial)", "group": "core", "icon": "☎️", "desc": "Click-to-call, screen-pop, live call window, dispositions.",
     "nav": ["connections"], "api": ["/api/integration"]},
    {"key": "devices", "name": "Device approval", "group": "core", "icon": "📱", "desc": "Approve phones/browsers staff sign in from.", "nav": ["devices"], "api": ["/api/devices"]},
    {"key": "audit", "name": "Activity & audit log", "group": "core", "required": True, "icon": "📜", "desc": "Who did what, when.",
     "nav": ["records", "audit"], "api": ["/api/audit"]},
    {"key": "salary", "name": "Salary & Payslips", "group": "core", "icon": "💰",
     "desc": "Payroll, payslips, income tax, full & final, bank files, payout gateway.", "nav": ["payroll", "payslips"],
     "api": ["/api/payroll", "/api/payouts"]},
    # ───────── add-ons ─────────
    {"key": "ai_assist", "name": "AI Assist", "group": "addon", "icon": "✨", "default_on": True,
     "desc": "Asks your data in plain words — every answer limited to what the user may see. Makes Excel / PDF / Word files, guides, drafts.",
     "nav": ["ai"], "api": ["/api/ai"],
     "settings": [
         {"key": "provider", "label": "AI provider", "type": "select", "default": "gemini",
          "options": {"local": "Local model on your server (Ollama / vLLM)", "gemini": "Google Gemini", "openrouter": "OpenRouter"}},
         {"key": "model", "label": "Model name (blank = provider default)", "type": "text", "default": ""},
         {"key": "local_url", "label": "Local model URL (OpenAI-compatible)", "type": "text", "default": "http://127.0.0.1:11434/v1"},
         {"key": "mask_pii", "label": "Mask phone & account numbers sent to the AI", "type": "bool", "default": True},
         {"key": "language", "label": "Answer language", "type": "select", "default": "auto",
          "options": {"auto": "Same as the question", "English": "English", "Telugu": "Telugu", "Hindi": "Hindi"}},
         {"key": "daily_limit", "label": "Questions per user per day", "type": "number", "default": 100},
         {"key": "allow_files", "label": "Allow Excel / PDF / Word generation", "type": "bool", "default": True},
         {"key": "allow_actions", "label": "Allow actions (with user confirmation)", "type": "bool", "default": True},
         {"key": "keys", "label": "API keys", "type": "secret_hint", "default": "GEMINI_API_KEY / OPENROUTER_API_KEY in the server .env"},
     ]},
    {"key": "compliance", "name": "Compliance guardrails", "group": "addon", "icon": "🛡️",
     "desc": "RBI calling hours, attempt caps, agent certification, DPDP data retention & requests.", "api": ["/api/compliance"],
     "settings": [
         {"key": "enforce_hours", "label": "Enforce contact hours (dialling blocked; calls / visits logged outside are flagged)", "type": "bool", "default": True},
         {"key": "hours_from", "label": "Contact allowed from", "type": "time", "default": "08:00"},
         {"key": "hours_to", "label": "Contact allowed until", "type": "time", "default": "19:00"},
         {"key": "max_calls_per_day", "label": "Max call attempts per customer per day", "type": "number", "default": 3},
         {"key": "max_visits_per_week", "label": "Max field visits per customer per week", "type": "number", "default": 3},
         {"key": "block_uncertified", "label": "Block agents with expired / missing certification", "type": "bool", "default": False},
         {"key": "retention_months", "label": "Keep closed-case personal data for (months, 0 = forever)", "type": "number", "default": 0},
     ]},
    {"key": "payments", "name": "Payment links & auto-reconciliation", "group": "addon", "icon": "💳",
     "desc": "Send pay links / UPI; payments reconcile into the case automatically; customer self-service page.", "api": ["/api/paylinks", "/pay"],
     "settings": [
         {"key": "provider", "label": "Payment gateway", "type": "select", "default": "razorpay",
          "options": {"razorpay": "Razorpay Payment Links (auto-reconcile)", "manual_upi": "Plain UPI link (reconcile by statement upload)"}},
         {"key": "min_amount", "label": "Smallest amount a customer may pay (₹)", "type": "number", "default": 100},
         {"key": "expiry_days", "label": "Link valid for (days)", "type": "number", "default": 7},
         {"key": "allow_partial", "label": "Allow part payment", "type": "bool", "default": True},
         {"key": "keys", "label": "API keys", "type": "secret_hint", "default": "RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET / RAZORPAY_WEBHOOK_SECRET in .env"},
     ]},
    {"key": "outreach", "name": "Digital outreach journeys", "group": "addon", "icon": "📣",
     "desc": "Automatic SMS / WhatsApp / email steps by days-past-due or PTP date, before calls and visits.", "api": ["/api/outreach"],
     "settings": [
         {"key": "sms_provider", "label": "SMS provider", "type": "select", "default": "none",
          "options": {"none": "Not connected (export lists)", "msg91": "MSG91 (DLT template)"}},
         {"key": "msg91_template_id", "label": "MSG91 flow / template id", "type": "text", "default": ""},
         {"key": "whatsapp_provider", "label": "WhatsApp provider", "type": "select", "default": "none",
          "options": {"none": "Not connected (click-to-WhatsApp)", "meta": "WhatsApp Cloud API"}},
         {"key": "wa_template", "label": "WhatsApp approved template name", "type": "text", "default": ""},
         {"key": "wa_lang", "label": "WhatsApp template language code", "type": "text", "default": "en"},
         {"key": "daily_cap", "label": "Max messages per customer per day", "type": "number", "default": 2},
         {"key": "auto_run", "label": "Run journeys automatically every day (10 am, within contact hours)", "type": "bool", "default": False},
         {"key": "keys", "label": "API keys", "type": "secret_hint", "default": "MSG91_AUTH_KEY / WHATSAPP_TOKEN / WHATSAPP_PHONE_ID in .env"},
     ]},
    {"key": "settlement", "name": "Settlement / OTS", "group": "addon", "icon": "🤝",
     "desc": "One-time-settlement offers with approval limits, settlement letters, instalment tracking.", "api": ["/api/settlements"],
     "settings": [
         {"key": "caller_max_waiver_pct", "label": "Caller / FOS can offer waiver up to %", "type": "number", "default": 0},
         {"key": "teamlead_max_waiver_pct", "label": "Team lead can approve waiver up to %", "type": "number", "default": 10},
         {"key": "manager_max_waiver_pct", "label": "Manager / HO can approve waiver up to %", "type": "number", "default": 30},
         {"key": "letter_footer", "label": "Settlement letter footer", "type": "text", "default": "This offer is subject to the lender's final approval."},
     ]},
    {"key": "smart_allocation", "name": "Smart allocation & route plan", "group": "addon", "icon": "🧠",
     "desc": "Likelihood-to-pay score, best time to call, capacity-based allocation, optimised FOS route for the day.",
     "api": ["/api/smart"],
     "settings": [
         {"key": "fos_capacity", "label": "Max open cases per FOS", "type": "number", "default": 150},
         {"key": "caller_capacity", "label": "Max open cases per caller", "type": "number", "default": 400},
         {"key": "route_stops", "label": "Visits in a daily route", "type": "number", "default": 15},
     ]},
    {"key": "legal_notices", "name": "Legal notices (bulk)", "group": "addon", "icon": "📨",
     "desc": "Bulk demand / Sec 138 / arbitration notices as PDF, dispatch & delivery tracking.", "api": ["/api/notices"],
     "settings": [
         {"key": "signatory", "label": "Signed by (advocate / officer)", "type": "text", "default": ""},
         {"key": "reply_days", "label": "Days given to respond", "type": "number", "default": 15},
     ]},
    {"key": "analytics", "name": "Advanced analytics", "group": "addon", "icon": "📊",
     "desc": "Roll-forward / roll-back by bucket, resolution by vintage, collection forecast, agent productivity.", "api": ["/api/insights"]},
    {"key": "billing", "name": "Agency billing & invoices", "group": "addon", "icon": "🧾",
     "desc": "Commission rates per bank / product / bucket, monthly invoices to banks with GST.", "api": ["/api/billing"],
     "settings": [
         {"key": "gst_rate", "label": "GST %", "type": "number", "default": 18},
         {"key": "invoice_prefix", "label": "Invoice number prefix", "type": "text", "default": "INV"},
         {"key": "gstin", "label": "Your GSTIN", "type": "text", "default": ""},
     ]},
    {"key": "skip_tracing", "name": "Skip tracing", "group": "addon", "icon": "🔎",
     "desc": "Finds alternate numbers / addresses for unreachable customers from your own data (other loans, field updates).",
     "api": ["/api/skiptrace"]},
    {"key": "open_api", "name": "Open API & webhooks", "group": "addon", "icon": "🔌",
     "desc": "API keys for lenders / your systems; webhooks on payment, PTP, visit, disposition.", "api": ["/api/open", "/api/apikeys"]},
    {"key": "ai_call_analysis", "name": "AI on calls", "group": "addon", "icon": "🎧", "reminder": True,
     "desc": "Transcripts, PTP / dispute detection, abuse alerts, call quality scores. Planned — needs the call-audio integration."},
    {"key": "ai_voice_bot", "name": "AI voice bot", "group": "addon", "icon": "🤖", "reminder": True,
     "desc": "Bot calls for reminders and PTP confirmations in Telugu / Hindi / English. Planned."},
]

BY_KEY = {s["key"]: s for s in SERVICES}
_cache: dict = {"t": 0.0, "v": None}


def _defaults(s):
    return {f["key"]: f.get("default") for f in s.get("settings") or [] if f["type"] != "secret_hint"}


def load(db: Session, fresh=False) -> dict:
    """{key: {"enabled": bool, "settings": {...}}} merged over defaults; cached for 5 s."""
    if not fresh and _cache["v"] is not None and time.time() - _cache["t"] < 5:
        return _cache["v"]
    row = db.get(models.AppSetting, "services")
    stored = {}
    if row and row.value:
        try:
            stored = json.loads(row.value)
        except ValueError:
            stored = {}
    out = {}
    for s in SERVICES:
        st = stored.get(s["key"]) or {}
        # Core services start ON; add-ons start OFF (Admin switches them on) unless marked default_on.
        enabled = True if s.get("required") else bool(st.get("enabled", s.get("default_on", s["group"] == "core")))
        if s.get("reminder"):
            enabled = False
        out[s["key"]] = {"enabled": enabled, "settings": {**_defaults(s), **(st.get("settings") or {})}}
    _cache.update(t=time.time(), v=out)
    return out


def save(db: Session, key: str, enabled: bool | None, settings: dict | None) -> dict:
    s = BY_KEY[key]
    row = db.get(models.AppSetting, "services")
    stored = {}
    if row and row.value:
        try:
            stored = json.loads(row.value)
        except ValueError:
            stored = {}
    cur = stored.get(key) or {}
    if enabled is not None and not s.get("required") and not s.get("reminder"):
        cur["enabled"] = bool(enabled)
    if settings is not None:
        allowed = {f["key"]: f for f in s.get("settings") or [] if f["type"] != "secret_hint"}
        clean = dict(cur.get("settings") or {})
        for k, v in settings.items():
            f = allowed.get(k)
            if not f:
                continue
            if f["type"] == "bool":
                v = bool(v)
            elif f["type"] == "number":
                try:
                    v = float(v)
                    v = int(v) if v == int(v) else v
                except (TypeError, ValueError):
                    raise ValueError(f"{f['label']}: must be a number")
            elif f["type"] == "select":
                if v not in f["options"]:
                    raise ValueError(f"{f['label']}: invalid choice")
            elif f["type"] == "time":
                v = str(v)[:5]
            else:
                v = str(v)[:500]
            clean[k] = v
        cur["settings"] = clean
    stored[key] = cur
    if not row:
        row = models.AppSetting(key="services", value="{}")
        db.add(row)
    row.value = json.dumps(stored)
    db.flush()
    _cache.update(t=0.0, v=None)
    return stored[key]


def is_on(db: Session, key: str) -> bool:
    return load(db).get(key, {}).get("enabled", True)


def settings_of(db: Session, key: str) -> dict:
    return load(db).get(key, {}).get("settings", {})


def api_owner(path: str) -> str | None:
    """Which service owns this API path (longest prefix wins)."""
    best, key = 0, None
    for s in SERVICES:
        for p in s.get("api") or []:
            if (path == p or path.startswith(p + "/")) and len(p) > best:
                best, key = len(p), s["key"]
    return key
