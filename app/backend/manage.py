"""RecoverIQ — command-line user & database management.

Run from the backend folder with your environment active. It uses the same
DATABASE_URL as the app, so it works against the local SQLite file OR your
production Cloud SQL (Postgres) — just point DATABASE_URL at the right one.

Examples
--------
  # create the first administrator
  python manage.py create-user --name "Asha Rao" --email asha@yourco.com \
      --role admin --password "StrongPass!23"

  # create a field agent with branch, banks and pincodes
  python manage.py create-user --name "Ravi K" --email ravi@yourco.com \
      --role fos --password "Field!234" --branch Visakhapatnam \
      --banks ICICI,RBL --pincodes 530001,530016

  python manage.py list-users
  python manage.py reset-password --email ravi@yourco.com --password "New!2345"
  python manage.py set-role --email ravi@yourco.com --role manager
  python manage.py deactivate --email old@yourco.com
  python manage.py activate   --email old@yourco.com
  python manage.py stats
"""
import argparse
import sys

from app.database import Base, engine, SessionLocal
from app import models
from app.security import hash_password

# internal role keys -> friendly labels shown in the app
ROLES = {
    "admin": "Administrator",
    "manager": "Collections Manager",
    "fos": "Field Agent",
    "telecaller": "Tele-calling Agent",
}
# convenient aliases so you can type the friendly word too
ALIASES = {
    "administrator": "admin", "collections-manager": "manager", "branch-manager": "manager",
    "manager": "manager", "field-agent": "fos", "field-officer": "fos", "fos": "fos",
    "tele-calling-agent": "telecaller", "telecaller": "telecaller", "caller": "telecaller",
    "admin": "admin",
}


def _norm_role(r: str) -> str:
    key = ALIASES.get((r or "").strip().lower())
    if not key:
        sys.exit(f"Invalid role '{r}'. Use one of: {', '.join(ROLES)}")
    return key


def _csv(v):
    return [x.strip() for x in v.split(",") if x.strip()] if v else []


def cmd_create(a):
    db = SessionLocal()
    try:
        email = a.email.strip().lower()
        if db.query(models.User).filter(models.User.email == email).first():
            sys.exit(f"A user with email {email} already exists.")
        role = _norm_role(a.role)
        if len(a.password) < 6:
            sys.exit("Password must be at least 6 characters.")
        u = models.User(
            name=a.name, email=email, role=role,
            hashed_password=hash_password(a.password),
            phone=a.phone, branch=a.branch,
            banks=_csv(a.banks), assigned_pincodes=_csv(a.pincodes),
            home_lat=a.lat, home_lng=a.lng,
            employment_type=a.employment_type, is_active=True,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        print(f"Created {ROLES[role]}: {u.name} <{u.email}>  (id={u.id})")
        print("They can now sign in with that email + password.")
    finally:
        db.close()


def cmd_list(a):
    db = SessionLocal()
    try:
        rows = db.query(models.User).order_by(models.User.role, models.User.name).all()
        if not rows:
            print("No users yet. Create an admin first (create-user --role admin).")
            return
        print(f"{'id':>3}  {'role':<20} {'name':<24} {'email':<30} {'branch':<16} active")
        print("-" * 104)
        for u in rows:
            print(f"{u.id:>3}  {ROLES.get(u.role, u.role):<20} {(u.name or ''):<24} "
                  f"{(u.email or ''):<30} {(u.branch or '-'):<16} {'yes' if u.is_active else 'NO'}")
        print(f"\n{len(rows)} user(s).")
    finally:
        db.close()


def _get(db, email):
    u = db.query(models.User).filter(models.User.email == email.strip().lower()).first()
    if not u:
        sys.exit(f"No user with email {email}")
    return u


def cmd_reset(a):
    db = SessionLocal()
    try:
        if len(a.password) < 6:
            sys.exit("Password must be at least 6 characters.")
        u = _get(db, a.email)
        u.hashed_password = hash_password(a.password)
        u.failed_login_count = 0          # a reset also clears any active lockout
        u.lockout_until = None
        db.commit()
        print(f"Password reset for {u.email} (lockout cleared).")
    finally:
        db.close()


def cmd_unlock(a):
    """Clear a 'too many failed attempts' lock so the user can sign in right away."""
    db = SessionLocal()
    try:
        u = _get(db, a.email)
        u.failed_login_count = 0
        u.lockout_until = None
        db.commit()
        print(f"Unlocked {u.email}. They can log in immediately.")
    finally:
        db.close()


def cmd_role(a):
    db = SessionLocal()
    try:
        u = _get(db, a.email)
        u.role = _norm_role(a.role)
        db.commit()
        print(f"{u.email} is now {ROLES[u.role]}.")
    finally:
        db.close()


def cmd_active(a, active):
    db = SessionLocal()
    try:
        u = _get(db, a.email)
        u.is_active = active
        db.commit()
        print(f"{u.email} is now {'ACTIVE' if active else 'DISABLED'}.")
    finally:
        db.close()


def cmd_stats(a):
    db = SessionLocal()
    try:
        print("Users by role:")
        for r, label in ROLES.items():
            print(f"  {label:<22} {db.query(models.User).filter(models.User.role == r).count()}")
        print(f"Cases:        {db.query(models.Case).count()}")
        print(f"Visits:       {db.query(models.Visit).count()}")
        print(f"Call logs:    {db.query(models.CallLog).count()}")
        print(f"Legal matters:{db.query(models.LegalCase).count()}")
        print(f"Devices:      {db.query(models.Device).count()}")
    finally:
        db.close()


def main():
    Base.metadata.create_all(bind=engine)  # ensure tables exist
    p = argparse.ArgumentParser(description="RecoverIQ user & DB management")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("create-user", help="create a login")
    c.add_argument("--name", required=True)
    c.add_argument("--email", required=True)
    c.add_argument("--role", required=True, help="admin | manager | fos | telecaller")
    c.add_argument("--password", required=True)
    c.add_argument("--branch", default=None)
    c.add_argument("--phone", default=None)
    c.add_argument("--banks", default=None, help="comma list e.g. ICICI,RBL,AXIS")
    c.add_argument("--pincodes", default=None, help="comma list e.g. 530001,530016")
    c.add_argument("--lat", type=float, default=None, help="field agent base latitude")
    c.add_argument("--lng", type=float, default=None, help="field agent base longitude")
    c.add_argument("--employment-type", dest="employment_type", default=None)
    c.set_defaults(func=cmd_create)

    sub.add_parser("list-users", help="list all logins").set_defaults(func=cmd_list)

    r = sub.add_parser("reset-password", help="set a new password (also clears lockout)")
    r.add_argument("--email", required=True); r.add_argument("--password", required=True)
    r.set_defaults(func=cmd_reset)

    ul = sub.add_parser("unlock", help="clear a 'too many failed attempts' lock")
    ul.add_argument("--email", required=True); ul.set_defaults(func=cmd_unlock)

    s = sub.add_parser("set-role", help="change a user's role")
    s.add_argument("--email", required=True); s.add_argument("--role", required=True)
    s.set_defaults(func=cmd_role)

    d = sub.add_parser("deactivate", help="block a user from signing in")
    d.add_argument("--email", required=True); d.set_defaults(func=lambda a: cmd_active(a, False))

    e = sub.add_parser("activate", help="re-enable a user")
    e.add_argument("--email", required=True); e.set_defaults(func=lambda a: cmd_active(a, True))

    sub.add_parser("stats", help="row counts").set_defaults(func=cmd_stats)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
