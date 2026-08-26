from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..config import get_settings
from ..security import verify_password, create_access_token, hash_password
from ..deps import get_current_user, allowed_views

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()


def _token_for(user: models.User, active_role: str | None = None) -> schemas.Token:
    # `user.role` here is the account's PRIMARY role (loaded from the DB). active_role is the
    # chosen view for a dual-role user; it defaults to the primary role.
    primary = getattr(user, "_primary_role", None) or user.role
    views = allowed_views(user)
    active = active_role if (active_role in views) else primary
    tok = create_access_token(subject=user.id, role=primary, name=user.name, active_role=active)
    user.available_views = views
    user.active_view = active
    out = schemas.UserOut.model_validate(user)
    out.role = active                     # the app treats `role` as the active view
    return schemas.Token(access_token=tok, user=out)


def _aware(dt):
    return dt if (dt is None or dt.tzinfo) else dt.replace(tzinfo=timezone.utc)


def _check_lockout(user: models.User):
    """Reject login while the account is in a brute-force cool-down."""
    lu = _aware(user.lockout_until)
    if lu and lu > datetime.now(timezone.utc):
        mins = int((lu - datetime.now(timezone.utc)).total_seconds() // 60) + 1
        raise HTTPException(status_code=429,
                            detail=f"Too many failed attempts. Try again in {mins} minute(s).")


def _register_failure(db: Session, user: models.User):
    user.failed_login_count = (user.failed_login_count or 0) + 1
    if user.failed_login_count >= settings.login_max_attempts:
        user.lockout_until = datetime.now(timezone.utc) + timedelta(minutes=settings.login_lockout_minutes)
        user.failed_login_count = 0
    db.commit()


def _register_success(db: Session, user: models.User):
    if user.failed_login_count or user.lockout_until:
        user.failed_login_count = 0
        user.lockout_until = None
        db.commit()


def _check_2fa(user: models.User, otp: str | None):
    """If the account has TOTP enabled, require a valid code."""
    if not user.twofa_enabled:
        return
    import pyotp
    if not otp:
        # Special signal the frontend recognises to prompt for the 6-digit code.
        raise HTTPException(status_code=401, detail="2FA_REQUIRED")
    if not user.totp_secret or not pyotp.TOTP(user.totp_secret).verify(otp.strip(), valid_window=1):
        raise HTTPException(status_code=401, detail="Invalid 2FA code")


def _device_gate(db: Session, user: models.User, device_id: str | None, label: str | None):
    """Block logins from unapproved devices. The user's first device auto-approves
    (and admins always do, so they're never locked out); any later new device must be
    approved by an admin/manager before it can sign in."""
    if not device_id:
        return  # no device info supplied (e.g. API/test clients) — skip the gate
    dev = (db.query(models.Device)
           .filter(models.Device.user_id == user.id, models.Device.device_id == device_id).first())
    if dev:
        if not dev.approved:
            raise HTTPException(status_code=403,
                                detail="This device is awaiting admin approval. Ask your admin to approve it.")
        dev.last_seen = datetime.now(timezone.utc)
        if label and not dev.label:
            dev.label = label
        db.commit()
        return
    count = db.query(models.Device).filter(models.Device.user_id == user.id).count()
    # IT Support View is an auditor account: EVERY device (even the first) must be approved,
    # and only by an admin or tech-support — never auto-approved.
    is_readonly = user.role == "it_support_view"
    auto = (user.role == "admin") or (count == 0 and not is_readonly)
    dev = models.Device(user_id=user.id, device_id=device_id, label=label, approved=auto,
                        approved_at=datetime.now(timezone.utc) if auto else None)
    db.add(dev)
    db.flush()
    if auto:
        # Auto-approved (first device or admin) → enforce the keep-latest-2 cap.
        from .devices import prune_approved_devices
        prune_approved_devices(db, user.id)
    elif is_readonly:
        # Route this approval request to admins + tech-support via the notification bell.
        from .notifications import push
        for appr in db.query(models.User).filter(
                models.User.role.in_(("admin", "techsupport")), models.User.is_active.is_(True)).all():
            push(db, appr.id, "Device approval needed — IT Support View",
                 f"{user.name} is trying to sign in from a new device ({label or device_id}). Approve it in Devices.",
                 ntype="device_request", by_name=user.name)
    db.commit()
    if not auto:
        raise HTTPException(status_code=403,
                            detail="New device registered. An admin must approve it before you can sign in.")


@router.post("/login", response_model=schemas.Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # OAuth2 form uses 'username' — we treat it as email
    user = db.query(models.User).filter(models.User.email == form.username.lower()).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    _check_lockout(user)
    if not verify_password(form.password, user.hashed_password):
        _register_failure(db, user)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    _register_success(db, user)
    return _token_for(user)


@router.post("/login-json", response_model=schemas.Token)
def login_json(body: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == body.email.lower()).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    _check_lockout(user)                              # 429 while locked out
    if not verify_password(body.password, user.hashed_password):
        _register_failure(db, user)                   # count the miss, maybe lock
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    _check_2fa(user, body.otp)                         # 401 "2FA_REQUIRED" / "Invalid 2FA code"
    _register_success(db, user)                        # reset counters
    _device_gate(db, user, body.device_id, body.device_label)
    return _token_for(user)


@router.post("/change-password", response_model=schemas.Token)
def change_password(body: dict = Body(...), db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)):
    """Set a new password. Verifies the current one, then clears the first-login flag.
    Returns a fresh token + updated user so the app can continue seamlessly."""
    current = (body.get("current_password") or "").strip()
    new = (body.get("new_password") or "").strip()
    if not user.hashed_password or not verify_password(current, user.hashed_password):
        raise HTTPException(status_code=400, detail="Your current password is incorrect")
    if len(new) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")
    if new == current:
        raise HTTPException(status_code=400, detail="New password must be different from the current one")
    user.hashed_password = hash_password(new)
    user.must_change_password = False
    db.commit()
    db.refresh(user)
    return _token_for(user)


@router.post("/google", response_model=schemas.Token)
def google_login(body: schemas.GoogleLogin, db: Session = Depends(get_db)):
    if not settings.google_client_id:
        raise HTTPException(status_code=400, detail="Google sign-in not configured (set GOOGLE_CLIENT_ID)")
    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests
        info = google_id_token.verify_oauth2_token(
            body.id_token, google_requests.Request(), settings.google_client_id
        )
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Google token")

    email = (info.get("email") or "").lower()
    sub = info.get("sub")
    user = db.query(models.User).filter(
        (models.User.google_sub == sub) | (models.User.email == email)
    ).first()
    if not user:
        # Only pre-registered staff may sign in — no self-serve account creation.
        raise HTTPException(status_code=403, detail="No account for this Google email. Ask an admin to add you.")
    if not user.google_sub:
        user.google_sub = sub
        db.commit()
    return _token_for(user)


@router.get("/me", response_model=schemas.UserOut)
def me(user: models.User = Depends(get_current_user)):
    return user


@router.post("/switch-view", response_model=schemas.Token)
def switch_view(body: dict = Body(...), db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)):
    """Dual-role users flip between their hats (e.g. caller ↔ team lead). Re-issues a token
    whose active view is the requested one — one hat at a time. `user.role` here is already the
    effective (active) role from the current token, but the picker validates against the full
    set of allowed views so any hat can be selected."""
    want = (body.get("view") or "").strip()
    views = getattr(user, "available_views", None) or [getattr(user, "_primary_role", user.role)]
    if want not in views:
        raise HTTPException(status_code=400, detail=f"Not an available view. Choose one of: {', '.join(views)}")
    return _token_for(user, active_role=want)
