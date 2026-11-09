"""📦 Monthly archive ZIP: admin-only, every portfolio + MIS + activity + summary for exactly that month."""
import io
import os
import sys
import tempfile
import unittest
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_t = tempfile.TemporaryDirectory(prefix="archzip-")
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(_t.name) / "z.db")
os.chdir(_t.name)

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app import models
from app.database import SessionLocal
from app.deps import get_current_user
from app.main import app


class ArchiveZipTests(unittest.TestCase):
    def test_zip(self):
        db = SessionLocal()
        a = models.User(name="Admin", email="a@x", role="admin", is_active=True)
        m = models.User(name="Mgr", email="m@x", role="manager", is_active=True)
        f = models.User(name="Ravi", email="f@x", role="fos", is_active=True, emp_code="F1")
        db.add_all([a, m, f]); db.flush()
        for i in range(12):
            db.add(models.Case(period="2026-10", bank="AXIS" if i % 2 else "ICICI", product="X/BKT", customer_name=f"C{i}",
                               account_no=f"A{i}", pending_amount=1000, total_outstanding=1000, received_amount=0,
                               paid_status="UNPAID", assigned_fos_id=f.id, close_date=date(2026, 10, 25), closing_type="cyc"))
        db.add(models.Case(period="2026-09", bank="AXIS", product="X/BKT", customer_name="OLD", account_no="OLD1"))
        db.flush()
        c1 = db.query(models.Case).filter_by(period="2026-10").first()
        db.add(models.CallLog(case_id=c1.id, caller_id=a.id, disposition="PAYMENT", ptp_amount=200, note="paid",
                              created_at=datetime(2026, 10, 3, 6, 0, tzinfo=timezone.utc)))
        db.add(models.Visit(case_id=c1.id, officer_id=f.id, disposition="PTP"))
        db.commit()
        aid, mid = a.id, m.id
        c = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: SessionLocal().get(models.User, mid)
        self.assertEqual(c.get("/api/archive/export.zip?period=2026-10").status_code, 403)
        app.dependency_overrides[get_current_user] = lambda: SessionLocal().get(models.User, aid)
        self.assertEqual(c.get("/api/archive/export.zip?period=bad").status_code, 400)
        r = c.get("/api/archive/export.zip?period=2026-10")
        self.assertEqual(r.status_code, 200)
        z = zipfile.ZipFile(io.BytesIO(r.content))
        names = z.namelist()
        root = "RecoverIQ_Archive_2026-10/"
        for n in ("00_Month_Summary.xlsx", "Portfolios/AXIS_X_BKT.xlsx", "Portfolios/ICICI_X_BKT.xlsx", "MIS/AXIS_X_BKT_MIS_Pivot.xlsx",
                  "Activity/Payments.xlsx", "Activity/Field_visits.xlsx", "Activity/Calls_and_PTPs.xlsx", "README.txt"):
            self.assertIn(root + n, names)
        self.assertIn("Cases: 12 in 2 portfolio(s)", z.read(root + "README.txt").decode())     # September case not included
        pay = list(load_workbook(io.BytesIO(z.read(root + "Activity/Payments.xlsx"))).active.iter_rows(values_only=True))
        self.assertEqual(pay[1][-4], 200); self.assertEqual(pay[1][0].hour, 11)                # 06:00 UTC → 11:30 IST
        db = SessionLocal()
        self.assertTrue(db.query(models.AuditLog).filter(models.AuditLog.detail.like("Monthly archive ZIP 2026-10%")).first())


if __name__ == "__main__":
    unittest.main(verbosity=2)
