from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext

from .config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    # bcrypt max 72 bytes
    return pwd_context.hash(password[:72])


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    return pwd_context.verify(plain[:72], hashed)


# Field officers are auto-logged-out at 7pm IST each day — their token expires then.
IST = timezone(timedelta(hours=5, minutes=30))
FOS_LOGOUT_HOUR = 19  # 7pm IST


def _fos_expiry() -> datetime:
    """Next 7pm IST from now (today if still before 7pm, else tomorrow)."""
    now_ist = datetime.now(IST)
    cutoff = now_ist.replace(hour=FOS_LOGOUT_HOUR, minute=0, second=0, microsecond=0)
    if now_ist >= cutoff:
        cutoff = cutoff + timedelta(days=1)
    return cutoff.astimezone(timezone.utc)


def create_access_token(subject: str, role: str, name: str) -> str:
    if role == "fos":
        expire = _fos_expiry()
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(subject), "role": role, "name": name, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
