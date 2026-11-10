"""AI Assist — conversational, tool-using, strictly scoped.

The model never touches the database: it asks for tools (ai_tools.py) that run with the user's own
role scope. Phone / account numbers are masked before anything reaches the provider (setting).
Files (Excel / PDF / Word) are built on the server from the scoped rows and handed back as
download links owned by the asking user. Actions (follow-up date…) wait for the user's confirm.
"""
from __future__ import annotations

import json
import secrets
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import ai_files, ai_llm, ai_tools, audit, models, schemas
from .. import services as svc
from ..ai_help import app_help
from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/api/ai", tags=["ai"])
MAX_STEPS = 8
IST = timezone(timedelta(hours=5, minutes=30))

META_TOOLS = {
    "app_help": (None, "How to use RecoverIQ: steps for any screen or task (topic e.g. 'upload', 'DPR', 'payslip').", {"topic": "string"}),
    "make_file": (None, "Create a downloadable file from a data tool's rows. format = xlsx|pdf|docx. source_tool = one of the data tools; "
                        "source_args = JSON object of its arguments; columns = optional comma-separated column list.",
                  {"format": "xlsx|pdf|docx", "title": "string", "source_tool": "string", "source_args": "string", "columns": "string"}),
    "make_document": (None, "Create a Word or PDF document (guide, letter, report, SOP) from text you write in markdown.",
                      {"format": "docx|pdf", "title": "string", "content": "string"}),
    "propose_action": (None, "Suggest an action the user confirms with one click. type = follow_up (needs case_id, date YYYY-MM-DD, note) | "
                             "open_case (case_id) | whatsapp_draft (case_id, text).",
                       {"type": "follow_up|open_case|whatsapp_draft", "case_id": "integer", "date": "string", "note": "string", "text": "string"}),
    "make_visual": (None, "Show a visual in the chat built from REAL data. kind = chart | kpis | table | flow. "
                          "chart/kpis/table need source_tool (a data tool) + source_args (JSON object of its arguments); "
                          "chart: chart_type = bar|hbar|line|area|pie|doughnut, x = label column, y = comma-separated number columns. "
                          "kpis: optional fields = comma-separated numeric fields from the tool's totals. "
                          "table: optional columns. flow: steps = 'Step one > Step two > Step three' (for how-to / process diagrams). "
                          "Call it several times for a dashboard (e.g. kpis + 2 charts + table).",
                    {"kind": "chart|kpis|table|flow", "title": "string", "chart_type": "string", "source_tool": "string",
                     "source_args": "string", "x": "string", "y": "string", "fields": "string", "columns": "string", "steps": "string"}),
}

VISUAL_MAX_ROWS = 200


def _conf(db):
    # settings + API keys (in-app keys first, .env fallback). Never returned to the browser.
    return {**svc.settings_of(db, "ai_assist"), **svc.secrets_of(db, "ai_assist")}


_CTX_CACHE: dict = {}


def _data_context(db, user, limit: int = 3500) -> str:
    """Compact map of the data this user can see — so the model uses real bank / product / month / staff names
    instead of guessing (guessed filters were the main cause of '0 results'). Cached 2 minutes per user."""
    import time as _t
    hit = _CTX_CACHE.get(user.id)
    if hit and _t.time() - hit[0] < 120:
        return hit[1][:limit]
    try:
        ov = ai_tools.overview(db, user, compact=True)
        if "months" not in ov:
            txt = "This role has no case data."
        else:
            lines = [f"Current month: {ov['current_month']}. Months with data (newest first):"]
            for m in ov["months"]:
                lines.append(f"- {m['month']}: {m['cases']} cases, {m['paid']} paid, ₹{m['pending']:,} pending · " + "; ".join(m["portfolios"]))
            for k, label in (("banks", "Banks"), ("products", "Products"), ("buckets", "Buckets"), ("branches", "Branches"),
                             ("dispositions", "Dispositions in use"), ("staff", "Staff you can see")):
                if ov.get(k):
                    lines.append(f"{label}: " + ", ".join(map(str, ov[k])))
            txt = "\n".join(lines)
    except Exception as e:
        txt = f"(data map unavailable: {str(e)[:80]})"
    txt = txt[:3500]
    _CTX_CACHE[user.id] = (_t.time(), txt)
    return txt[:limit]


APP_MAP = ("RecoverIQ screens: Dashboard · Accounts/Portfolios (bank→product→month uploads, allocation, case drawer) · Live Sheet · "
           "Calling queue · PTP Tracker · Escalations · Litigation · Field Tracking (FOS visits, GPS, routes) · Activity · Audit Log · "
           "Monthly Archive · Team/Manpower · MIS (live, cycle, pivot) · Bank Feedback · DPR upload · Leave · Attendance · Communication "
           "templates · Devices · Connections (ViciDial) · Salary & Payslips · Security · ⚙️ Services · 🧩 Add-ons. "
           "Key terms: PTP = promise to pay; RTP = refused to pay; RNR = rang no response; FOS = field officer; TOS = total outstanding; "
           "NORM/STAB = bank target amounts (normalise / stabilise); bucket = days-past-due band (X, 1, 2, 3 BKT…); "
           "DPR = bank's daily progress report; a 'month' is the allocation month (period YYYY-MM).")


def _system(user, conf, db=None):
    lang = conf.get("language") or "auto"
    langline = "Reply in the same language as the user's question." if lang == "auto" else f"Always reply in {lang}."
    return (
        f"You are AI Assist inside RecoverIQ, a debt-collection operations platform used by agencies and lenders in India. "
        f"Today is {datetime.now(IST):%A %d %B %Y}. The user is {user.name}, role '{user.role}', branch '{user.branch or '-'}'.\n"
        "RULES:\n"
        "1. Use the tools for every number, name or case you mention. Never invent or estimate data. If a tool returns nothing or an "
        "error, say so plainly.\n"
        "2. Tools already limit data to what this user may see — never claim to see more, never guess about other people's data.\n"
        "3. Money is INR; write ₹ with Indian digit grouping. Be concise: short answer first, then a small table or bullets.\n"
        "4. When the user asks for Excel / PDF / Word / a report / a download, call make_file (data) or make_document (text) and "
        "then tell them the file is ready. Don't paste huge tables — summarise and offer a file.\n"
        "5. For how-to questions call app_help and give numbered steps using the exact screen and button names.\n"
        "6. Only suggest actions via propose_action; they run only after the user confirms. You cannot send messages, approve, "
        "pay or change data yourself.\n"
        "7. Phone and account numbers you see are masked (XXXX1234) — keep them masked.\n"
        "8. Collections must be lawful and respectful (RBI fair-practice rules): no threats, no calls before 8 am or after 7 pm.\n"
        "9. Use the exact bank / product / month / staff names from the DATA MAP below. Start with broad searches (few filters). "
        "If a tool returns 0 rows, read its why_empty / hint, fix or drop the filter and try again (or call data_overview) before "
        "telling the user nothing was found. If a tool says it showed a different month, tell the user which month you used.\n"
        "10. If the question is vague, answer with a useful overview (e.g. portfolio_summary) and offer specific follow-ups.\n"
        "11. VISUALS: when numbers compare, trend or break down (by bank, bucket, person, day…), call make_visual — kpis for "
        "headline totals, chart for comparisons/trends (line/area for days, bar/hbar for categories, doughnut for shares of a whole), "
        "table for lists. For 'dashboard' requests build 3–5 visuals (kpis first). For how-to answers add a flow visual of the steps. "
        "After visuals, give a 1–3 line insight (what stands out, what to do next) — don't repeat every number.\n"
        "12. Other data: audit_log (who did what), dpr_uploads, mis_breakdown, collection_trend, legal_cases, legal_notices, "
        "settlements, payment_links, team_leads, devices — use them when the question is about those areas.\n"
        "13. If the message includes SCREEN context, the user is looking at that page: explain what it shows, answer about it and "
        "guide them on that screen (exact button names). Use tools for anything not visible on the page.\n"
        "14. End EVERY reply with two last lines exactly like:\nMood: <one of happy, celebrate, love, sorry, surprised, wink>\n"
        "Suggestions: <short follow-up 1> | <short follow-up 2> | <short follow-up 3>\n"
        "Pick the mood that fits the answer: celebrate = good news (paid, target hit, big collection), love = the user thanked you, "
        "sorry = nothing found / an error / bad news, surprised = an unusual or surprising number, wink = a handy tip, happy = anything else.\n"
        f"{langline}\n\n{APP_MAP}\n\nDATA MAP (what this user can see):\n" + (_data_context(db, user, 1500 if conf.get("fast_mode", True) else 3500) if db is not None else "")
    )


import re as _re  # noqa: E402
import hashlib as _hashlib  # noqa: E402
import time as _time  # noqa: E402

# ⚡ Fast mode: only offer the model the tools a question needs (the tool list is the biggest part of every prompt).
_ROUTES = [
    (r"case|customer|account|unpaid|paid|pending|outstanding|priorit|search|find|list|who owes|loan|card", ("search_cases", "case_detail", "portfolio_summary")),
    (r"ptp|promise", ("ptp_list",)),
    (r"team|perform|fos|caller|staff|agent|leaderboard|rank|best|worst", ("team_performance", "team_leads")),
    (r"visit|call log|calls|activity|today did|field", ("activity",)),
    (r"attend|late|check.?in|present|absent|hours", ("attendance",)),
    (r"leave|holiday|off day", ("leave",)),
    (r"salary|payslip|pay slip", ("my_salary",)),
    (r"audit|log|who (changed|did|edited|moved)|changed|reassign|history of", ("audit_log",)),
    (r"dpr|bank report|upload", ("dpr_uploads",)),
    (r"mis|bucket|branch|break ?down|by bank|by product|cycle|portfolio|summary|overview|dashboard|resolution|paid ?%", ("mis_breakdown", "portfolio_summary")),
    (r"collect|trend|daily|day.?wise|recovery|cash", ("collection_trend",)),
    (r"legal|notice|court|hearing|sec ?138|sarfaesi|arbitration", ("legal_cases", "legal_notices")),
    (r"settle|ots|waiver|one.?time", ("settlements",)),
    (r"pay(ment)? link|paylink|upi link", ("payment_links",)),
    (r"device|login approv|phone approv", ("devices",)),
    (r"team lead|\btl\b|lead wise", ("team_leads",)),
]
_CORE = ("data_overview", "app_help", "whoami")
_DEFAULT = ("portfolio_summary", "search_cases", "case_detail", "ptp_list", "team_performance", "mis_breakdown")


def _route_tools(text: str, tools: dict, prev: list | None = None) -> dict:
    q = (text or "").lower()
    want = set(_CORE)
    for pat, names in _ROUTES:
        if _re.search(pat, q):
            want.update(names)
    if len(want) == len(_CORE):
        want.update(_DEFAULT)
    want.update(prev or [])                                   # keep what the conversation already used (follow-ups)
    if _re.search(r"chart|graph|plot|dashboard|visual|trend|compare|pie|bar", q) or "make_visual" in (prev or []):
        want.add("make_visual")
    if _re.search(r"excel|xlsx|pdf|word|docx|file|download|export|report|sop|letter|document", q):
        want.update(("make_file", "make_document"))
    if _re.search(r"follow.?up|remind|whatsapp|open (the )?case|draft|message", q):
        want.add("propose_action")
    return {n: v for n, v in tools.items() if n in want}


_GREET = _re.compile(r"^\s*(hi+|hello+|hey+|namaste|good (morning|afternoon|evening)|yo)\s*[!.👋]*\s*$", _re.I)
_THANKS = _re.compile(r"^\s*(thanks?( you)?( so much)?|thank u|thx|ty|great|awesome|nice|cool|ok(ay)?|👍|🙏)\s*[!.👍🙏]*\s*$", _re.I)


def _instant(text: str, user, origin: str):
    """Small talk answered without the model (zero wait)."""
    first = (user.name or "").split(" ")[0]
    if _GREET.match(text or ""):
        return {"reply": f"Hi {first}! 👋 Ask me about your cases, PTPs, team, MIS or this page.",
                "mood": "happy", "suggestions": ["Explain this page", "Summarise my portfolio this month", "Overdue PTPs"] if origin == "bot"
                else ["Summarise my portfolio this month", "Overdue PTPs", "My team performance"]}
    if _THANKS.match(text or ""):
        return {"reply": "Happy to help! 💙", "mood": "love", "suggestions": []}
    return None


_ANS_CACHE: dict = {}


def _cache_key(user, text, page, case_context):
    raw = f"{user.id}|{(text or '').strip().lower()}|{(page or {}).get('section')}|{_hashlib.md5(str((page or {}).get('text'))[:2500].encode()).hexdigest()}|{case_context or ''}"
    return _hashlib.md5(raw.encode()).hexdigest()

_SUGG_RE = _re.compile(r"\n*\s*\**suggestions?\**\s*[:：]\s*(.+?)\s*$", _re.I | _re.S)


def _split_suggestions(reply: str):
    """Pull the trailing 'Suggestions: a | b | c' line off the reply → (clean reply, [a, b, c])."""
    m = _SUGG_RE.search(reply or "")
    if not m or "\n" in m.group(1).strip():
        return reply, []
    sugg = [s.strip(" -•*`\"'") for s in m.group(1).split("|")]
    return reply[:m.start()].rstrip(), [s[:90] for s in sugg if 2 < len(s) <= 120][:4]


MOODS = ("happy", "celebrate", "love", "sorry", "surprised", "wink")
_MOOD_RE = _re.compile(r"\n?\s*\**mood\**\s*[:：]\s*([a-z]+)\s*\.?\s*$", _re.I)


def _split_mood(reply: str, question: str = ""):
    """Pull the trailing 'Mood: x' line off the reply; fall back to simple cues when the model didn't give one."""
    mood = None
    m = _MOOD_RE.search(reply or "")
    if m:
        reply = reply[:m.start()].rstrip()
        mood = m.group(1).lower() if m.group(1).lower() in MOODS else None
    if not mood:
        q, r = (question or "").lower(), (reply or "").lower()
        if _re.search(r"\b(thank|thanks|thx|great job|awesome|nice)\b", q):
            mood = "love"
        elif r.startswith("⚠") or _re.search(r"\b(no (cases|records|data|results)|couldn'?t|could not|not found|nothing found|error)\b", r):
            mood = "sorry"
        elif _re.search(r"\b(target (hit|achieved|met)|fully paid|congrat|well done|record high)\b", r):
            mood = "celebrate"
    return reply, mood


_DIGITS_RE = _re.compile(r"(?<![\d])(\+?\d[\d -]{8,20}\d)(?![\d])")


def _mask_page_text(t: str) -> str:
    """Phone / account / card numbers on the screen → XXXX1234 before the text goes to the AI."""
    def rep(m):
        d = _re.sub(r"\D", "", m.group(1))
        return ("XXXX" + d[-4:]) if len(d) >= 9 else m.group(1)
    return _DIGITS_RE.sub(rep, t or "")


def _page_block(page: dict | None, conf: dict) -> str:
    if not page or not conf.get("bot_read_page", True):
        return ""
    sec = str(page.get("section") or "")[:60]
    title = str(page.get("title") or "")[:120]
    text = str(page.get("text") or "")[:(2500 if conf.get("fast_mode", True) else 6000)]
    if conf.get("mask_pii", True):
        text = _mask_page_text(text)
    return f"\n\nSCREEN (what the user is looking at now) — section: {sec or '?'}; title: {title or '?'}\n{text}"


def _tools_for(conf):
    from .. import ai_tools_more
    off = ai_tools_more.disabled_tools(conf)
    t = {n: v for n, v in ai_tools.TOOLS.items() if n not in off}
    t["app_help"] = META_TOOLS["app_help"]
    if conf.get("allow_visuals", True):
        t["make_visual"] = META_TOOLS["make_visual"]
    if conf.get("allow_files", True):
        t["make_file"] = META_TOOLS["make_file"]
        t["make_document"] = META_TOOLS["make_document"]
    if conf.get("allow_actions", True):
        t["propose_action"] = META_TOOLS["propose_action"]
    return t


def _shrink(obj, max_rows=40, max_chars=14000):
    if isinstance(obj, dict) and isinstance(obj.get("rows"), list) and len(obj["rows"]) > max_rows:
        obj = {**obj, "rows": obj["rows"][:max_rows], "rows_note": f"showing {max_rows} of {len(obj['rows'])} — use make_file for all"}
    s = json.dumps(obj, default=str)
    return s if len(s) < max_chars else s[:max_chars] + '…"}'


def _artifact(db, user, kind, name, path=None, payload=None, status="ready"):
    a = models.AiArtifact(token=secrets.token_urlsafe(18), user_id=user.id, kind=kind, name=name, path=path, payload=payload or {}, status=status)
    db.add(a); db.flush()
    return a


def _json_arg(v, default):
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v) if v else default
    except (ValueError, TypeError):
        return default


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _make_visual(db, user, conf, args, allowed_tools):
    """Builds a chart / KPI / table / flow spec from a real tool result (never from numbers the model typed)."""
    kind = (args.get("kind") or "chart").lower().strip()
    title = str(args.get("title") or "").strip()[:120]
    if kind == "flow":
        steps = args.get("steps") or ""
        steps = _json_arg(steps, None) if str(steps).strip().startswith("[") else [s.strip() for s in str(steps).replace("→", ">").split(">")]
        steps = [str(s)[:120] for s in (steps or []) if str(s).strip()][:12]
        if len(steps) < 2:
            raise ai_tools.ToolError("flow needs at least 2 steps, e.g. 'Open Accounts > Pick bank > Upload file'")
        return {"kind": "flow", "title": title or "Steps", "steps": steps}
    if kind not in ("chart", "kpis", "table"):
        raise ai_tools.ToolError("kind must be chart, kpis, table or flow")
    src = args.get("source_tool")
    if src not in ai_tools.TOOLS or src not in allowed_tools:
        raise ai_tools.ToolError(f"source_tool must be one of {', '.join(n for n in ai_tools.TOOLS if n in allowed_tools)}")
    sargs = {**_json_arg(args.get("source_args"), {}), "limit": VISUAL_MAX_ROWS, "_max": VISUAL_MAX_ROWS}
    data = ai_tools.run_tool(db, user, src, sargs)
    rows = (data.get("rows") if isinstance(data, dict) else None) or []
    if conf.get("mask_pii", True):
        rows = ai_tools.mask(rows)
    if kind == "kpis":
        base = (data.get("totals") if isinstance(data, dict) else None) or {}
        if not base:
            base = {k: v for k, v in (data.items() if isinstance(data, dict) else []) if _is_num(v)}
        if not base and rows:
            base = rows[0]
        want = [f.strip() for f in (args.get("fields") or "").split(",") if f.strip()]
        items = [{"label": k.replace("_", " ").title(), "value": base[k], "key": k}
                 for k in (want or list(base.keys())) if k in base and _is_num(base[k])][:8]
        if not items:
            raise ai_tools.ToolError("no numeric totals in that tool's result for KPIs — try kind=table or chart")
        return {"kind": "kpis", "title": title, "items": items, "source": src}
    if not rows:
        raise ai_tools.ToolError("that tool returned no rows — nothing to draw")
    cols = list(rows[0].keys())
    if kind == "table":
        want = [c.strip() for c in (args.get("columns") or "").split(",") if c.strip() in cols]
        cols = want or (data.get("columns") if isinstance(data, dict) and data.get("columns") else cols)
        return {"kind": "table", "title": title, "columns": cols[:14], "rows": [{c: r.get(c) for c in cols[:14]} for r in rows],
                "source": src}
    x = args.get("x") if args.get("x") in cols else next((c for c in cols if not _is_num(rows[0].get(c))), cols[0])
    ys = [c.strip() for c in (args.get("y") or "").split(",") if c.strip() in cols and _is_num(rows[0].get(c.strip()))]
    if not ys:
        ys = [c for c in cols if c != x and _is_num(rows[0].get(c)) and c not in ("id", "case_id")][:2]
    if not ys:
        raise ai_tools.ToolError("no numeric column to plot — pass y=")
    ct = (args.get("chart_type") or "bar").lower()
    if ct not in ("bar", "hbar", "line", "area", "pie", "doughnut"):
        ct = "bar"
    if ct in ("pie", "doughnut"):
        ys = ys[:1]
    rows = rows[:60]
    return {"kind": "chart", "title": title, "chart_type": ct, "labels": [str(r.get(x) if r.get(x) is not None else "—") for r in rows],
            "series": [{"name": y.replace("_", " ").title(), "data": [r.get(y) or 0 for r in rows]} for y in ys],
            "x": x, "source": src}


def _run_meta(db, user, conf, name, args, out, allowed_tools=None):
    if name == "app_help":
        return app_help(args.get("topic"))
    if name == "make_visual":
        v = _make_visual(db, user, conf, args, allowed_tools or ai_tools.TOOLS)
        out["visuals"].append(v)
        n = len(v.get("rows") or v.get("labels") or v.get("items") or v.get("steps") or [])
        return {"visual_shown": v["kind"], "title": v.get("title"), "points": n,
                "note": "The user now sees this visual — don't repeat its numbers in a table; summarise the key insight in 1–3 lines."}
    if name == "make_file":
        fmt = (args.get("format") or "xlsx").lower()
        if fmt not in ("xlsx", "pdf", "docx"):
            raise ai_tools.ToolError("format must be xlsx, pdf or docx")
        src = args.get("source_tool")
        if src not in ai_tools.TOOLS or (allowed_tools is not None and src not in allowed_tools):
            raise ai_tools.ToolError(f"source_tool must be one of {', '.join(n for n in ai_tools.TOOLS if allowed_tools is None or n in allowed_tools)}")
        sargs = args.get("source_args") or {}
        if isinstance(sargs, str):
            try:
                sargs = json.loads(sargs or "{}")
            except ValueError:
                sargs = {}
        sargs = {**sargs, "limit": 50000, "_max": 50000}
        data = ai_tools.run_tool(db, user, src, sargs)              # scoped, unmasked — the user may see these
        rows = data.get("rows") if isinstance(data, dict) else None
        if rows is None:
            rows = [data] if isinstance(data, dict) else []
        cols = [c.strip() for c in (args.get("columns") or "").split(",") if c.strip()] or data.get("columns") or (list(rows[0].keys()) if rows else [])
        title = (args.get("title") or src.replace("_", " ").title())[:120]
        cfg = {}
        try:
            from .payroll import get_cfg
            cfg = get_cfg(db)
        except Exception:
            pass
        blob = (ai_files.table_xlsx(title, cols, rows) if fmt == "xlsx" else
                ai_files.table_pdf(title, cols, rows, cfg) if fmt == "pdf" else ai_files.doc_docx(title, "", cols, rows))
        a = _artifact(db, user, "file", f"{ai_files._safe(title)}.{fmt}")
        a.path = ai_files.save(a.token, a.name, blob)
        out["files"].append({"token": a.token, "name": a.name, "rows": len(rows)})
        audit.record(db, user, "ai.file", entity_type="ai", detail=f"{a.name} ({len(rows)} rows from {src})")
        return {"file_ready": a.name, "rows": len(rows)}
    if name == "make_document":
        fmt = (args.get("format") or "docx").lower()
        title = (args.get("title") or "Document")[:120]
        content = str(args.get("content") or "")[:60000]
        blob = ai_files.doc_docx(title, content) if fmt == "docx" else ai_files.doc_pdf(title, content)
        a = _artifact(db, user, "file", f"{ai_files._safe(title)}.{'docx' if fmt == 'docx' else 'pdf'}")
        a.path = ai_files.save(a.token, a.name, blob)
        out["files"].append({"token": a.token, "name": a.name})
        audit.record(db, user, "ai.file", entity_type="ai", detail=f"{a.name} (document)")
        return {"file_ready": a.name}
    if name == "propose_action":
        typ = args.get("type")
        cid = int(args.get("case_id") or 0)
        c = ai_tools._cases(db, user, None).filter(models.Case.id == cid).first() if cid else None
        if not c:
            raise ai_tools.ToolError("That case is not in your scope.")
        if typ == "follow_up":
            try:
                d = date.fromisoformat(str(args.get("date"))[:10])
            except ValueError:
                raise ai_tools.ToolError("date must be YYYY-MM-DD")
            a = _artifact(db, user, "action", f"Set follow-up for {c.customer_name} on {d:%d %b %Y}", status="pending",
                          payload={"type": "follow_up", "case_id": c.id, "date": d.isoformat(), "note": str(args.get("note") or "")[:300]})
            out["actions"].append({"token": a.token, "label": a.name, "type": "follow_up", "case_id": c.id})
            return {"proposed": a.name, "needs_user_confirmation": True}
        if typ == "open_case":
            out["actions"].append({"token": None, "label": f"Open case — {c.customer_name}", "type": "open_case", "case_id": c.id})
            return {"proposed": "open case button shown"}
        if typ == "whatsapp_draft":
            text = str(args.get("text") or "")[:1000]
            out["actions"].append({"token": None, "label": f"WhatsApp {c.customer_name}", "type": "whatsapp", "case_id": c.id,
                                   "phone": c.phone, "text": text})
            return {"proposed": "WhatsApp draft shown to the user (they send it themselves)"}
        raise ai_tools.ToolError("type must be follow_up, open_case or whatsapp_draft")
    raise ai_tools.ToolError("unknown tool")


def _daily_count(db, user):
    start = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    return (db.query(models.AiMessage).join(models.AiConversation, models.AiConversation.id == models.AiMessage.conversation_id)
            .filter(models.AiConversation.user_id == user.id, models.AiMessage.role == "user", models.AiMessage.created_at >= start).count())


def converse(db, user, text: str, conv: models.AiConversation | None, case_context: str | None = None,
             page: dict | None = None, origin: str = "assist") -> dict:
    conf = _conf(db)
    limit = int(conf.get("daily_limit") or 100)
    if _daily_count(db, user) >= limit:
        raise HTTPException(429, f"Daily AI question limit ({limit}) reached. Try again tomorrow.")
    if not conv:
        conv = models.AiConversation(user_id=user.id, title=(("🤖 " if origin == "bot" else "") + text)[:80]); db.add(conv); db.flush()
    hist = (db.query(models.AiMessage).filter(models.AiMessage.conversation_id == conv.id)
            .order_by(models.AiMessage.id.desc()).limit(12).all())[::-1]
    messages = [{"role": m.role, "content": m.content or ""} for m in hist]
    prompt = text if not case_context else f"{text}\n\n(Open case context: {case_context[:1500]})"
    prompt += _page_block(page, conf)
    messages.append({"role": "user", "content": prompt})
    db.add(models.AiMessage(conversation_id=conv.id, role="user", content=text))
    audit.record(db, user, "ai.ask", entity_type="ai", detail=text[:300])
    db.commit()
    t_start = _time.time()
    fast = conf.get("fast_mode", True)

    def _finish(out, reply, how):
        out["timing"] = {"total_ms": int((_time.time() - t_start) * 1000), "llm_ms": out.pop("_llm_ms", 0),
                         "calls": out.pop("_calls", 0), "how": how, "tools_offered": out.pop("_offered", None)}
        db.add(models.AiMessage(conversation_id=conv.id, role="assistant", content=reply,
                                meta={k: out.get(k) for k in ("files", "actions", "tools", "visuals", "steps", "suggestions", "mood", "timing")}))
        conv.updated_at = datetime.now(timezone.utc)
        db.commit()
        return {"conversation_id": conv.id, "reply": reply, **out}

    # 1) small talk → instant, no model
    inst = _instant(text, user, origin) if not case_context else None
    if inst:
        out = {"files": [], "actions": [], "tools": [], "visuals": [], "steps": [], "suggestions": inst["suggestions"], "mood": inst["mood"]}
        return _finish(out, inst["reply"], "instant")
    # 2) same question on the same screen in the last 2 minutes → cached answer
    ck = _cache_key(user, text, page, case_context)
    hit = _ANS_CACHE.get(ck)
    if hit and _time.time() - hit[0] < 120:
        out = json.loads(hit[1])
        return _finish(out, out.pop("_reply"), "cache")

    tools = _tools_for(conf)
    if fast:
        prev = []
        for m in hist:
            prev += list((m.meta or {}).get("tools") or []) if m.role == "assistant" else []
        tools = _route_tools(text, tools, prev[-6:])
    specs = ai_llm.tool_specs(tools)
    out = {"files": [], "actions": [], "tools": [], "visuals": [], "steps": [], "suggestions": [], "mood": None,
           "_llm_ms": 0, "_calls": 0, "_offered": len(specs)}
    reply = ""
    system = _system(user, conf, db)
    run_conf = dict(conf)
    if fast:
        run_conf["_max_tokens"] = 900
    if origin == "bot" and (conf.get("bot_model") or "").strip():
        run_conf["model"] = conf["bot_model"].strip()
    max_steps = (5 if origin == "bot" else MAX_STEPS) if fast else MAX_STEPS + 2
    try:
        for _ in range(max_steps):
            t_call = _time.time()
            res = ai_llm.call_llm(run_conf, system, messages, specs)
            out["_llm_ms"] += int((_time.time() - t_call) * 1000); out["_calls"] += 1
            if not res["tool_calls"]:
                reply = res["content"].strip()
                break
            messages.append({"role": "assistant", "content": res["content"], "tool_calls": res["tool_calls"]})
            for call in res["tool_calls"]:
                name, args = call["name"], call.get("args") or {}
                ok = True
                try:
                    if name in ai_tools.TOOLS and name in tools:
                        data = ai_tools.run_tool(db, user, name, args)
                        payload = ai_tools.mask(data) if conf.get("mask_pii", True) else data
                    elif name in tools:
                        payload = _run_meta(db, user, conf, name, args, out, allowed_tools=tools)
                        db.commit()
                    else:
                        payload = {"error": "tool not available (it may be switched off in ⚙️ Services → AI Assist)"}
                        ok = False
                except ai_tools.ToolError as e:
                    payload, ok = {"error": str(e)}, False
                except Exception as e:
                    payload, ok = {"error": f"tool failed: {str(e)[:150]}"}, False
                out["tools"].append(name)
                rows = None
                if isinstance(payload, dict):
                    rv = payload.get("count", payload.get("total_matching", payload.get("rows", payload.get("points"))))
                    rows = len(rv) if isinstance(rv, list) else (rv if isinstance(rv, int) else None)
                out["steps"].append({"tool": name, "args": {k: v for k, v in (args or {}).items() if not str(k).startswith("_")},
                                     "ok": ok, "rows": rows, "error": payload.get("error") if isinstance(payload, dict) else None})
                messages.append({"role": "tool", "tool_call_id": call["id"], "name": name,
                                 "content": _shrink(payload, 15, 6000) if fast else _shrink(payload)})
        else:
            reply = reply or "I needed too many steps for that — please ask a narrower question."
    except ai_llm.LLMError as e:
        reply = f"⚠️ {e}"
    reply, out["suggestions"] = _split_suggestions(reply)
    reply, out["mood"] = _split_mood(reply, text)
    if not reply and (out["files"] or out["actions"] or out["visuals"]):
        reply = "Here you go 👇"
    if reply and not reply.startswith("⚠") and not out["actions"] and not out["files"]:
        _ANS_CACHE[ck] = (_time.time(), json.dumps({**{k: v for k, v in out.items() if not k.startswith("_")}, "_reply": reply}, default=str))
        if len(_ANS_CACHE) > 500:
            for k in sorted(_ANS_CACHE, key=lambda k: _ANS_CACHE[k][0])[:100]:
                _ANS_CACHE.pop(k, None)
    return _finish(out, reply, "model")


@router.get("/providers/models")
def provider_models(provider: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Admin: models the saved key / server offers, for the model dropdown in ⚙️ Services."""
    if user.role != "admin":
        raise HTTPException(403, "Only Admin can configure AI Assist.")
    try:
        return {"provider": provider, "models": ai_llm.list_models(_conf(db), provider)}
    except ai_llm.LLMError as e:
        raise HTTPException(400, str(e))


@router.post("/providers/test")
def provider_test(body: dict = Body(default={}), db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Admin: one real question that needs a tool call — proves the model can actually drive AI Assist
    (small models often chat fine but can't call tools)."""
    import time as _t
    if user.role != "admin":
        raise HTTPException(403, "Only Admin can configure AI Assist.")
    conf = _conf(db)
    which = "fallback" if body.get("fallback") else "main"
    if which == "fallback":
        conf = {**conf, "provider": conf.get("fallback_provider"), "model": conf.get("fallback_model"), "fallback_provider": "none"}
    else:
        conf = {**conf, "fallback_provider": "none"}
    st = ai_llm.provider_status(conf)
    if not st["configured"]:
        return {"ok": False, "step": "setup", "detail": st["hint"], **st}
    spec = [{"name": "whoami", "description": "Who is the signed-in user (name and role).", "parameters": {"type": "object", "properties": {}}}]
    t0 = _t.time()
    try:
        r1 = ai_llm.call_llm(conf, "You are a test. Use the whoami tool to answer.", [{"role": "user", "content": "Who am I? Use the tool."}], spec, timeout=120)
    except ai_llm.LLMError as e:
        return {"ok": False, "step": "connect", "detail": str(e), **st}
    t1 = _t.time()
    if not r1["tool_calls"] or r1["tool_calls"][0]["name"] != "whoami":
        return {"ok": False, "step": "tools", "seconds": round(t1 - t0, 1), **st,
                "detail": "Connected, but the model didn't use the tool. AI Assist needs a model that supports tool/function calling — pick another model."}
    call = r1["tool_calls"][0]
    try:
        r2 = ai_llm.call_llm(conf, "Answer in one short sentence.",
                             [{"role": "user", "content": "Who am I? Use the tool."},
                              {"role": "assistant", "content": "", "tool_calls": [call]},
                              {"role": "tool", "tool_call_id": call["id"], "name": "whoami", "content": json.dumps({"name": user.name, "role": user.role})}],
                             spec, timeout=120)
    except ai_llm.LLMError as e:
        return {"ok": False, "step": "answer", "detail": str(e), **st}
    total = round(_t.time() - t0, 1)
    audit.record(db, user, "ai.test", entity_type="ai", detail=f"{st['provider']} / {st['model']}: ok in {total}s")
    db.commit()
    return {"ok": True, "seconds": total, "answer": (r2["content"] or "")[:300], **st}


@router.get("/status")
def status(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    conf = _conf(db)
    from .. import ai_tools_more
    off = ai_tools_more.disabled_tools(conf)
    return {**ai_llm.provider_status(conf), "mask_pii": conf.get("mask_pii", True), "allow_files": conf.get("allow_files", True),
            "allow_actions": conf.get("allow_actions", True), "allow_visuals": conf.get("allow_visuals", True),
            "bot_enabled": conf.get("bot_enabled", True), "bot_read_page": conf.get("bot_read_page", True),
            "bot_avatar": {"css3d": "rivet", "threejs": "rivet3d"}.get(conf.get("bot_avatar"), conf.get("bot_avatar") or "rivet"),
            "bot_user_pick": conf.get("bot_user_pick", True) is not False,
            "data_areas": [{"key": g, "label": lbl, "on": cfg_key not in conf or conf.get(cfg_key) is not False}
                           for g, (cfg_key, lbl) in ai_tools_more.GROUPS.items()],
            "tools_off": sorted(off),
            "used_today": _daily_count(db, user), "daily_limit": conf.get("daily_limit"),
            "speed": _speed(db, None if user.role == "admin" else user)}


def _speed(db, user=None, n: int = 40) -> dict:
    """Average answer time over the last n model answers (instant / cached replies counted separately)."""
    q = db.query(models.AiMessage).filter(models.AiMessage.role == "assistant")
    if user is not None:
        q = q.join(models.AiConversation, models.AiConversation.id == models.AiMessage.conversation_id).filter(models.AiConversation.user_id == user.id)
    rows = q.order_by(models.AiMessage.id.desc()).limit(n * 3).all()
    model = [r.meta["timing"] for r in rows if isinstance(r.meta, dict) and isinstance(r.meta.get("timing"), dict)
             and r.meta["timing"].get("how") == "model"][:n]
    quick = sum(1 for r in rows if isinstance(r.meta, dict) and isinstance(r.meta.get("timing"), dict) and r.meta["timing"].get("how") in ("instant", "cache"))
    if not model:
        return {"answers": 0, "quick": quick}
    tot = sorted(t["total_ms"] for t in model)
    return {"answers": len(model), "avg_s": round(sum(tot) / len(tot) / 1000, 1), "median_s": round(tot[len(tot) // 2] / 1000, 1),
            "fastest_s": round(tot[0] / 1000, 1), "slowest_s": round(tot[-1] / 1000, 1),
            "avg_calls": round(sum(t.get("calls", 0) for t in model) / len(model), 1), "quick": quick}


@router.post("/chat")
def chat(body: dict = Body(...), db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    text = str(body.get("message") or "").strip()
    if not text:
        raise HTTPException(400, "Type a question.")
    conv = None
    if body.get("conversation_id"):
        conv = db.get(models.AiConversation, int(body["conversation_id"]))
        if not conv or conv.user_id != user.id:
            raise HTTPException(404, "Conversation not found")
    page = body.get("page_context") if isinstance(body.get("page_context"), dict) else None
    return converse(db, user, text[:4000], conv, body.get("case_context"), page=page,
                    origin="bot" if body.get("origin") == "bot" else "assist")


@router.get("/conversations")
def conversations(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    rows = (db.query(models.AiConversation).filter(models.AiConversation.user_id == user.id)
            .order_by(models.AiConversation.updated_at.desc()).limit(50).all())
    return [{"id": c.id, "title": c.title, "updated_at": c.updated_at.isoformat() if c.updated_at else None} for c in rows]


@router.get("/conversations/{cid}")
def conversation(cid: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    c = db.get(models.AiConversation, cid)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "Conversation not found")
    msgs = db.query(models.AiMessage).filter(models.AiMessage.conversation_id == cid).order_by(models.AiMessage.id).all()
    return {"id": c.id, "title": c.title, "messages": [{"role": m.role, "content": m.content, **(m.meta or {})} for m in msgs]}


@router.delete("/conversations/{cid}")
def delete_conversation(cid: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    c = db.get(models.AiConversation, cid)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "Conversation not found")
    db.query(models.AiMessage).filter(models.AiMessage.conversation_id == cid).delete()
    db.delete(c); db.commit()
    return {"ok": True}


@router.get("/files/{token}")
def get_file(token: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    a = db.query(models.AiArtifact).filter_by(token=token, kind="file").first()
    if not a or a.user_id != user.id or not a.path:
        raise HTTPException(404, "File not found")
    if a.created_at and (datetime.now(timezone.utc) - a.created_at.replace(tzinfo=a.created_at.tzinfo or timezone.utc)) > timedelta(days=7):
        raise HTTPException(410, "This file has expired — ask again to regenerate it.")
    audit.record(db, user, "download", entity_type="ai", detail=a.name); db.commit()
    return FileResponse(a.path, filename=a.name)


@router.post("/actions/{token}/confirm")
def confirm_action(token: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    a = db.query(models.AiArtifact).filter_by(token=token, kind="action").first()
    if not a or a.user_id != user.id:
        raise HTTPException(404, "Action not found")
    if a.status != "pending":
        raise HTTPException(400, "Already done or cancelled.")
    p = a.payload or {}
    if p.get("type") == "follow_up":
        c = ai_tools._cases(db, user, None).filter(models.Case.id == p["case_id"]).first()
        if not c:
            raise HTTPException(403, "That case is no longer in your scope.")
        from .cases import _ensure_open
        _ensure_open(c, user)
        old = c.follow_up_date
        c.follow_up_date = date.fromisoformat(p["date"])
        if p.get("note"):
            c.remarks = ((c.remarks or "") + f"\n[{datetime.now(IST):%d-%b} {user.name}] {p['note']}").strip()[-4000:]
        audit.record(db, user, "case.follow_up", c, field="follow_up_date", old=old, new=c.follow_up_date, detail="via AI Assist (confirmed)")
    a.status = "done"
    db.commit()
    return {"ok": True}


# Back-compat for the Android app's single-question screen.
@router.post("", response_model=schemas.AIResponse)
def assist(body: schemas.AIRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    out = converse(db, user, body.prompt[:4000], None, body.context)
    extra = "".join(f"\n📎 {f['name']} — open AI Assist on the web to download." for f in out["files"])
    return schemas.AIResponse(reply=(out["reply"] or "") + extra)
