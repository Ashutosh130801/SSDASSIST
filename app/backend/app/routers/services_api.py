"""⚙️ Services (top-right): list every service, admin switches them on/off and sets their options."""
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import audit, models
from .. import services as svc
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/api/services", tags=["services"])


@router.get("")
def list_services(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Every user gets the on/off map (menus hide what's off). Admin also gets settings + schemas."""
    state = svc.load(db, fresh=True)
    admin = user.role == "admin"
    out = []
    for s in svc.SERVICES:
        row = {"key": s["key"], "name": s["name"], "group": s["group"], "icon": s.get("icon"), "desc": s["desc"],
               "nav": s.get("nav") or [], "required": bool(s.get("required")), "reminder": bool(s.get("reminder")),
               "enabled": state[s["key"]]["enabled"]}
        if admin:
            row["settings"] = state[s["key"]]["settings"]
            row["schema"] = s.get("settings") or []
            if any(f["type"] == "secret" for f in row["schema"]):
                row["secrets"] = svc.secret_status(db, s["key"])
        out.append(row)
    return out


@router.put("/{key}")
def update_service(key: str, body: dict = Body(...), db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Only Admin can change services.")
    s = svc.BY_KEY.get(key)
    if not s:
        raise HTTPException(404, "Unknown service")
    if s.get("reminder"):
        raise HTTPException(400, f"{s['name']} is planned — not available yet.")
    if s.get("required") and body.get("enabled") is False:
        raise HTTPException(400, f"{s['name']} is a core service and can't be turned off.")
    before = svc.load(db, fresh=True)[key]
    try:
        svc.save(db, key, body.get("enabled"), body.get("settings"), body.get("secrets"), body.get("clear_secrets"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    after = svc.load(db, fresh=True)[key]
    keys_changed = [k for k, v in (body.get("secrets") or {}).items() if str(v or "").strip()] + list(body.get("clear_secrets") or [])
    audit.record(db, user, "service.update", entity_type="settings",
                 detail=f"{s['name']}: " + ("ON" if after["enabled"] else "OFF") +
                        ("" if before["settings"] == after["settings"] else " · settings changed") +
                        (f" · API keys changed: {', '.join(keys_changed)}" if keys_changed else ""),
                 old=before, new=after)
    db.commit()
    return {"key": key, **after}
