from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import hash_password
from ..deps import get_current_user, require_roles

router = APIRouter(prefix="/api/users", tags=["users"])

_HRMS_FIELDS = ("employment_type", "joining_date", "address", "emergency_contact", "photo_url")
_ROLE_PREFIX = {"telecaller": "TC", "fos": "FO", "manager": "MG", "backend": "BO",
                "admin": "AD", "headoffice": "HO", "teamlead": "TL",
                "hr": "HR", "it": "IT", "staff": "ST", "techsupport": "TS"}


def _team_lead_name(db: Session, tl_id):
    if not tl_id:
        return None
    tl = db.query(models.User.name).filter(models.User.id == tl_id).first()
    return tl[0] if tl else None


def generate_emp_code(db: Session, role: str) -> str:
    """A short, unique staff/caller ID (e.g. TC001) — printed in upload sheets so a case's
    CALLER column maps back to the exact caller."""
    prefix = _ROLE_PREFIX.get(role, "EMP")
    existing = [u.emp_code for u in db.query(models.User.emp_code)
                .filter(models.User.emp_code.like(prefix + "%")).all() if u.emp_code]
    # Dual-role team leads store their TL id in tl_emp_code — count those too so each new
    # grant gets a UNIQUE TL code (otherwise every dual-role user would get the same one).
    existing += [u.tl_emp_code for u in db.query(models.User.tl_emp_code)
                 .filter(models.User.tl_emp_code.like(prefix + "%")).all() if u.tl_emp_code]
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
    q = db.query(models.User).filter(models.User.role != "techsupport")   # hidden diagnostic role
    if role:
        q = q.filter(models.User.role == role)
    if user.role == "admin":
        pass                                   # sees everyone
    elif user.role == "manager":
        q = q.filter(models.User.branch == user.branch)   # only their branch
    elif user.role == "teamlead":
        # a team lead sees only their own members (+ themselves)
        q = q.filter((models.User.team_lead_id == user.id) | (models.User.id == user.id))
    else:
        q = q.filter(models.User.role != "admin")          # staff roster only
    rows = q.order_by(models.User.name).all()
    # resolve team-lead display name for the roster
    lead_ids = {u.team_lead_id for u in rows if u.team_lead_id}
    names = {}
    if lead_ids:
        names = {i: n for (i, n) in db.query(models.User.id, models.User.name)
                 .filter(models.User.id.in_(lead_ids)).all()}
    for u in rows:
        u.team_lead_name = names.get(u.team_lead_id)
    return rows


def _guard_manager(actor: models.User, body_role: str | None, body_branch: str | None):
    """Managers may manage staff — including fellow branch managers — inside their own
    branch, but never admins. Team leads may only manage FOS/callers on their own team."""
    if actor.role == "manager":
        if body_role in ("admin", "headoffice"):
            raise HTTPException(status_code=403, detail="Managers cannot create or manage admins or head-office staff")
        if body_branch and body_branch != actor.branch:
            raise HTTPException(status_code=403, detail="Managers can only manage staff in their own branch")
    if actor.role == "teamlead":
        if body_role not in (None, "fos", "telecaller"):
            raise HTTPException(status_code=403, detail="Team leads can only add field officers or callers")


@router.post("", response_model=schemas.UserOut)
def create_user(body: schemas.UserCreate, db: Session = Depends(get_db),
                actor: models.User = Depends(require_roles("admin", "manager", "teamlead"))):
    if db.query(models.User).filter(models.User.email == body.email.lower()).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    _guard_manager(actor, body.role, body.branch)
    if actor.role == "teamlead":
        branch = actor.branch
        team_lead_id = actor.id                 # members created by a TL report to that TL
    else:
        branch = actor.branch if actor.role == "manager" else body.branch
        team_lead_id = body.team_lead_id
    u = models.User(
        name=body.name, email=body.email.lower(), phone=body.phone, role=body.role,
        branch=branch, team_lead_id=team_lead_id,
        banks=body.banks, assigned_products=body.assigned_products,
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
    u.team_lead_name = _team_lead_name(db, u.team_lead_id)
    return u


@router.patch("/{user_id}", response_model=schemas.UserOut)
def update_user(user_id: int, body: schemas.UserUpdate, db: Session = Depends(get_db),
                actor: models.User = Depends(require_roles("admin", "manager", "teamlead"))):
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    if actor.role == "manager" and u.branch != actor.branch:
        raise HTTPException(status_code=403, detail="Not in your branch")
    if actor.role == "teamlead" and u.team_lead_id != actor.id:
        raise HTTPException(status_code=403, detail="Not one of your team members")
    _guard_manager(actor, body.role, body.branch)
    data = body.model_dump(exclude_unset=True)
    if data.get("password"):
        u.hashed_password = hash_password(data.pop("password"))
    else:
        data.pop("password", None)
    if actor.role == "manager":
        data.pop("branch", None)               # managers can't move staff to another branch
    if actor.role == "teamlead":
        data.pop("branch", None)
        data.pop("role", None)                 # team leads can't change a member's role
        data.pop("team_lead_id", None)         # …or hand them to another team lead
    for k, v in data.items():
        setattr(u, k, v)
    db.commit()
    db.refresh(u)
    u.team_lead_name = _team_lead_name(db, u.team_lead_id)
    return u


@router.delete("/{user_id}")
def deactivate_user(user_id: int, db: Session = Depends(get_db),
                    actor: models.User = Depends(require_roles("admin", "manager", "teamlead"))):
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    if actor.role == "manager" and (u.branch != actor.branch or u.role in ("admin", "manager")):
        raise HTTPException(status_code=403, detail="Not allowed")
    if actor.role == "teamlead" and u.team_lead_id != actor.id:
        raise HTTPException(status_code=403, detail="Not one of your team members")
    u.is_active = False
    db.commit()
    return {"ok": True}
