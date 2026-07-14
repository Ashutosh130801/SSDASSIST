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


def create_access_token(subject: str, role: str, name: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(subject), "role": role, "name": name, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
