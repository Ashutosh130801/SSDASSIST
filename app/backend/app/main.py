import os

from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from sqlalchemy import inspect, text, func

from .database import Base, engine, get_db
from .config import get_settings
from . import models  # noqa: F401  (register models)
from .routers import (auth, users, cases, imports, visits, calls, tracking, analytics, ai,
                      devices, leaves, templates, legal, twofa, webauthn_auth, sheet, realtime,
                      team, mis, feedback, reminders, audit_log, archive, catalog, manpower,
                      notifications, dpr)

settings = get_settings()

Base.metadata.create_all(bind=engine)


def _ensure_columns():
    """Lightweight auto-migration: add columns introduced after a DB was first
    created, so existing SQLite/Postgres databases keep working without a reset."""
    wanted = {
        "cases": {
            "address2": "TEXT",
            "new_address": "TEXT",
            "new_phone": "VARCHAR(20)",
            "new_contact_by": "VARCHAR(120)",
            "new_contact_at": "TIMESTAMP",
            "period": "VARCHAR(7)",
            "close_date": "DATE",
            "closing_type": "VARCHAR(12)",
            "updated_by": "INTEGER",
            "updated_by_name": "VARCHAR(120)",
            "last_contacted_at": "TIMESTAMP",
            "follow_up_date": "DATE",
            "segment": "VARCHAR(30)",
            "enr": "NUMERIC(14,2)",
            "norm_amount": "NUMERIC(14,2)",
            "stab_amount": "NUMERIC(14,2)",
            "rollback_amount": "NUMERIC(14,2)",
            "norm_stab": "VARCHAR(10)",
            "caller_name": "VARCHAR(80)",
            "fos_name": "VARCHAR(120)",
            "team": "VARCHAR(40)",
            "team_lead": "VARCHAR(40)",
            "cat": "VARCHAR(20)",
            "visited": "BOOLEAN",
            "extra": "JSON",
            "escalated": "BOOLEAN",
            "escalated_to": "INTEGER",
            "escalated_by": "INTEGER",
            "escalated_at": "TIMESTAMP",
            "removed": "BOOLEAN",
            "removed_at": "TIMESTAMP",
            "removed_by": "INTEGER",
            "flagged": "BOOLEAN",
            "flag_reason": "VARCHAR(160)",
        },
        "users": {
            "employment_type": "VARCHAR(30)",
            "joining_date": "DATE",
            "address": "TEXT",
            "designation": "VARCHAR(80)",
            "location": "VARCHAR(80)",
            "hr_ref": "VARCHAR(30)",
            "gender": "VARCHAR(10)",
            "dob": "DATE",
            "blood_group": "VARCHAR(8)",
            "marital_status": "VARCHAR(20)",
            "ctc": "VARCHAR(30)",
            "emergency_name": "VARCHAR(80)",
            "emergency_relation": "VARCHAR(30)",
            "dra_status": "VARCHAR(20)",
            "pvc_status": "VARCHAR(20)",
            "aadhar_number": "VARCHAR(20)",
            "pan_number": "VARCHAR(20)",
            "bank_holder": "VARCHAR(120)",
            "bank_account": "VARCHAR(40)",
            "ifsc_code": "VARCHAR(20)",
            "bank_name": "VARCHAR(80)",
            "aadhar_address": "TEXT",
            "current_address": "TEXT",
            "rent_own": "VARCHAR(10)",
            "also_team_lead": "BOOLEAN",
            "tl_emp_code": "VARCHAR(20)",
            "profile_completed": "BOOLEAN",
            "must_change_password": "BOOLEAN",
            "emergency_contact": "VARCHAR(60)",
            "photo_url": "VARCHAR(255)",
            "failed_login_count": "INTEGER",
            "lockout_until": "TIMESTAMP",
            "totp_secret": "VARCHAR(64)",
            "twofa_enabled": "BOOLEAN",
            "webauthn_challenge": "VARCHAR(255)",
            "sheet_prefs": "JSON",
            "assigned_products": "JSON",
            "emp_code": "VARCHAR(20)",
            "team_lead_id": "INTEGER",
        },
        "visits": {
            "distance_from_case_m": "FLOAT",
        },
        "import_batches": {
            "product": "VARCHAR(80)",
        },
    }
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, cols in wanted.items():
            if not insp.has_table(table):
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in cols.items():
                if name not in existing:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}'))


_ensure_columns()


def _backfill_emp_codes():
    """Give every existing staff member a caller/staff ID (emp_code) if they don't have one."""
    from .database import SessionLocal
    from .routers.users import generate_emp_code
    from . import models as _m
    db = SessionLocal()
    try:
        missing = db.query(_m.User).filter((_m.User.emp_code.is_(None)) | (_m.User.emp_code == "")).all()
        for u in missing:
            u.emp_code = generate_emp_code(db, u.role)
            db.flush()
        if missing:
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def _backfill_norm_stab():
    """Retrofit the NORM/STAB mark onto cases imported before that rule existed, using the
    STATUS (final_status) they already carry — so the MIS NORM%/STAB% populate on restart
    without re-uploading."""
    from .database import SessionLocal
    from . import models as _m
    db = SessionLocal()
    try:
        rows = db.query(_m.Case).filter(
            (_m.Case.norm_stab.is_(None)) | (_m.Case.norm_stab == ""),
            func.upper(_m.Case.final_status).in_(("NORM", "STAB")),
        ).all()
        for c in rows:
            c.norm_stab = (c.final_status or "").upper()
        if rows:
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def _fix_negative_pending():
    """One-time repair: an earlier amount-edit path computed pending as funding − received
    (funding is 0 for CC/PL-BL) without using TOS, leaving negative pendings. Recompute those
    from the real base (funding → TOS → ENR) − received, floored at 0, so pending shows the
    true remaining balance (TOS − received) even on resolved cases. Self-limiting: only touches
    rows where pending < 0, so it's a no-op on every restart after the first."""
    from decimal import Decimal
    from .database import SessionLocal
    from . import models as _m
    from .routers.cases import _pay_base_total
    db = SessionLocal()
    try:
        rows = db.query(_m.Case).filter(_m.Case.pending_amount < 0).all()
        for c in rows:
            pend = _pay_base_total(c) - Decimal(c.received_amount or 0)
            c.pending_amount = pend if pend > 0 else Decimal(0)
        if rows:
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def _backfill_dual_role_flag():
    """The also_team_lead column is new, so rows created before it exists carry NULL. Set them
    to 0 so the value is a real boolean everywhere (the native app rejects a null here)."""
    from sqlalchemy import text
    with engine.begin() as conn:
        try:
            conn.execute(text("UPDATE users SET also_team_lead = 0 WHERE also_team_lead IS NULL"))
        except Exception:
            pass


def _reset_rtp_promises():
    """One-time cleanup: RTP = 'Refuse to Pay' was previously treated as a promise, so those
    cases are stuck in 'ptp' status with a follow-up date. Pull them out of PTP and drop a red
    caution flag so HR/managers can spot and reconsider them. Self-limiting: only touches RTP
    cases still parked in ptp / with a follow-up, so it's a no-op after the first run."""
    from .database import SessionLocal
    from . import models as _m
    from sqlalchemy import func, or_
    db = SessionLocal()
    try:
        rows = (db.query(_m.Case)
                .filter(func.upper(_m.Case.disposition) == "RTP",
                        or_(_m.Case.status == "ptp", _m.Case.follow_up_date.isnot(None)))
                .all())
        for c in rows:
            if (c.paid_status or "").upper() == "PAID":
                continue                                  # already resolved — leave it
            c.status = "in_progress"
            c.follow_up_date = None
            c.flagged = True
            c.flag_reason = "RTP (Refuse to Pay) — was in PTP; review / take action"
        if rows:
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


_backfill_emp_codes()
_backfill_norm_stab()
_fix_negative_pending()
_backfill_dual_role_flag()
_reset_rtp_promises()


def _maybe_seed():
    """First-deploy convenience: create demo staff/admin when SEED_ON_START=1."""
    if not settings.seed_on_start:
        return
    from .database import SessionLocal
    from .seed import seed_users
    db = SessionLocal()
    try:
        seed_users(db)
    finally:
        db.close()


_maybe_seed()

# Production guardrails
_is_prod = settings.environment.lower() == "production"
if _is_prod and settings.secret_key in ("dev-secret-change-me", "", "change-this-to-a-long-random-string"):
    raise RuntimeError("Refusing to start in production with a default SECRET_KEY — set a strong one.")

app = FastAPI(title="SSD Recovery API", version="1.0.0",
              docs_url=None if _is_prod else "/docs",
              redoc_url=None)

# CORS: same-origin by default (backend serves the frontend). Only widen if configured.
_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins if _origins else ([] if _is_prod else ["*"]),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def _security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "SAMEORIGIN"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return resp


for r in (auth, users, cases, imports, visits, calls, tracking, analytics, ai, devices,
          leaves, templates, legal, twofa, webauthn_auth, sheet, realtime, team, mis, feedback,
          reminders, audit_log, archive, catalog, manpower, notifications, dpr):
    app.include_router(r.router)


@app.on_event("startup")
async def _capture_loop():
    import asyncio
    from .routers import realtime as _rt
    _rt.set_loop(asyncio.get_running_loop())


@app.get("/api/config")
def config(db: Session = Depends(get_db)):
    from .products import catalog
    from .routers.cases import _current_period, _next_period
    return {
        "bank_products": catalog(db),
        "current_period": _current_period(),
        "next_period": _next_period(),
        "google_maps_api_key": settings.google_maps_api_key,
        "google_client_id": settings.google_client_id,
        "location_ping_seconds": settings.location_ping_seconds,
        "ai_enabled": bool(settings.gemini_api_key),
        "upi_vpa": settings.upi_vpa,
        "upi_payee_name": settings.upi_payee_name,
        "geofence_metres": settings.geofence_metres,
        "brand_name": settings.brand_name,
        "brand_tagline": settings.brand_tagline,
    }


@app.get("/api/health")
def health():
    return {"status": "ok"}


BASE_DIR = os.path.dirname(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

if os.path.isdir(FRONTEND_DIR):
    # Serve the PWA from the site root so index.html's relative assets
    # (styles.css, app.jsx, manifest, sw.js) resolve correctly.
    # Mounted LAST so all /api/* and /uploads routes take precedence.
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
