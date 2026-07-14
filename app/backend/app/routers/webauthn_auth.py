"""WebAuthn / passkeys — biometric login (Face ID, fingerprint, Windows Hello, security keys).

The heavy lifting is done by the optional `webauthn` (py_webauthn) package. If it isn't
installed the endpoints return 501 and the rest of the app (password + TOTP login) is
unaffected. Passkeys are additive — they never replace or weaken password auth.

NOTE: WebAuthn only works over HTTPS (or http://localhost). Set WEBAUTHN_RP_ID and
WEBAUTHN_ORIGIN in production; otherwise they're derived from the request's Origin header.
"""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user
from ..config import get_settings
from ..security import create_access_token

router = APIRouter(prefix="/api/auth/webauthn", tags=["webauthn"])
settings = get_settings()


def _wa():
    try:
        import webauthn  # noqa
        from webauthn.helpers import base64url_to_bytes, bytes_to_base64url  # noqa
        return webauthn
    except Exception:
        raise HTTPException(status_code=501,
                            detail="Passkeys not available on the server (webauthn package not installed).")


def _rp(request: Request):
    """Return (rp_id, origin). Prefer explicit config; else derive from the Origin header."""
    origin = settings.webauthn_origin or request.headers.get("origin") or ""
    rp_id = settings.webauthn_rp_id
    if not rp_id and origin:
        # strip scheme + port -> bare host
        host = origin.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
        rp_id = host
    if not rp_id:
        raise HTTPException(status_code=400, detail="Cannot determine WebAuthn RP ID; set WEBAUTHN_RP_ID.")
    return rp_id, origin


class EmailBody(BaseModel):
    email: str


class AssertBody(BaseModel):
    email: str
    credential: dict


class RegBody(BaseModel):
    credential: dict
    label: str | None = None


# ---------------- registration (must be logged in) ----------------
@router.post("/register/options")
def register_options(request: Request, db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)):
    wa = _wa()
    from webauthn.helpers import bytes_to_base64url, base64url_to_bytes
    from webauthn.helpers.structs import PublicKeyCredentialDescriptor
    rp_id, _ = _rp(request)
    existing = db.query(models.WebAuthnCredential).filter_by(user_id=user.id).all()
    options = wa.generate_registration_options(
        rp_id=rp_id, rp_name=settings.brand_name,
        user_id=str(user.id).encode(), user_name=user.email, user_display_name=user.name or user.email,
        exclude_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id))
                             for c in existing],
    )
    user.webauthn_challenge = bytes_to_base64url(options.challenge)
    db.commit()
    return json.loads(wa.options_to_json(options))


@router.post("/register/verify")
def register_verify(body: RegBody, request: Request, db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)):
    wa = _wa()
    from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
    rp_id, origin = _rp(request)
    if not user.webauthn_challenge:
        raise HTTPException(status_code=400, detail="No registration in progress.")
    verification = wa.verify_registration_response(
        credential=json.dumps(body.credential),
        expected_challenge=base64url_to_bytes(user.webauthn_challenge),
        expected_rp_id=rp_id, expected_origin=origin,
    )
    cred = models.WebAuthnCredential(
        user_id=user.id,
        credential_id=bytes_to_base64url(verification.credential_id),
        public_key=bytes_to_base64url(verification.credential_public_key),
        sign_count=verification.sign_count,
        label=body.label or "Passkey",
    )
    user.webauthn_challenge = None
    db.add(cred)
    db.commit()
    return {"registered": True, "label": cred.label}


@router.get("/list")
def list_passkeys(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    rows = db.query(models.WebAuthnCredential).filter_by(user_id=user.id).all()
    return [{"id": c.id, "label": c.label, "created_at": c.created_at, "last_used": c.last_used} for c in rows]


@router.delete("/{cid}")
def delete_passkey(cid: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    c = db.query(models.WebAuthnCredential).filter_by(id=cid, user_id=user.id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Passkey not found")
    db.delete(c)
    db.commit()
    return {"ok": True}


# ---------------- authentication (pre-login, by email) ----------------
@router.post("/login/options")
def login_options(body: EmailBody, request: Request, db: Session = Depends(get_db)):
    wa = _wa()
    from webauthn.helpers import bytes_to_base64url, base64url_to_bytes
    from webauthn.helpers.structs import PublicKeyCredentialDescriptor
    rp_id, _ = _rp(request)
    user = db.query(models.User).filter(models.User.email == body.email.lower()).first()
    if not user:
        raise HTTPException(status_code=404, detail="No passkeys for this account.")
    creds = db.query(models.WebAuthnCredential).filter_by(user_id=user.id).all()
    if not creds:
        raise HTTPException(status_code=404, detail="No passkeys for this account.")
    options = wa.generate_authentication_options(
        rp_id=rp_id,
        allow_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id)) for c in creds],
    )
    user.webauthn_challenge = bytes_to_base64url(options.challenge)
    db.commit()
    return json.loads(wa.options_to_json(options))


@router.post("/login/verify", response_model=schemas.Token)
def login_verify(body: AssertBody, request: Request, db: Session = Depends(get_db)):
    wa = _wa()
    from webauthn.helpers import base64url_to_bytes
    rp_id, origin = _rp(request)
    user = db.query(models.User).filter(models.User.email == body.email.lower()).first()
    if not user or not user.webauthn_challenge:
        raise HTTPException(status_code=400, detail="No sign-in in progress.")
    raw_id = body.credential.get("id") or body.credential.get("rawId")
    cred = db.query(models.WebAuthnCredential).filter_by(user_id=user.id, credential_id=raw_id).first()
    if not cred:
        raise HTTPException(status_code=400, detail="Unknown passkey.")
    verification = wa.verify_authentication_response(
        credential=json.dumps(body.credential),
        expected_challenge=base64url_to_bytes(user.webauthn_challenge),
        expected_rp_id=rp_id, expected_origin=origin,
        credential_public_key=base64url_to_bytes(cred.public_key),
        credential_current_sign_count=cred.sign_count,
    )
    cred.sign_count = verification.new_sign_count
    cred.last_used = datetime.now(timezone.utc)
    user.webauthn_challenge = None
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    db.commit()
    tok = create_access_token(subject=user.id, role=user.role, name=user.name)
    return schemas.Token(access_token=tok, user=schemas.UserOut.model_validate(user))
