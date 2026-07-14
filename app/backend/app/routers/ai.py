import json
import httpx

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..config import get_settings
from ..deps import get_current_user

router = APIRouter(prefix="/api/ai", tags=["ai"])
settings = get_settings()


def _live_context(db: Session, user: models.User) -> str:
    """Give the model a small, current snapshot so answers are grounded in real data."""
    q = db.query(models.Case)
    if user.role == "fos":
        q = q.filter(models.Case.assigned_fos_id == user.id)
    elif user.role == "telecaller":
        q = q.filter(models.Case.assigned_caller_id == user.id)
    total = q.count()
    received = db.query(func.coalesce(func.sum(models.Case.received_amount), 0)).scalar()
    pending = db.query(func.coalesce(func.sum(models.Case.pending_amount), 0)).scalar()
    paid = q.filter(models.Case.paid_status == "PAID").count()
    return (
        f"Role={user.role}; visible_cases={total}; paid_cases={paid}; "
        f"total_received={received}; total_pending={pending}."
    )


@router.post("", response_model=schemas.AIResponse)
def assist(body: schemas.AIRequest, db: Session = Depends(get_db),
           user: models.User = Depends(get_current_user)):
    ctx = _live_context(db, user)
    system = (
        "You are the SSD Recovery assistant for a loan-recovery enterprise working with "
        "ICICI, RBL and Axis banks. Help admins, field officers and telecallers with "
        "collections strategy, prioritising cases, drafting call scripts and polite payment "
        "reminders, and explaining the dashboard. Be concise and practical. Never invent "
        "customer data; use only the snapshot provided. Money is in INR."
    )
    prompt = f"{system}\n\nLIVE SNAPSHOT: {ctx}\n"
    if body.context:
        prompt += f"\nCASE CONTEXT: {body.context}\n"
    prompt += f"\nUSER ({user.name}, {user.role}) ASKS: {body.prompt}"

    if not settings.gemini_api_key:
        # graceful offline fallback so the feature still responds
        return schemas.AIResponse(reply=(
            "AI assist is not configured yet — add GEMINI_API_KEY to the backend .env to enable "
            "live answers.\n\nBased on your current data: " + ctx.replace(";", ",")
        ))

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        r = httpx.post(url, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        reply = data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI service error: {e}")
    return schemas.AIResponse(reply=reply)
