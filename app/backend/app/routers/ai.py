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
MAX_STEPS = 6
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
}


def _conf(db):
    return svc.settings_of(db, "ai_assist")


def _system(user, conf):
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
        f"{langline}"
    )


def _tools_for(conf):
    t = {n: v for n, v in ai_tools.TOOLS.items()}
    t["app_help"] = META_TOOLS["app_help"]
    if conf.get("allow_files", True):
        t["make_file"] = META_TOOLS["make_file"]
        t["make_document"] = META_TOOLS["make_document"]
    if conf.get("allow_actions", True):
        t["propose_action"] = META_TOOLS["propose_action"]
    return t


def _shrink(obj, max_rows=40):
    if isinstance(obj, dict) and isinstance(obj.get("rows"), list) and len(obj["rows"]) > max_rows:
        obj = {**obj, "rows": obj["rows"][:max_rows], "rows_note": f"showing {max_rows} of {len(obj['rows'])} — use make_file for all"}
    s = json.dumps(obj, default=str)
    return s if len(s) < 14000 else s[:14000] + '…"}'


def _artifact(db, user, kind, name, path=None, payload=None, status="ready"):
    a = models.AiArtifact(token=secrets.token_urlsafe(18), user_id=user.id, kind=kind, name=name, path=path, payload=payload or {}, status=status)
    db.add(a); db.flush()
    return a


def _run_meta(db, user, conf, name, args, out):
    if name == "app_help":
        return app_help(args.get("topic"))
    if name == "make_file":
        fmt = (args.get("format") or "xlsx").lower()
        if fmt not in ("xlsx", "pdf", "docx"):
            raise ai_tools.ToolError("format must be xlsx, pdf or docx")
        src = args.get("source_tool")
        if src not in ai_tools.TOOLS:
            raise ai_tools.ToolError(f"source_tool must be one of {', '.join(ai_tools.TOOLS)}")
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


def converse(db, user, text: str, conv: models.AiConversation | None, case_context: str | None = None) -> dict:
    conf = _conf(db)
    limit = int(conf.get("daily_limit") or 100)
    if _daily_count(db, user) >= limit:
        raise HTTPException(429, f"Daily AI question limit ({limit}) reached. Try again tomorrow.")
    if not conv:
        conv = models.AiConversation(user_id=user.id, title=text[:80]); db.add(conv); db.flush()
    hist = (db.query(models.AiMessage).filter(models.AiMessage.conversation_id == conv.id)
            .order_by(models.AiMessage.id.desc()).limit(12).all())[::-1]
    messages = [{"role": m.role, "content": m.content or ""} for m in hist]
    prompt = text if not case_context else f"{text}\n\n(Open case context: {case_context[:1500]})"
    messages.append({"role": "user", "content": prompt})
    db.add(models.AiMessage(conversation_id=conv.id, role="user", content=text))
    audit.record(db, user, "ai.ask", entity_type="ai", detail=text[:300])
    db.commit()

    tools = _tools_for(conf)
    specs = ai_llm.tool_specs(tools)
    out = {"files": [], "actions": [], "tools": []}
    reply = ""
    try:
        for _ in range(MAX_STEPS):
            res = ai_llm.call_llm(conf, _system(user, conf), messages, specs)
            if not res["tool_calls"]:
                reply = res["content"].strip()
                break
            messages.append({"role": "assistant", "content": res["content"], "tool_calls": res["tool_calls"]})
            for call in res["tool_calls"]:
                name, args = call["name"], call.get("args") or {}
                try:
                    if name in ai_tools.TOOLS:
                        data = ai_tools.run_tool(db, user, name, args)
                        payload = ai_tools.mask(data) if conf.get("mask_pii", True) else data
                    elif name in tools:
                        payload = _run_meta(db, user, conf, name, args, out)
                        db.commit()
                    else:
                        payload = {"error": "tool not available"}
                except ai_tools.ToolError as e:
                    payload = {"error": str(e)}
                except Exception as e:
                    payload = {"error": f"tool failed: {str(e)[:150]}"}
                out["tools"].append(name)
                messages.append({"role": "tool", "tool_call_id": call["id"], "name": name, "content": _shrink(payload)})
        else:
            reply = reply or "I needed too many steps for that — please ask a narrower question."
    except ai_llm.LLMError as e:
        reply = f"⚠️ {e}"
    if not reply and (out["files"] or out["actions"]):
        reply = "Done — see below."
    db.add(models.AiMessage(conversation_id=conv.id, role="assistant", content=reply,
                            meta={"files": out["files"], "actions": out["actions"], "tools": out["tools"]}))
    conv.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"conversation_id": conv.id, "reply": reply, **out}


@router.get("/status")
def status(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    conf = _conf(db)
    return {**ai_llm.provider_status(conf), "mask_pii": conf.get("mask_pii", True), "allow_files": conf.get("allow_files", True),
            "allow_actions": conf.get("allow_actions", True), "used_today": _daily_count(db, user), "daily_limit": conf.get("daily_limit")}


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
    return converse(db, user, text[:4000], conv, body.get("case_context"))


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
