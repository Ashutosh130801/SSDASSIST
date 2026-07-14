import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from sqlalchemy import inspect, text

from .database import Base, engine
from .config import get_settings
from . import models  # noqa: F401  (register models)
from .routers import (auth, users, cases, imports, visits, calls, tracking, analytics, ai,
                      devices, leaves, templates, legal, twofa, webauthn_auth)

settings = get_settings()

Base.metadata.create_all(bind=engine)


def _ensure_columns():
    """Lightweight auto-migration: add columns introduced after a DB was first
    created, so existing SQLite/Postgres databases keep working without a reset."""
    wanted = {
        "cases": {
            "last_contacted_at": "TIMESTAMP",
            "follow_up_date": "DATE",
        },
        "users": {
            "employment_type": "VARCHAR(30)",
            "joining_date": "DATE",
            "address": "TEXT",
            "emergency_contact": "VARCHAR(60)",
            "photo_url": "VARCHAR(255)",
            "failed_login_count": "INTEGER",
            "lockout_until": "TIMESTAMP",
            "totp_secret": "VARCHAR(64)",
            "twofa_enabled": "BOOLEAN",
            "webauthn_challenge": "VARCHAR(255)",
        },
        "visits": {
            "distance_from_case_m": "FLOAT",
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
          leaves, templates, legal, twofa, webauthn_auth):
    app.include_router(r.router)


@app.get("/api/config")
def config():
    return {
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
