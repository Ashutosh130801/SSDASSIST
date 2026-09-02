from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value

from .database import get_db
from .security import decode_token
from . import models

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# A read-only auditor role: sees & downloads everything, but may not change anything.
READONLY_ROLES = ("it_support_view",)
_SAFE_METHODS = ("GET", "HEAD", "OPTIONS")
# Self-account endpoints a read-only user is still allowed to POST to (so they can set their own
# password / 2FA / passkey and sign in, and mark their own attendance). None of these touch shared
# collections data — attendance check-in/out/heartbeat only records the user's own presence.
_READONLY_WRITE_ALLOW = ("/api/auth/", "/api/webauthn", "/api/attendance/")


def get_current_user(request: Request, token: str = Depends(oauth2_scheme),
                     db: Session = Depends(get_db)) -> models.User:
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
    if av in allowed and av != primary:
        # Override the effective role for THIS request only. Use set_committed_value so SQLAlchemy
        # treats it as the already-persisted value — it is never marked dirty, so a later db.commit()
        # in the same request can't flush the active view over the user's real (primary) role.
        set_committed_value(user, "role", av)
    user._primary_role = primary        # noqa: SLF001 (transient, per-request only)
    user._active_view = user.role       # noqa: SLF001
    user.available_views = allowed
    user.active_view = user.role

    # Read-only roles: block every state-changing request (anything but GET/HEAD/OPTIONS),
    # except the self-security endpoints they need to sign in and secure their own account.
    if primary in READONLY_ROLES and request.method not in _SAFE_METHODS:
        path = request.url.path
        if not any(path.startswith(p) for p in _READONLY_WRITE_ALLOW):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="IT Support View is read-only — you can view and download, but not make changes.")
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
        # 'techsupport' is a hidden diagnostic super-role — it may open every screen/endpoint so
        # support can reproduce and understand any user's problem. It is never listed in Manpower.
        # 'techsupport' (full super-role) and 'it_support_view' (read-only auditor) may reach
        # every endpoint. Writes for the read-only role are already blocked in get_current_user,
        # so this only opens up the GET/read side for them.
        if user.role in ("techsupport",) + READONLY_ROLES:
            return user
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {', '.join(roles)}",
            )
        return user
    return checker
