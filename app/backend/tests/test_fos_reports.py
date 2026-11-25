"""FOS daily visit report + monthly visit/attendance sheet generate valid, styled workbooks."""
import unittest, io
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_t = tempfile.TemporaryDirectory(prefix="fr-")
os.environ["DATABASE_URL"] = "sqlite:///" + _t.name + "/t.db"
os.chdir(_t.name)
from datetime import datetime, timedelta, date, timezone
from fastapi.testclient import TestClient
from app import models, presence
from app.database import SessionLocal
from app.deps import get_current_user
from app.main import app
import random
random.seed(3)
db = SessionLocal()
hr = models.User(name="HR", email="hr@x", role="hr", is_active=True)
db.add(hr); db.flush()
names=[("CHINTA SRINIVASA RAO","TANUKU","EAST &WEST","9154934446"),("NADIPINTI BHARATH CHANDRA","KAIKALURU - ELURU","EAST &WEST","8639680560"),
("AKULA UDAY KUMAR","KAKINADA","EAST &WEST","9032220101"),("MANIKE VIJAYA BABU","CHILAKALURIPETA","GUNTUR","9885269778"),
("GAJULA PRAVEEN","MANCHERIAL","TELANGANA","8639562425"),("KARRI YASWANTH","VIZAG","VISAKHAPATNAM","7793912147")]
fos=[]
for i,(n,a,b,ph) in enumerate(names):
    u=models.User(name=n,email=f"f{i}@x",role="fos",is_active=True,branch=b,location=a,phone=ph,
                  joining_date=date(2026,11,10) if i==5 else date(2025,1,1))
    db.add(u); fos.append(u)
c=models.Case(customer_name="X",account_no="1",bank="AXIS",product="CC"); db.add(c); db.flush()
IST=presence.IST
start=date(2026,10,21)
for d in (start+timedelta(days=k) for k in range(35)):
    if d>date(2026,11,25): break
    for i,u in enumerate(fos):
        if i==5 and d<date(2026,11,10): continue
        if d.weekday()==6 and random.random()<0.8: continue
        r=random.random()
        if r<0.08: continue                         # absent
        if r<0.12:
            db.add(models.Leave(user_id=u.id,start_date=d,end_date=d,days=1,status="approved",leave_type="Casual",reason="Family function")); continue
        cin=datetime(d.year,d.month,d.day,random.choice([7,8,8,9,10,11]),random.randint(0,59),tzinfo=IST)
        db.add(models.Attendance(user_id=u.id,date=d,check_in_at=cin.astimezone(timezone.utc),status="present",
               check_out_at=(cin+timedelta(hours=9)).astimezone(timezone.utc)))
        for k in range(random.choice([0,1,2,3,4,5,6,7,9])):
            t=cin+timedelta(minutes=random.randint(20,560))
            db.add(models.Visit(case_id=c.id,officer_id=u.id,created_at=t.astimezone(timezone.utc),paid=random.random()<0.15,amount_collected=0))
db.commit()
app.dependency_overrides[get_current_user]=lambda: SessionLocal().get(models.User, hr.id)
cl=TestClient(app)


class FosReports(unittest.TestCase):
    def test_daily(self):
        import openpyxl
        r = cl.get("/api/attendance/fos-report/daily.xlsx?start=2026-11-20&end=2026-11-22")
        self.assertEqual(r.status_code, 200, r.text[:200])
        wb = openpyxl.load_workbook(io.BytesIO(r.content))
        self.assertEqual(wb.sheetnames, ["Summary", "20-11-2026", "21-11-2026", "22-11-2026"])
        ws = wb["20-11-2026"]
        self.assertEqual(ws["B2"].value, "TODAY FIELD VISIT REPORT")
        self.assertEqual(ws.cell(row=4, column=9).value, "PRODUCTIVE VISIT (PAID)")
        self.assertEqual(ws.max_row > 6, True)

    def test_monthly(self):
        import openpyxl
        r = cl.get("/api/attendance/fos-report/monthly.xlsx?start=2026-10-21&end=2026-11-20")
        self.assertEqual(r.status_code, 200, r.text[:200])
        ws = openpyxl.load_workbook(io.BytesIO(r.content)).worksheets[0]
        self.assertEqual(ws.cell(row=8, column=8).value, 21)          # first day column = 21st
        vals = {ws.cell(row=15, column=8 + k).value for k in range(31)}
        self.assertIn("NA", vals)                                         # joined 10 Nov → earlier days NA
        self.assertEqual(ws.cell(row=8, column=8 + 31).value, "TOTAL COUNT")

    def test_previews_match_excel(self):
        import openpyxl
        d = cl.get("/api/attendance/fos-report/daily?start=2026-11-20&end=2026-11-21").json()
        self.assertEqual([x["date"] for x in d["days"]], ["2026-11-20", "2026-11-21"])
        day = d["days"][0]
        self.assertEqual(day["totals"]["visits"], sum(r["total"] for r in day["rows"]))
        m = cl.get("/api/attendance/fos-report/monthly?start=2026-10-21&end=2026-11-20").json()
        self.assertEqual(len(m["days"]), 31)
        ws = openpyxl.load_workbook(io.BytesIO(cl.get(
            "/api/attendance/fos-report/monthly.xlsx?start=2026-10-21&end=2026-11-20").content)).worksheets[0]
        for i, r in enumerate(m["rows"]):
            excel = [ws.cell(row=10 + i, column=8 + k).value for k in range(31)]
            self.assertEqual(excel, r["days"])                       # preview grid == Excel grid

    def test_bad_range(self):
        self.assertEqual(cl.get("/api/attendance/fos-report/daily.xlsx?start=2026-09-01&end=2026-11-20").status_code, 400)


if __name__ == "__main__":
    unittest.main()
