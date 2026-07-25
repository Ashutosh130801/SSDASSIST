from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import hash_password
from ..deps import get_current_user, require_roles

router = APIRouter(prefix="/api/users", tags=["users"])

_HRMS_FIELDS = ("employment_type", "joining_date", "address", "emergency_contact", "photo_url")
_ROLE_PREFIX = {"telecaller": "TC", "fos": "FO", "manager": "MG", "backend": "BO",
                "admin": "AD", "headoffice": "HO"}


def generate_emp_code(db: Session, role: str) -> str:
    """A short, unique staff/caller ID (e.g. TC001) — printed in upload sheets so a case's
    CALLER column maps back to the exact caller."""
    prefix = _ROLE_PREFIX.get(role, "EMP")
    existing = [u.emp_code for u in db.query(models.User.emp_code)
                .filter(models.User.emp_code.like(prefix + "%")).all() if u.emp_code]
    n = 0
    for code in existing:
        try:
            n = max(n, int(code[len(prefix):]))
        except (ValueError, TypeError):
            continue
    return f"{prefix}{n + 1:03d}"


@router.get("", response_model=list[schemas.UserOut])
def list_users(role: str | None = None, db: Session = Depends(get_db),
               user: models.User = Depends(get_current_user)):
    q = db.query(models.User)
    if role:
        q = q.filter(models.User.role == role)
    if user.role == "admin":
        pass                                   # sees everyone
    elif user.role == "manager":
        q = q.filter(models.User.branch == user.branch)   # only their branch
    else:
        q = q.filter(models.User.role != "admin")          # staff roster only
    return q.order_by(models.User.name).all()


def _guard_manager(actor: models.User, body_role: str | None, body_branch: str | None):
    """Managers may manage staff — including fellow branch managers — inside their own
    branch, but never admins."""
    if actor.role == "manager":
        if body_role in ("admin", "headoffice"):
            raise HTTPException(status_code=403, detail="Managers cannot create or manage admins or head-office staff")
        if body_branch and body_branch != actor.branch:
            raise HTTPException(status_code=403, detail="Managers can only manage staff in their own branch")


@router.post("", response_model=schemas.UserOut)
def create_user(body: schemas.UserCreate, db: Session = Depends(get_db),
                actor: models.User = Depends(require_roles("admin", "manager"))):
    if db.query(models.User).filter(models.User.email == body.email.lower()).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    _guard_manager(actor, body.role, body.branch)
    branch = actor.branch if actor.role == "manager" else body.branch
    u = models.User(
        name=body.name, email=body.email.lower(), phone=body.phone, role=body.role,
        branch=branch, banks=body.banks, assigned_products=body.assigned_products,
        assigned_pincodes=body.assigned_pincodes,
        home_lat=body.home_lat, home_lng=body.home_lng,
        employment_type=body.employment_type, joining_date=body.joining_date,
        address=body.address, emergency_contact=body.emergency_contact, photo_url=body.photo_url,
        emp_code=generate_emp_code(db, body.role),
        hashed_password=hash_password(body.password),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@router.patch("/{user_id}", response_model=schemas.UserOut)
def update_user(user_id: int, body: schemas.UserUpdate, db: Session = Depends(get_db),
                actor: models.User = Depends(require_roles("admin", "manager"))):
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    if actor.role == "manager" and u.branch != actor.branch:
        raise HTTPException(status_code=403, detail="Not in your branch")
    _guard_manager(actor, body.role, body.branch)
    data = body.model_dump(exclude_unset=True)
    if data.get("password"):
        u.hashed_password = hash_password(data.pop("password"))
    else:
        data.pop("password", None)
    if actor.role == "manager":
        data.pop("branch", None)               # managers can't move staff to another branch
    for k, v in data.items():
        setattr(u, k, v)
    db.commit()
    db.refresh(u)
    return u


@router.delete("/{user_id}")
def deactivate_user(user_id: int, db: Session = Depends(get_db),
                    actor: models.User = Depends(require_roles("admin", "manager"))):
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    if actor.role == "manager" and (u.branch != actor.branch or u.role in ("admin", "manager")):
        raise HTTPException(status_code=403, detail="Not allowed")
    u.is_active = False
    db.commit()
    return {"ok": True}
