"""One-shot: guarantee the hidden tech-support login exists with a known password.

Run from the backend folder with the same environment/DATABASE_URL the app uses:

    cd app\backend
    .venv\Scripts\activate           (Windows)   OR   source .venv/bin/activate
    python fix_techsupport.py

It upserts techsupportashu@gmail.com (role techsupport), sets the password below,
clears any failed-login lockout, marks it active, and does NOT force a password change.
"""
from app.database import SessionLocal
from app import models
from app.security import hash_password

EMAIL = "techsupportashu@gmail.com"
PASSWORD = "SsdSupport@2026"


def main():
    db = SessionLocal()
    try:
        u = db.query(models.User).filter(models.User.email == EMAIL).first()
        created = u is None
        if created:
            u = models.User(name="Tech Support", email=EMAIL, role="techsupport",
                            emp_code="TS001", profile_completed=True)
            db.add(u)
        u.role = "techsupport"
        u.hashed_password = hash_password(PASSWORD)
        u.is_active = True
        u.must_change_password = False
        # Clear any brute-force lockout if those columns exist.
        for attr in ("failed_login_count", "lockout_until"):
            if hasattr(u, attr):
                setattr(u, attr, 0 if attr == "failed_login_count" else None)
        db.commit()
        print(("CREATED" if created else "UPDATED") + f" {EMAIL}")
        print(f"Password set to: {PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
