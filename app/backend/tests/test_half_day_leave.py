"""Half-day leave end-to-end tests against an isolated SQLite database."""
import ast
import io
from datetime import date, datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import patch

import test_predictive_screenpop as fixture
from sqlalchemy import create_engine, inspect, text
from app.routers import leaves, attendance
from app.leave_policy import day_credit


class HalfDayTests(unittest.TestCase):
    def setUp(self):
        fixture.ScreenPopTests.setUp(self)
        self.app.include_router(leaves.router)
        self.app.include_router(attendance.router)
        self.employee = self.actor
        self.admin = fixture.models.User(name="Admin", email="admin@test.example", role="admin", is_active=True)
        self.db.add(self.admin); self.db.commit()
        self.today = date(2026, 10, 9)
        self.patchers = [patch.object(leaves, "_today", return_value=self.today),
                         patch.object(attendance, "_ist_today", return_value=self.today),
                         patch.object(leaves, "_changed")]
        for p in self.patchers: p.start()

    def tearDown(self):
        for p in self.patchers: p.stop()
        fixture.ScreenPopTests.tearDown(self)

    def apply(self, half=True, start="2026-10-08", end=None, **extra):
        return self.client.post("/api/leaves", json=dict(leave_type="Casual", start_date=start,
            end_date=end or start, half_day=half, reason="Test request", **extra))

    def decision(self, lid, decision="approve", actor=None):
        original = self.actor
        self.actor = actor or self.admin
        try: return self.client.post(f"/api/leaves/{lid}/{decision}")
        finally: self.actor = original

    def checkin(self, day=date(2026, 10, 8), late=False):
        self.db.add(fixture.models.Attendance(user_id=self.employee.id, date=day, late=late,
            check_in_at=datetime(day.year, day.month, day.day, 4, tzinfo=timezone.utc),
            check_out_at=datetime(day.year, day.month, day.day, 8, tzinfo=timezone.utc),
            status="present", shift_start="09:00", shift_end="19:00"))
        self.db.commit()

    def day(self, day="2026-10-08"):
        r = self.client.get("/api/attendance/day", params={"date": day})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["rows"][0]

    def month(self):
        r = self.client.get("/api/attendance/month?month=2026-10")
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["people"][0]

    def test_pending_and_rejected_do_not_change_attendance(self):
        r = self.apply(); self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["half_day"])
        self.assertEqual(r.json()["days_effective"], 0.5)
        self.assertEqual(self.day()["status"], "absent")
        self.assertEqual(self.client.get("/api/leaves/balance").json()[0]["pending"], 0.5)
        self.assertEqual(self.decision(r.json()["id"], "reject").status_code, 200)
        self.assertEqual(self.day()["status"], "absent")
        self.assertEqual(self.client.get("/api/leaves/balance").json()[0]["used"], 0)

    def test_approved_with_checkin_daily_monthly_and_balances(self):
        self.checkin(late=True)
        r = self.apply(); self.assertEqual(self.decision(r.json()["id"]).status_code, 200)
        d = self.day(); m = self.month()
        self.assertEqual(d["status"], "half_leave")
        self.assertEqual((d["present_days"], d["leave_days"], d["absent_days"]), (0.5, 0.5, 0))
        self.assertTrue(d["late"])
        self.assertEqual(m["days"]["2026-10-08"], "HD")
        self.assertEqual((m["present"], m["leave"], m["half_days"], m["late"]), (0.5, 0.5, 1, 1))
        self.assertEqual(m["worked_hours"], 4)
        b = self.client.get("/api/leaves/balance").json()[0]
        self.assertEqual((b["used"], b["remaining"], b["pending"]), (0.5, 11.5, 0))
        self.actor = self.admin
        bs = self.client.get("/api/leaves/balances?year=2026").json()["rows"]
        self.assertEqual(next(x for x in bs if x["user_id"] == self.employee.id)["total_taken"], 0.5)

    def test_past_no_checkin_half_absent(self):
        r = self.apply(); self.decision(r.json()["id"])
        self.assertEqual(self.day()["absent_days"], 0.5)
        self.assertEqual(self.month()["present"], 0)
        self.assertEqual(self.month()["leave"], 0.5)

    def test_future_half_not_absent(self):
        before = self.month()["absent"]
        r = self.apply(start="2026-10-12"); self.decision(r.json()["id"])
        self.assertEqual(self.day("2026-10-12")["absent_days"], 0)
        self.assertEqual(self.month()["absent"], before)

    def test_current_day_unworked_half_not_yet_absent(self):
        r = self.apply(start="2026-10-09"); self.decision(r.json()["id"])
        self.assertEqual(self.day("2026-10-09")["absent_days"], 0)

    def test_multiday_half_and_reverse_dates_rejected(self):
        self.assertEqual(self.apply(end="2026-10-09").status_code, 400)
        self.assertEqual(self.apply(False, end="2026-10-07").status_code, 400)

    def test_duplicate_overlap_and_reapply_after_rejection(self):
        first = self.apply()
        self.assertEqual(self.apply().status_code, 409)
        self.assertEqual(self.apply(False, start="2026-10-07", end="2026-10-10").status_code, 409)
        self.decision(first.json()["id"], "reject")
        self.assertEqual(self.apply().status_code, 200)

    def test_no_self_approval_and_cross_branch_manager(self):
        r = self.apply(); lid = r.json()["id"]
        self.employee.role = "manager"; self.db.commit()
        self.assertEqual(self.decision(lid, actor=self.employee).status_code, 403)
        manager = fixture.models.User(name="Other manager", email="other@test.example", role="manager", branch="Other", is_active=True)
        self.db.add(manager); self.db.commit()
        self.assertEqual(self.decision(lid, actor=manager).status_code, 403)

    def test_repeated_approval_is_idempotent(self):
        lid = self.apply().json()["id"]
        self.assertEqual(self.decision(lid).status_code, 200)
        self.assertEqual(self.decision(lid).status_code, 200)
        self.assertEqual(self.decision(lid, "reject").status_code, 409)
        self.assertEqual(self.db.query(fixture.models.AuditLog).filter_by(action="leave_approved").count(), 1)
        self.assertEqual(self.client.get("/api/leaves/balance").json()[0]["used"], 0.5)

    def test_full_day_legacy_null_and_year_boundaries(self):
        self.db.add(fixture.models.Leave(user_id=self.employee.id, leave_type="Casual", start_date=date(2025,12,31), end_date=date(2026,1,2), days=3, status="approved"))
        self.db.add(fixture.models.Leave(user_id=self.employee.id, leave_type="Casual", start_date=date(2027,1,1), end_date=date(2027,1,1), days=1, status="approved"))
        self.db.commit()
        self.db.execute(text("UPDATE leaves SET half_day=NULL")); self.db.commit()
        self.assertEqual(self.client.get("/api/leaves/balance").json()[0]["used"], 2)
        self.assertFalse(self.client.get("/api/leaves?scope=mine").json()[0]["half_day"])

    def test_full_day_and_sunday_daily_month_consistent(self):
        self.checkin()
        lid = self.apply(False).json()["id"]; self.decision(lid)
        self.assertEqual(self.day()["status"], "leave")
        self.assertEqual(self.month()["days"]["2026-10-08"], "LV")
        self.assertEqual(self.month()["present"], 0)
        lid = self.apply(start="2026-10-04").json()["id"]; self.decision(lid)
        self.assertEqual(self.day("2026-10-04")["status"], "half_leave")
        self.assertEqual(self.month()["days"]["2026-10-04"], "HD")

    def test_excel_export_fractional_totals_and_legend(self):
        import openpyxl
        self.checkin(); self.decision(self.apply().json()["id"])
        self.actor = self.admin
        r = self.client.get("/api/attendance/download?month=2026-10")
        self.assertEqual(r.status_code, 200, r.text[:100] if r.status_code != 200 else "")
        wb = openpyxl.load_workbook(io.BytesIO(r.content))
        sheet = wb.worksheets[0]
        headers = [c.value for c in sheet[1]]
        row = [c.value for c in sheet[2]]
        self.assertEqual(row[headers.index("08")], "HD")
        self.assertEqual(row[headers.index("Present")], 0.5)
        self.assertEqual(row[headers.index("Leave")], 0.5)
        self.assertEqual(row[headers.index("Half-day leaves")], 1)
        self.assertIn("Legend", wb.sheetnames)

    def test_non_manager_team_scope_remains_private(self):
        self.apply()
        self.actor = self.admin
        self.apply(start="2026-10-12")
        self.actor = self.employee; self.actor.role = "backend"; self.db.commit()
        self.assertEqual(len(self.client.get("/api/leaves?scope=team").json()), 1)

    def test_migration_adds_flag_preserves_rows_and_is_repeatable(self):
        # Execute only the actual migration function, never import production app.main.
        tree = ast.parse((Path(__file__).parents[1] / "app/main.py").read_text(encoding="utf-8"))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_ensure_columns")
        engine = create_engine("sqlite://")
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE leaves (id INTEGER PRIMARY KEY, days INTEGER)"))
            conn.execute(text("INSERT INTO leaves VALUES (1, 3)"))
        ns = dict(engine=engine, inspect=inspect, text=text)
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "migration", "exec"), ns)
        ns["_ensure_columns"](); ns["_ensure_columns"]()
        with engine.begin() as conn:
            conn.execute(text("UPDATE leaves SET half_day = NULL WHERE id = 1"))
        ns["_ensure_columns"]()
        with engine.connect() as conn:
            self.assertEqual(tuple(conn.execute(text("SELECT days, half_day FROM leaves")).one()), (3, 0))
        engine.dispose()


if __name__ == "__main__": unittest.main(verbosity=2)
