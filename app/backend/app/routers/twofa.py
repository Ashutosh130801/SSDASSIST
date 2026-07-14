"""Two-factor authentication (TOTP authenticator app: Google Authenticator, Authy, etc.)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..deps import get_current_user
from ..config import get_settings

router = APIRouter(prefix="/api/auth/2fa", tags=["2fa"])
settings = get_settings()


class OtpBody(BaseModel):
    otp: str


@router.get("/status")
def status(user: models.User = Depends(get_current_user)):
    return {"enabled": bool(user.twofa_enabled)}


@router.post("/setup")
def setup(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Generate a fresh secret and the otpauth:// URL to show as a QR. Not active until
    the user confirms a code via /enable."""
    import pyotp
    secret = pyotp.random_base32()
    user.totp_secret = secret
    user.twofa_enabled = False
    db.commit()
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=settings.brand_name)
    return {"secret": secret, "otpauth_url": uri}


@router.post("/enable")
def enable(body: OtpBody, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    import pyotp
    if not user.totp_secret:
        raise HTTPException(status_code=400, detail="Run setup first.")
    if not pyotp.TOTP(user.totp_secret).verify(body.otp.strip(), valid_window=1):
        raise HTTPException(status_code=400, detail="Incorrect code — try again.")
    user.twofa_enabled = True
    db.commit()
    return {"enabled": True}


@router.post("/disable")
def disable(body: OtpBody, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    import pyotp
    if user.twofa_enabled and user.totp_secret and \
            not pyotp.TOTP(user.totp_secret).verify(body.otp.strip(), valid_window=1):
        raise HTTPException(status_code=400, detail="Incorrect code.")
    user.twofa_enabled = False
    user.totp_secret = None
    db.commit()
    return {"enabled": False}
