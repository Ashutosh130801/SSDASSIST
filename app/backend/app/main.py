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
                      notifications, dpr, support)

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
            "esc_prev_fos_id": "INTEGER",
            "esc_prev_caller_id": "INTEGER",
            "removed": "BOOLEAN",
            "removed_at": "TIMESTAMP",
            "removed_by": "INTEGER",
            "flagged": "BOOLEAN",
            "flag_reason": "VARCHAR(160)",
            "branch_explicit": "BOOLEAN",
            "auto_debit": "BOOLEAN",
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
            "blocked_reason": "VARCHAR(200)",
            "blocked_at": "TIMESTAMP",
            "blocked_by": "INTEGER",
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
        "devices": {
            "approved_at": "TIMESTAMP",
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


def _recompute_pay_status():
    """Re-derive every case's PAID / PARTIAL / UNPAID + pending against the settlement (NORM/STAB)
    money rules, so historical rows match the single source of truth in app.paymath. Idempotent:
    only rows whose status/pending actually change are written."""
    from .database import SessionLocal
    from . import models as _m, paymath as _pm
    db = SessionLocal()
    try:
        changed = 0
        for c in db.query(_m.Case).filter(_m.Case.removed.isnot(True)).yield_per(500):
            before = (c.paid_status, c.pending_amount, c.status)
            _pm.recompute(c)
            if (c.paid_status, c.pending_amount, c.status) != before:
                changed += 1
        if changed:
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


_recompute_pay_status()


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


def _backfill_pending():
    """Fill the stored pending_amount on any case that still shows 0/NULL but actually has a
    balance. Freshly-uploaded rows never had pending written (it was only set when a payment or
    edit landed), so their portfolio cards read ₹0 even though TOS/ENR carry a real figure. Here
    we recompute pending = base(FUNDING → TOS → ENR) − received, floored at 0, for exactly those
    stale rows. Self-limiting: only touches pending 0/NULL rows whose real balance is > 0, so a
    genuinely resolved case (received ≥ base → 0) and any already-correct row are left untouched,
    making this a no-op on every restart after the first."""
    from decimal import Decimal
    from sqlalchemy import or_
    from .database import SessionLocal
    from . import models as _m
    from .routers.cases import _pay_base_total
    db = SessionLocal()
    try:
        rows = (db.query(_m.Case)
                .filter(_m.Case.removed.isnot(True),
                        or_(_m.Case.pending_amount.is_(None), _m.Case.pending_amount == 0))
                .all())
        changed = 0
        for c in rows:
            pend = _pay_base_total(c) - Decimal(c.received_amount or 0)
            if pend > 0:
                c.pending_amount = pend
                changed += 1
        if changed:
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


def _fix_dup_tl_codes():
    """Repair dual-role team-lead IDs: earlier every 'also a team lead' grant reused the same
    tl_emp_code. Give every dual-role user a UNIQUE tl_emp_code (keeping any already-unique one)."""
    from .database import SessionLocal
    from . import models as _m
    from .routers.users import generate_emp_code
    db = SessionLocal()
    try:
        used = set()
        for u in db.query(_m.User).filter(_m.User.role == "teamlead").all():
            if u.emp_code:
                used.add(u.emp_code.strip().upper())
        duals = (db.query(_m.User)
                 .filter(_m.User.also_team_lead.is_(True))
                 .order_by(_m.User.id).all())
        changed = False
        for u in duals:
            code = (u.tl_emp_code or "").strip().upper()
            if not code or code in used:              # missing or duplicate → reassign
                fresh = generate_emp_code(db, "teamlead")
                u.tl_emp_code = fresh
                used.add(fresh.strip().upper())
                db.flush()                            # so the next generate sees it
                changed = True
            else:
                used.add(code)
        if changed:
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def _clear_random_allocations():
    """One-time cleanup of the old pincode/GPS auto-allocator's work: strip any FOS/caller
    assignment that ISN'T backed by the upload sheet. When a case is allocated from its Excel ID,
    the importer overwrites fos_name/caller_name with the matched user's real name — so an
    assignment whose stored name doesn't match the assigned user (or where the sheet name is blank)
    was a 'random' allocation. Those are cleared so the case is unallocated, per the ID-only policy."""
    import os
    from .database import SessionLocal
    from . import models as _m
    # Run ONCE (not every restart) so we never undo an admin's later manual reassignments.
    marker = os.path.join(os.path.dirname(__file__), "..", ".alloc_cleaned_v1")
    if os.path.exists(marker):
        return
    db = SessionLocal()
    try:
        users = {u.id: ((u.name or "").strip().upper(), (u.emp_code or "").strip().upper())
                 for u in db.query(_m.User.id, _m.User.name, _m.User.emp_code).all()}
        changed = 0
        for c in db.query(_m.Case).filter(_m.Case.removed.isnot(True)).all():
            for id_attr, name_attr in (("assigned_fos_id", "fos_name"),
                                       ("assigned_caller_id", "caller_name")):
                uid = getattr(c, id_attr)
                if not uid:
                    continue
                uname, ucode = users.get(uid, ("", ""))
                sheet = (getattr(c, name_attr) or "").strip().upper()
                # Keep only if the sheet clearly names this person (ID-matched rows store the
                # user's real name); otherwise it was auto/randomly allocated → clear it.
                ok = bool(sheet) and (
                    (uname and (uname in sheet or sheet in uname))
                    or (ucode and ucode in sheet))
                if not ok:
                    setattr(c, id_attr, None)
                    changed += 1
        if changed:
            db.commit()
        try:                                   # mark done so it runs only once
            with open(marker, "w") as _f:
                _f.write("done")
        except Exception:
            pass
    except Exception:
        db.rollback()
    finally:
        db.close()


_backfill_emp_codes()
_backfill_norm_stab()
_fix_negative_pending()
_backfill_pending()
_backfill_dual_role_flag()
_reset_rtp_promises()
_fix_dup_tl_codes()
_clear_random_allocations()


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


def _ensure_techsupport():
    """Create the hidden tech-support account once, if it doesn't exist. It never appears in
    Manpower/team lists but can open every screen to diagnose issues and handle Help tickets."""
    from .database import SessionLocal
    from .security import hash_password
    from . import models as _m
    email = "techsupportashu@gmail.com"
    db = SessionLocal()
    try:
        if db.query(_m.User).filter(_m.User.email == email).first():
            return
        db.add(_m.User(
            name="Tech Support", email=email, role="techsupport",
            emp_code="TS001", is_active=True, must_change_password=True,
            profile_completed=True, hashed_password=hash_password("SsdSupport@2026"),
        ))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


_maybe_seed()
_ensure_techsupport()

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
          reminders, audit_log, archive, catalog, manpower, notifications, dpr, support):
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
    from . import models as _m
    branches = sorted(
        {(b or "").strip() for (b,) in db.query(_m.User.branch).distinct().all() if b and str(b).strip()}
        | {(b or "").strip() for (b,) in db.query(_m.Case.branch).distinct().all() if b and str(b).strip()}
    )
    return {
        "bank_products": catalog(db),
        "branches": branches,
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
        "call_scheme": settings.call_scheme,
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
