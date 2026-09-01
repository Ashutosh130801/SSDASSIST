"""One-shot: activate (allow login for) support/office staff whose accounts are currently
disabled — e.g. IT and generic "staff" roles that have no collections work but still need to
log in for attendance, leave and their E-ID.

Login is only blocked by is_active=False (there is no role gate), so this simply flips those
accounts on and clears any brute-force lockout. Nothing else changes.

Run from app/backend with the same DATABASE_URL the app uses (dev: sqlite via run_local.bat;
prod: Postgres):

    python activate_staff.py                 # activates roles: it, staff
    python activate_staff.py it staff hr     # pass a custom role list

They can then log in on web or the native app and check in. Assign a password first if they
don't have one (use manage.py or the Manpower screen).
"""
import sys

from app.database import SessionLocal
from app import models

DEFAULT_ROLES = ("it", "staff")


def main(roles) -> None:
    db = SessionLocal()
    try:
        q = db.query(models.User).filter(models.User.role.in_(roles))
        users = q.all()
        changed = 0
        for u in users:
            if not u.is_active or (getattr(u, "failed_login_count", 0) or 0) or getattr(u, "lockout_until", None):
                u.is_active = True
                u.blocked_reason = None
                if hasattr(u, "failed_login_count"):
                    u.failed_login_count = 0
                if hasattr(u, "lockout_until"):
                    u.lockout_until = None
                changed += 1
        db.commit()
        print(f"Roles {roles}: {len(users)} accounts found, {changed} activated / unlocked.")
        for u in users:
            pw = "has-password" if u.hashed_password else "NO PASSWORD (set one before they can log in)"
            print(f"  - {u.emp_code or '—':8} {u.name:28} {u.email:32} active={u.is_active}  {pw}")
    finally:
        db.close()


if __name__ == "__main__":
    roles = tuple(a.strip() for a in sys.argv[1:] if a.strip()) or DEFAULT_ROLES
    main(roles)
