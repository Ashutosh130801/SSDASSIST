"""
Read-only: see exactly what a TEAM LEAD gets in MIS, My Portfolios and Team Accounts — against the
REAL database — without their password. It signs a short-lived token for that user in the
team-lead view and calls the same API endpoints the screens call (GET only; nothing is changed).

USAGE (from app/backend, using the backend's own Python):
    .venv\\Scripts\\python.exe check_tl_view.py "IMMANDI"        # part of the name
    .venv\\Scripts\\python.exe check_tl_view.py TL014           # or an emp / TL code
"""
import sys

sys.path.insert(0, ".")
from sqlalchemy import or_, func                     # noqa: E402
from fastapi.testclient import TestClient            # noqa: E402
from app.main import app                             # noqa: E402
from app.database import SessionLocal               # noqa: E402
from app import models                              # noqa: E402
from app.security import create_access_token        # noqa: E402
from app.routers.cases import teamlead_case_filter, _current_period, _next_period, _last_period  # noqa: E402

if len(sys.argv) < 2:
    print(__doc__)
    sys.exit(1)
key = sys.argv[1].strip()

db = SessionLocal()
cands = (db.query(models.User)
         .filter(or_(models.User.role == "teamlead", models.User.also_team_lead.is_(True)))
         .filter(or_(models.User.name.ilike(f"%{key}%"), func.upper(models.User.emp_code) == key.upper(),
                     func.upper(models.User.tl_emp_code) == key.upper()))
         .all())
if not cands:
    print(f"No team lead matches '{key}'.")
    sys.exit(1)
if len(cands) > 1:
    print("Several team leads match — use a code instead:")
    for u in cands:
        print(f"   {u.name}  role={u.role}  emp={u.emp_code}  tl={u.tl_emp_code}")
    sys.exit(1)
u = cands[0]
print(f"\nTEAM LEAD: {u.name}  (role={u.role}, emp={u.emp_code}, tl_code={u.tl_emp_code}, branch={u.branch})")
print(f"Months: this={_current_period()}  next={_next_period()}  last={_last_period()}")

# Raw truth from the DB: this lead's cases (same rule the app uses), by month / portfolio
rows = (db.query(models.Case.period, models.Case.bank, models.Case.product, func.count(models.Case.id))
        .filter(models.Case.removed.isnot(True), teamlead_case_filter(u))
        .group_by(models.Case.period, models.Case.bank, models.Case.product).all())
print("\nDB — cases whose TEAM LEAD column is this lead:")
if not rows:
    vals = (db.query(models.Case.team_lead, func.count(models.Case.id)).filter(models.Case.removed.isnot(True))
            .group_by(models.Case.team_lead).order_by(func.count(models.Case.id).desc()).limit(15).all())
    print("   NONE. The case TEAM LEAD column must equal this lead's name, emp code or TL code.")
    print("   Most common TEAM LEAD values in the data:", vals)
for per, b, p, n in sorted(rows, key=lambda r: (r[0] or "", r[1] or "", r[2] or "")):
    print(f"   {per or '-'}  {b} / {p}: {n}")

c = TestClient(app)          # no 'with' → startup jobs don't run; only GETs below
h = {"Authorization": f"Bearer {create_access_token(str(u.id), 'teamlead', u.name)}"}


def get(path):
    r = c.get(path, headers=h)
    return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:200])


print("\nMIS screen (portfolio list per month):")
for mb in ("current", "next", "last", ""):
    st, js = get("/api/cases/product-summary" + (f"?month_bucket={mb}" if mb else ""))
    lst = [f"{x.get('bank')}/{x.get('product')} ({x.get('count')})" for x in js] if st == 200 else js
    print(f"   {mb or 'all':<8} {st}  {lst}")
    if st == 200 and js and mb:
        x = js[0]
        st2, m = get(f"/api/mis?bank={x['bank']}&product={x['product']}&month_bucket={mb}")
        cnt = (m.get("overall") or {}).get("count") if st2 == 200 and isinstance(m, dict) else m
        print(f"            MIS for {x['bank']}/{x['product']}: {st2} cases={cnt}")

print("\nMy Portfolios:")
st, pfs = get("/api/team/portfolios")
print(f"   {st}  " + (", ".join(f"{p['bank']}/{p['product']}/{p['branch'] or '-'} ({p['count']})" for p in pfs) if st == 200 else str(pfs)))
if st == 200:
    for p in pfs[:3]:
        q = f"bank={p['bank']}&product={p['product']}&branch={p['branch']}"
        st2, leads = get(f"/api/team/portfolio/leads?{q}")
        if st2 != 200:
            print(f"   leads {p['product']}: {st2} {leads}")
            continue
        me = next((l for l in leads if l.get("is_me")), leads[0] if leads else None)
        if not me:
            continue
        for mb in ("current", "next", "last", "all"):
            st3, ov = get(f"/api/team/portfolio/lead/{me['id']}/overview?{q}&month_bucket={mb}")
            k = (ov or {}).get("kpis", {}) if st3 == 200 else {}
            print(f"   {p['product']} · {me['name']} · {mb:<7} {st3} cases={k.get('cases')} members={k.get('members')}")

print("\nTeam Accounts (case list) per month:")
for mb in ("current", "next", "last"):
    st, js = get(f"/api/cases?limit=5000&month_bucket={mb}")
    print(f"   {mb:<8} {st}  {len(js) if st == 200 else js}")
print("\nDone — nothing was changed.")
