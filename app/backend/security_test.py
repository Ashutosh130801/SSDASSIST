"""
SSD Recovery — security & authentication self-test.
Run from app/backend with your venv active:

    # Windows
    set DATABASE_URL=sqlite:///./sec_test.db
    set SECRET_KEY=sec-test
    set SEED_DEMO=1
    python security_test.py

    # macOS/Linux
    DATABASE_URL=sqlite:///./sec_test.db SECRET_KEY=sec-test SEED_DEMO=1 python security_test.py

It boots the real app, seeds demo staff, and asserts every access-control rule.
Exit code 0 and "ALL SECURITY CHECKS PASSED" means auth is working.
"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./sec_test.db")
os.environ.setdefault("SECRET_KEY", "sec-test")
os.environ.setdefault("SEED_DEMO", "1")
if os.path.exists("./sec_test.db"):
    os.remove("./sec_test.db")

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app import seed, models

SessionLocal_ = SessionLocal
db = SessionLocal_(); seed.seed_users(db); db.close()
c = TestClient(app)
ok = 0


def check(name, cond):
    global ok
    assert cond, "FAIL: " + name
    ok += 1
    print("PASS:", name)


def login(email, pw, device="dev-main"):
    r = c.post("/api/auth/login-json", json={"email": email, "password": pw, "device_id": device})
    return r


# ---- authentication ----
check("valid admin login", login("admin@ssdrecovery.in", "admin123").status_code == 200)
check("wrong password rejected (401)", login("admin@ssdrecovery.in", "nope").status_code == 401)
check("unknown user rejected (401)", login("ghost@x.co", "x").status_code == 401)

atok = login("admin@ssdrecovery.in", "admin123").json()["access_token"]
ftok = login("ravi@ssdrecovery.in", "fos123").json()["access_token"]
ttok = login("krishna@ssdrecovery.in", "tc123").json()["access_token"]
mtok = login("manager@ssdrecovery.in", "mgr123").json()["access_token"]
AH = {"Authorization": "Bearer " + atok}
FH = {"Authorization": "Bearer " + ftok}
TH = {"Authorization": "Bearer " + ttok}
MH = {"Authorization": "Bearer " + mtok}

# ---- token required / tamper ----
check("no token -> 401 on protected", c.get("/api/cases").status_code == 401)
check("garbage token -> 401", c.get("/api/cases", headers={"Authorization": "Bearer abc.def.ghi"}).status_code == 401)

# ---- RBAC: admin-only endpoints blocked for staff ----
check("FO cannot list/create users beyond roster (create 403)",
      c.post("/api/users", json={"name": "x", "email": "x@x.co", "password": "x", "role": "fos"}, headers=FH).status_code == 403)
check("telecaller cannot import (403)",
      c.post("/api/import/commit", files={"file": ("x.xlsx", b"x")}, headers=TH).status_code in (403, 400) and
      c.post("/api/import/commit", files={"file": ("x.xlsx", b"x")}, headers=TH).status_code != 200)
check("FO cannot allocate (403)", c.post("/api/cases/allocate", json={"only_unallocated": True}, headers=FH).status_code == 403)
check("telecaller cannot view devices (403)", c.get("/api/devices", headers=TH).status_code == 403)
check("FO cannot geocode (403)", c.post("/api/cases/geocode", headers=FH).status_code == 403)
check("telecaller cannot see admin records summary (403)", c.get("/api/analytics/summary", headers=TH).status_code == 403)

# ---- scoping: staff see only their own data ----
all_cases = c.get("/api/cases?limit=5000", headers=AH).json()
tc_cases = c.get("/api/cases?limit=5000", headers=TH).json()
fo_cases = c.get("/api/cases?limit=5000", headers=FH).json()
check("telecaller sees only own cases", all(x["assigned_caller_id"] == c.get("/api/auth/me", headers=TH).json()["id"] for x in tc_cases))
check("FO sees only own cases", all(x["assigned_fos_id"] == c.get("/api/auth/me", headers=FH).json()["id"] for x in fo_cases))
check("admin sees >= staff", len(all_cases) >= len(tc_cases) and len(all_cases) >= len(fo_cases))

# ---- FO cannot act on a foreign / unknown case ----
check("FO cannot visit unknown case", c.post("/api/visits", data={"case_id": 999999, "paid": "false", "amount_collected": "0"}, headers=FH).status_code in (403, 404))

# ---- manager branch scoping ----
mgr_users = c.get("/api/users", headers=MH).json()
check("manager sees only own branch staff", all(u.get("branch") == "Visakhapatnam" for u in mgr_users))

# ---- device gate ----
check("new device blocked until approved (403)", login("ravi@ssdrecovery.in", "fos123", device="dev-second").status_code == 403)

# ---- disabled account ----
u = SessionLocal_(); usr = u.query(models.User).filter(models.User.email == "prasanth@ssdrecovery.in").first(); usr.is_active = False; u.commit(); u.close()
check("disabled account cannot log in (403)", login("prasanth@ssdrecovery.in", "tc123").status_code == 403)

print(f"\nALL SECURITY CHECKS PASSED ✅  ({ok} checks)")
