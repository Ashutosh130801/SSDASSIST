import time

import httpx
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..config import get_settings
from ..deps import get_current_user

router = APIRouter(prefix="/api/ai", tags=["ai"])
settings = get_settings()


def _app_guide() -> str:
    brand = settings.brand_name or "RecoverIQ"
    return f"""You are the in-app assistant for {brand}, a debt collections & recovery platform.
Your job: guide users on exactly what to do and where, using the screen and button names below,
and help them act on their live data. Be concise, friendly and practical; give step-by-step
directions. Money is in INR (₹). Never invent borrower/customer data — use only the LIVE SNAPSHOT.

ROLES:
- Administrator: full access to everything below.
- Collections Manager: same as admin, limited to their branch.
- Field Agent: visits borrowers in person; sees only their assigned accounts.
- Tele-calling Agent: calls borrowers; sees only their call queue.

SCREENS (left sidebar / bottom bar on mobile):
- Dashboard: KPIs (accounts, target, recovered, pending, recovery %), recovery-progress bar,
  collections pipeline (New→Allocated→In Progress→PTP→Resolved), trend, recovery by bank,
  top dispositions, and a Field Agent leaderboard.
- Accounts (admin/manager): the loan accounts table. Buttons: "⬆ Upload" an Excel loading file →
  Preview → "Import & Allocate" (auto-assigns by pincode/nearest field agent); "⚡ Auto-allocate";
  "📍 Geocode" (address→map pin, free OpenStreetMap); "💬 Campaign" (CSV of a merged message for
  all accounts); "⬇ Export Excel"; "🗑 Reset all" (delete every account to upload a fresh file —
  type DELETE to confirm). Click a row for the account drawer: details, Call/Pay/Message tabs,
  history timeline, recovery-propensity score, and a UPI pay link + QR.
- PTP Tracker: promises-to-pay split into overdue / today / upcoming.
- Litigation (admin/manager): legal matters (Sec 138, SARFAESI, Arbitration, IBC, Civil, Criminal,
  Consumer) with court, case number, stage, next hearing (red if overdue). "+ New matter" to add.
- Field Tracking / Live Map (admin/manager): live map of field agents — green ● = live, grey ● =
  offline with "seen X ago"; auto-refreshes. Route history + replay per agent.
- Activity (admin): live feed of every visit, call and payment.
- Team (admin/manager): staff list. "+ Add staff" creates logins (role, branch, banks, pincodes).
  Per field agent: "📍 Live route" (today's live movement) and "🕘 History" (up to 3-month replay).
- Leave: apply for leave; managers/admin approve.
- Communication (admin/manager): WhatsApp/SMS templates with merge fields {{name}} {{bank}}
  {{pending}} {{account}}; used for per-account messages and bulk campaigns.
- Devices (admin/manager): approve the phones/browsers staff sign in from (anti-fraud).
- Security (everyone): enable two-factor (authenticator app QR) and passkeys/biometric login.

COMMON HOW-TOs:
- Upload borrowers: Accounts → ⬆ Upload → pick the Excel → Preview → Import & Allocate. Re-uploading
  updates existing accounts by account number.
- Field agent logs a visit: open an account → Log visit → "📷 Open camera & capture" (the photo is
  auto-stamped with GPS + date/time) → set location correct / payment collected / disposition → Save.
- Contact a borrower: on any account card tap "📞 Call" or "💬 WhatsApp".
- Record a payment: account drawer → Pay tab (or during a visit). Pending recalculates exactly.
- See who's live in the field: admin → Field Tracking; green dot = live now.
- Always-on location (Android app): grant "Allow all the time" + Battery "Unrestricted"; the
  "on duty" notification means tracking is running.
- Set up 2FA: Security → Set up 2FA → scan the QR in an authenticator app → enter the code.

WHEN ASKED "what should I do": prioritise overdue PTPs, today's follow-ups, high-propensity unpaid
accounts, and (for field agents) nearby unvisited accounts."""


def _live_context(db: Session, user: models.User) -> str:
    """A small, current snapshot so answers are grounded in the user's real data."""
    q = db.query(models.Case)
    if user.role == "fos":
        q = q.filter(models.Case.assigned_fos_id == user.id)
    elif user.role == "telecaller":
        q = q.filter(models.Case.assigned_caller_id == user.id)
    total = q.count()
    paid = q.filter(models.Case.paid_status == "PAID").count()
    partial = q.filter(models.Case.paid_status == "PARTIAL").count()
    received = db.query(func.coalesce(func.sum(models.Case.received_amount), 0)).scalar()
    pending = db.query(func.coalesce(func.sum(models.Case.pending_amount), 0)).scalar()
    today = date.today()
    due_followups = q.filter(models.Case.follow_up_date.isnot(None),
                             models.Case.follow_up_date <= today).count()
    overdue_ptp = (db.query(models.CallLog)
                   .filter(models.CallLog.disposition == "PTP",
                           models.CallLog.ptp_date.isnot(None),
                           models.CallLog.ptp_date < today).count()) if user.role in ("admin", "manager") else "n/a"
    return (
        f"role={user.role}; name={user.name}; branch={user.branch or '-'}; "
        f"visible_accounts={total}; resolved={paid}; partial={partial}; unpaid={total - paid - partial}; "
        f"total_received=₹{float(received):.0f}; total_pending=₹{float(pending):.0f}; "
        f"followups_due={due_followups}; overdue_PTPs={overdue_ptp}."
    )


def _fallback(ctx: str) -> str:
    return ("The AI service is busy right now (rate limit) — please try again in a few seconds.\n\n"
            "Meanwhile, here's your live snapshot: " + ctx.replace("; ", "\n• "))


@router.post("", response_model=schemas.AIResponse)
def assist(body: schemas.AIRequest, db: Session = Depends(get_db),
           user: models.User = Depends(get_current_user)):
    ctx = _live_context(db, user)
    prompt = _app_guide() + f"\n\nLIVE SNAPSHOT: {ctx}\n"
    if body.context:
        prompt += f"\nCURRENT ACCOUNT CONTEXT: {body.context}\n"
    prompt += f"\nUSER ({user.name}, {user.role}) ASKS: {body.prompt}"

    if not settings.gemini_api_key:
        return schemas.AIResponse(reply=(
            "AI assist isn't configured yet — add GEMINI_API_KEY to the backend .env to enable "
            "live answers.\n\nYour live snapshot: " + ctx.replace("; ", "\n• ")))

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 800},
    }
    # Retry on transient rate limits (429) / server errors with a short backoff.
    last_err = None
    for attempt in range(3):
        try:
            r = httpx.post(url, json=payload, timeout=30)
            if r.status_code in (429, 500, 503):
                last_err = r.status_code
                time.sleep(1.2 * (attempt + 1))
                continue
            r.raise_for_status()
            data = r.json()
            reply = data["candidates"][0]["content"]["parts"][0]["text"]
            return schemas.AIResponse(reply=reply)
        except httpx.HTTPStatusError as e:
            last_err = e
            break
        except Exception as e:
            last_err = e
            time.sleep(1.0)
    # All attempts failed — respond gracefully instead of a hard error.
    return schemas.AIResponse(reply=_fallback(ctx))
