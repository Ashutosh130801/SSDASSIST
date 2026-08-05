from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from .database import get_db
from .security import decode_token
from . import models

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.User:
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise cred_exc
    except JWTError:
        raise cred_exc

    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    if not user or not user.is_active:
        raise cred_exc

    # Dual-role support: a caller/FOS who is also a team lead picks a "view" at login. The
    # chosen view rides in the token's `av` claim. For this request we make the effective
    # role that active view, so every role check + data scope behaves as that single hat.
    primary = user.role
    allowed = allowed_views(user)
    av = payload.get("av") or primary
    if av in allowed:
        user.role = av
    user._primary_role = primary        # noqa: SLF001 (transient, per-request only)
    user._active_view = user.role       # noqa: SLF001
    user.available_views = allowed
    user.active_view = user.role
    return user


def allowed_views(user: "models.User") -> list[str]:
    """The hats a user may switch between. Primary role always; plus 'teamlead' when the
    account was granted the extra team-lead hat (and isn't already a team lead)."""
    primary = getattr(user, "_primary_role", None) or user.role
    views = [primary]
    if getattr(user, "also_team_lead", False) and primary != "teamlead":
        views.append("teamlead")
    return views


def require_roles(*roles: str):
    def checker(user: models.User = Depends(get_current_user)) -> models.User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {', '.join(roles)}",
            )
        return user
    return checker
