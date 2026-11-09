"""Payroll tests (engine maths + API end to end) on an isolated in-memory database.

Run from app/backend:  .venv/Scripts/python.exe -B tests/test_payroll.py
"""
import io
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_temp = tempfile.TemporaryDirectory(prefix="payroll-test-")
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(_temp.name) / "unused.db")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models, payroll_engine as eng, tax_engine as tx
from app.database import Base, get_db
from app.deps import get_current_user
from app.routers import payouts as payouts_mod
from app.routers.payroll import router
from app.routers.payroll_extra import router as extra_router
from app.security import hash_password


def xlsx(rows):
    wb = Workbook()
    for r in rows:
        wb.active.append(r)
    b = io.BytesIO(); wb.save(b)
    return b.getvalue()


class EngineTests(unittest.TestCase):
    cfg = eng.merged_config({})

    def test_split_gross(self):
        p = {x["code"]: x["full"] for x in eng.split_gross(18000, self.cfg["components"])}
        self.assertEqual(p, {"BASIC": Decimal("9000.00"), "HRA": Decimal("3600.00"), "CONV": Decimal("1600.00"), "SPECIAL": Decimal("3800.00")})
        self.assertEqual(sum(p.values()), Decimal("18000.00"))
        p = {x["code"]: x["full"] for x in eng.split_gross(3000, self.cfg["components"])}  # small gross never exceeds itself
        self.assertEqual(sum(p.values()), Decimal("3000.00"))

    def test_cycle(self):
        self.assertEqual(eng.cycle_for("2026-11", 21), (date(2026, 10, 21), date(2026, 11, 20)))
        self.assertEqual(eng.cycle_for("2026-01", 21), (date(2025, 12, 21), date(2026, 1, 20)))
        self.assertEqual(eng.cycle_for("2026-02", 1), (date(2026, 2, 1), date(2026, 2, 28)))

    def _att(self, absent=0, n=31, late=0):
        days = [{"date": date(2026, 10, 21 + i) if i < 11 else date(2026, 11, i - 10), "present": 1, "leave": 0,
                 "absent": 0, "late": 0, "weekoff": 0, "half_days": 0, "late_half": 0, "unpaid_leave": 0} for i in range(n)]
        for i in range(absent):
            days[i].update(present=0, absent=1)
        for i in range(late):
            days[-1 - i]["late"] = 1
        return eng.attendance_lop(days, self.cfg, date(2026, 10, 21), date(2026, 11, 20), None, None, False)

    def test_lop_and_late_rule(self):
        a = self._att(absent=2, late=6)            # 6 lates → 2 × 0.5 = 1 day
        self.assertEqual((a["lop"], a["paid_days"], a["divisor"]), (3.0, 28.0, 31.0))

    def test_statutory(self):
        att = self._att()
        r = eng.compute_line(gross_monthly=18000, components=self.cfg["components"], overrides={}, att=att,
                             paid_days_override=None, adjustments=[{"kind": "earning", "code": "INCENTIVE", "amount": 2500}],
                             adj_types={a["code"]: a for a in self.cfg["adjustment_types"]}, advances=[],
                             flags_in={"pf": True, "esi": True, "pt": True, "lwf": False, "tds": 0}, cfg=self.cfg, period="2026-11")
        d = {x["code"]: x["amount"] for x in r["deductions"]}
        self.assertEqual(r["gross"], 20500.0)
        self.assertEqual(d["PF"], 1080.0)               # 12% of basic 9000
        self.assertEqual(d["ESI"], 154.0)               # ceil(20500 × 0.75%)
        self.assertEqual(d["PT"], 200.0)                # > 20000
        self.assertEqual(r["net"], 20500 - 1080 - 154 - 200)
        er = {x["code"]: x["amount"] for x in r["employer"]}
        self.assertEqual(er["PF_EPS"] + er["PF_EPF"], 1080.0)

    def test_advance_never_makes_net_negative(self):
        att = self._att(absent=30)
        r = eng.compute_line(gross_monthly=10000, components=self.cfg["components"], overrides={}, att=att,
                             paid_days_override=None, adjustments=[], adj_types={}, advances=[{"id": 1, "emi": 5000, "balance": 9000}],
                             flags_in={"pf": False, "esi": False, "pt": False, "lwf": False, "tds": 0}, cfg=self.cfg, period="2026-11")
        self.assertGreaterEqual(r["net"], 0)
        self.assertTrue(any("cut" in f["text"] for f in r["flags"]))

    def test_words(self):
        self.assertEqual(eng.words_inr(132293), "Rupees One Lakh Thirty Two Thousand Two Hundred Ninety Three Only")


class ApiTests(unittest.TestCase):
    def setUp(self):
        payouts_mod.SECTION_LOCKED = False
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.admin = models.User(name="Admin", email="a@x.test", role="admin", is_active=True, hashed_password=hash_password("pw123456"))
        self.hr = models.User(name="HR", email="hr@x.test", role="hr", is_active=True)
        self.e1 = models.User(name="Ravi Kumar", email="r@x.test", role="fos", is_active=True, emp_code="FO047",
                              bank_account="918010012345671", ifsc_code="UTIB0001234", bank_holder="RAVI KUMAR", bank_name="AXIS BANK")
        self.e2 = models.User(name="Lakshmi", email="l@x.test", role="telecaller", is_active=True, emp_code="TC012",
                              bank_account="50100123456789", ifsc_code="HDFC0001234", bank_name="HDFC")
        self.e3 = models.User(name="No Bank", email="n@x.test", role="telecaller", is_active=True, emp_code="TC099")
        self.db.add_all([self.admin, self.hr, self.e1, self.e2, self.e3]); self.db.commit()
        self.actor = self.admin
        app = FastAPI(); app.include_router(extra_router); app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: self.actor
        app.dependency_overrides[get_db] = lambda: self.db
        self.c = TestClient(app)

    def tearDown(self):
        payouts_mod.SECTION_LOCKED = True
        self.c.close(); self.db.close()

    def ok(self, r):
        self.assertLess(r.status_code, 300, r.text[:500]); return r

    def setup_salaries(self):
        self.ok(self.c.post(f"/api/payroll/employees/{self.e1.id}/salary", json={"monthly_gross": 18000, "effective_from": "2026-01-01"}))
        self.ok(self.c.post(f"/api/payroll/employees/{self.e2.id}/salary", json={"monthly_gross": 14000, "effective_from": "2026-01-01", "esi_applicable": "N"}))
        self.ok(self.c.post(f"/api/payroll/employees/{self.e3.id}/salary", json={"monthly_gross": 12000, "effective_from": "2026-01-01"}))

    def test_locked_and_roles(self):
        payouts_mod.SECTION_LOCKED = True
        self.assertEqual(self.c.get("/api/payroll/runs").status_code, 423)
        payouts_mod.SECTION_LOCKED = False
        self.actor = self.e1
        self.assertEqual(self.c.get("/api/payroll/runs").status_code, 403)
        self.assertEqual(self.c.get("/api/payroll/my").status_code, 200)
        self.actor = self.hr
        self.assertEqual(self.c.get("/api/payroll/runs").status_code, 200)
        self.assertEqual(self.c.put("/api/payroll/config", json={"config": {}}).status_code, 403)

    def test_config_validation(self):
        cfg = self.ok(self.c.get("/api/payroll/config")).json()["config"]
        cfg["components"].append({"code": "BASIC", "name": "dup", "calc": "fixed", "value": 1})
        r = self.c.put("/api/payroll/config", json={"config": cfg})
        self.assertEqual(r.status_code, 400)
        cfg["components"].pop(); cfg["cycle"]["start_day"] = 1
        self.ok(self.c.put("/api/payroll/config", json={"config": cfg}))

    def test_full_run(self):
        self.setup_salaries()
        # attendance: Ravi absent 2 days (no check-in on past weekdays → absent), others checked in daily
        for u in (self.e1, self.e2, self.e3):
            d = date(2026, 10, 21)
            while d <= date(2026, 11, 20):
                if d.weekday() != 6 and not (u is self.e1 and d in (date(2026, 10, 22), date(2026, 10, 23))):
                    self.db.add(models.Attendance(user_id=u.id, date=d, check_in_at=datetime(d.year, d.month, d.day, 4, 0, tzinfo=timezone.utc)))
                d = date.fromordinal(d.toordinal() + 1)
        self.db.add(models.SalaryAdvance(user_id=self.e2.id, principal=3000, emi=1000, balance=3000, start_period="2026-11"))
        self.db.commit()
        run = self.ok(self.c.post("/api/payroll/runs", json={"period": "2026-11"})).json()
        L = {l["snapshot"]["emp_code"]: l for l in run["lines"]}
        self.assertEqual(L["FO047"]["attendance"]["lop"], 2.0)
        self.assertEqual(L["FO047"]["attendance"]["paid_days"], 29.0)
        self.assertTrue(any(f["level"] == "error" for f in L["TC099"]["flags"]))      # no bank
        self.assertTrue(any(d["code"] == "ADVANCE" for d in L["TC012"]["deductions"]))
        self.assertFalse(any(d["code"] == "ESI" for d in L["TC012"]["deductions"]))
        # duplicate run refused
        self.assertEqual(self.c.post("/api/payroll/runs", json={"period": "2026-11"}).status_code, 400)
        # adjustment upload
        up = self.c.post(f"/api/payroll/runs/{run['id']}/adjustments/upload", data={"commit": "true"},
                         files={"file": ("a.xlsx", xlsx([["Emp ID", "Type", "Amount", "Note"], ["FO047", "INCENTIVE", 2500, "Nov"]]))})
        self.ok(up)
        run = self.ok(self.c.get(f"/api/payroll/runs/{run['id']}")).json()
        L = {l["snapshot"]["emp_code"]: l for l in run["lines"]}
        self.assertTrue(any(e["code"] == "INCENTIVE" for e in L["FO047"]["earnings"]))
        # approval blocked by the no-bank error
        r = self.c.post(f"/api/payroll/runs/{run['id']}/approve", json={"password": "pw123456", "confirm_total": run["totals"]["net"]})
        self.assertEqual(r.status_code, 400)
        # exclude needs a reason
        self.assertEqual(self.c.patch(f"/api/payroll/runs/{run['id']}/lines/{L['TC099']['id']}", json={"included": False}).status_code, 400)
        run = self.ok(self.c.patch(f"/api/payroll/runs/{run['id']}/lines/{L['TC099']['id']}", json={"included": False, "exclude_reason": "Bank pending"})).json()
        net = run["totals"]["net"]
        self.assertEqual(self.c.post(f"/api/payroll/runs/{run['id']}/approve", json={"password": "bad", "confirm_total": net}).status_code, 401)
        self.assertEqual(self.c.post(f"/api/payroll/runs/{run['id']}/approve", json={"password": "pw123456", "confirm_total": net + 5}).status_code, 400)
        run = self.ok(self.c.post(f"/api/payroll/runs/{run['id']}/approve", json={"password": "pw123456", "confirm_total": net})).json()
        self.assertEqual(run["status"], "approved")
        self.assertEqual(float(self.db.query(models.SalaryAdvance).first().balance), 2000.0)
        # locked
        self.assertEqual(self.c.post(f"/api/payroll/runs/{run['id']}/recalculate").status_code, 400)
        # bank file
        tpl = self.ok(self.c.get("/api/payroll/bank-templates")).json()
        axis = tpl[0]
        r = self.ok(self.c.get(f"/api/payroll/runs/{run['id']}/bank-file?template_id={axis['id']}"))
        ws = load_workbook(io.BytesIO(r.content)).active
        rows = list(ws.iter_rows(values_only=True))
        self.assertEqual(rows[0][0], "Payment Mode")
        self.assertEqual(len(rows), 3)                               # header + 2 paid employees
        modes = {row[5]: row[0] for row in rows[1:]}
        self.assertEqual(modes["918010012345671"], "I")              # Axis → Axis
        self.assertEqual(modes["50100123456789"], "N")               # other bank → NEFT
        self.assertAlmostEqual(sum(row[1] for row in rows[1:]), net, places=2)
        # bank details changed after approval → bank file refused
        self.e1.bank_account = "111122223333"; self.db.commit()
        self.assertEqual(self.c.get(f"/api/payroll/runs/{run['id']}/bank-file?template_id={axis['id']}").status_code, 409)
        self.e1.bank_account = "918010012345671"; self.db.commit()
        # documents
        for p in ("register.xlsx", "payslips.pdf", "ecr.txt", "statutory.xlsx"):
            r = self.ok(self.c.get(f"/api/payroll/runs/{run['id']}/{p}"))
            self.assertGreater(len(r.content), 50, p)
        self.assertTrue(self.c.get(f"/api/payroll/runs/{run['id']}/payslips.pdf").content.startswith(b"%PDF"))
        # employee can't see until released
        self.actor = self.e1
        self.assertEqual(self.c.get("/api/payroll/my").json(), [])
        self.actor = self.admin
        self.ok(self.c.post(f"/api/payroll/runs/{run['id']}/release", json={}))
        self.actor = self.e1
        mine = self.c.get("/api/payroll/my").json()
        self.assertEqual(len(mine), 1)
        self.assertTrue(self.c.get(f"/api/payroll/my/{mine[0]['line_id']}.pdf").content.startswith(b"%PDF"))
        other = [l for l in run["lines"] if l["user_id"] == self.e2.id][0]
        self.assertEqual(self.c.get(f"/api/payroll/my/{other['id']}.pdf").status_code, 404)      # not someone else's
        self.actor = self.admin
        # bank status report → UTR + paid
        st = xlsx([["Customer Ref No", "UTR", "Status"], [f"PR{run['id']}FO047", "AXISN1234", "Success"], [f"PR{run['id']}TC012", "", "Failed"]])
        r = self.ok(self.c.post(f"/api/payroll/runs/{run['id']}/bank-status", files={"file": ("s.xlsx", st)})).json()
        self.assertEqual((r["matched"], r["failed"]), (2, 1))
        # reopen restores the advance
        run2 = self.ok(self.c.post(f"/api/payroll/runs/{run['id']}/reopen", json={"password": "pw123456", "reason": "fix incentive"})).json()
        self.assertEqual(run2["status"], "draft")
        self.assertEqual(float(self.db.query(models.SalaryAdvance).first().balance), 3000.0)

    def test_auto_tds_and_statements(self):
        rich = models.User(name="Big Earner", email="b@x.test", role="manager", is_active=True, emp_code="MG001", pan_number="ABCDE1234F",
                           bank_account="918010099999999", ifsc_code="UTIB0001234")
        self.db.add(rich); self.db.commit()
        self.ok(self.c.post(f"/api/payroll/employees/{rich.id}/salary", json={"monthly_gross": 200000, "effective_from": "2026-01-01", "attendance_exempt": "Y"}))
        run = self.ok(self.c.post("/api/payroll/runs", json={"period": "2026-11"})).json()
        L = [l for l in run["lines"] if l["user_id"] == rich.id][0]
        tds = [d for d in L["deductions"] if d["code"] == "TDS"]
        self.assertTrue(tds and tds[0]["amount"] > 0, L["attendance"].get("tax"))
        self.assertEqual(L["attendance"]["tax"]["regime"], "new")
        # switching to old regime with no declarations raises the tax
        self.ok(self.c.put(f"/api/payroll/tax/declarations/{rich.id}?fy=2026-27", json={"regime": "old", "data": {}}))
        run = self.ok(self.c.post(f"/api/payroll/runs/{run['id']}/recalculate")).json()
        L2 = [l for l in run["lines"] if l["user_id"] == rich.id][0]
        self.assertGreater([d for d in L2["deductions"] if d["code"] == "TDS"][0]["amount"], tds[0]["amount"])
        lst = self.ok(self.c.get("/api/payroll/tax/declarations?fy=2026-27")).json()
        self.assertTrue(any(r["projection"] and r["projection"]["annual_tax"] > 0 for r in lst["rows"]))
        run = self.ok(self.c.get(f"/api/payroll/runs/{run['id']}")).json()
        self.ok(self.c.post(f"/api/payroll/runs/{run['id']}/approve", json={"password": "pw123456", "confirm_total": run["totals"]["net"]}))
        pdf = self.ok(self.c.get(f"/api/payroll/tax/form16.pdf?fy=2026-27&user_id={rich.id}"))
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        q = self.ok(self.c.get("/api/payroll/tax/24q.xlsx?fy=2026-27&quarter=Q3"))
        ws = load_workbook(io.BytesIO(q.content)).active
        self.assertTrue(any(r[3] == "ABCDE1234F" for r in ws.iter_rows(min_row=5, values_only=True)))
        self.actor = rich
        me = self.ok(self.c.get("/api/payroll/my/tax")).json()
        self.assertTrue(me["allow_edit"])
        self.ok(self.c.put("/api/payroll/my/tax", json={"regime": "new", "data": {"sec80c": 50000}}))
        self.assertTrue(self.c.get("/api/payroll/my/form16.pdf?fy=2026-27").content.startswith(b"%PDF"))

    def test_full_and_final(self):
        self.setup_salaries()
        self.e1.joining_date = date(2020, 6, 1); self.db.commit()
        self.db.add(models.SalaryAdvance(user_id=self.e1.id, principal=5000, emi=1000, balance=4000, start_period="2026-06"))
        self.db.commit()
        p = self.ok(self.c.post("/api/payroll/fnf/preview", json={"user_id": self.e1.id, "last_working_day": "2026-11-10",
                                                                   "notice_served_days": 20})).json()
        codes = {i["code"] for i in p["items"]}
        self.assertTrue({"SALARY", "LEAVE_ENCASH", "GRATUITY", "NOTICE_RECOVERY", "ADVANCE"} <= codes, codes)
        grat = [i for i in p["items"] if i["code"] == "GRATUITY"][0]["amount"]
        self.assertAlmostEqual(grat, round(15 / 26 * 9000 * 6, 2), places=2)       # 6.4 yrs → 6
        f = self.ok(self.c.post("/api/payroll/fnf", json={"user_id": self.e1.id, "last_working_day": "2026-11-10", "items": p["items"],
                                                            "reason": "resigned"})).json()
        self.assertEqual(self.c.post("/api/payroll/fnf", json={"user_id": self.e1.id, "last_working_day": "2026-11-10", "items": []}).status_code, 400)
        items = f["items"] + [{"kind": "earning", "code": "BONUS", "name": "Festival bonus", "amount": 1000}]
        f = self.ok(self.c.put(f"/api/payroll/fnf/{f['id']}", json={"items": items})).json()
        self.assertEqual(self.c.post(f"/api/payroll/fnf/{f['id']}/approve", json={"password": "pw123456", "confirm_total": f["net"] + 9}).status_code, 400)
        f = self.ok(self.c.post(f"/api/payroll/fnf/{f['id']}/approve", json={"password": "pw123456", "confirm_total": f["net"]})).json()
        self.assertEqual(f["status"], "approved")
        self.db.refresh(self.e1)
        self.assertFalse(self.e1.is_active)
        self.assertEqual(float(self.db.query(models.SalaryAdvance).filter_by(user_id=self.e1.id).first().balance), 0.0)
        # the payroll run for that month must not pay them again
        run = self.ok(self.c.post("/api/payroll/runs", json={"period": "2026-11"})).json()
        self.assertFalse(any(l["user_id"] == self.e1.id for l in run["lines"]))
        self.ok(self.c.post(f"/api/payroll/fnf/{f['id']}/paid", json={"paid_on": "2026-11-15", "utr": "AXIS123"}))
        self.assertTrue(self.c.get(f"/api/payroll/fnf/{f['id']}.pdf").content.startswith(b"%PDF"))

    def test_salary_upload_and_template_parse(self):
        r = self.ok(self.c.post("/api/payroll/employees/upload", data={"commit": "false"},
                                files={"file": ("s.xlsx", xlsx([["Emp ID", "Name", "Monthly Gross", "Effective From"],
                                                                 ["FO047", "Ravi", 20000, "2026-04-01"], ["ZZ1", "x", 1, "2026-04-01"]]))})).json()
        self.assertEqual((len(r["valid"]), len(r["errors"])), (1, 1))
        self.assertEqual(self.c.post("/api/payroll/employees/upload", data={"commit": "true"},
                                     files={"file": ("s.xlsx", xlsx([["Emp ID", "Monthly Gross"], ["ZZ1", 5]]))}).status_code, 400)
        p = self.ok(self.c.post("/api/payroll/bank-templates/parse",
                                files={"file": ("axis.xlsx", xlsx([["AXIS BANK"], ["Txn Type", "Amount", "Beneficiary Account No", "Bene IFSC", "Beneficiary Name", "Debit Account"], ["N", 1, "1", "X", "Y", "Z"]]))})).json()
        self.assertEqual([c["field"] for c in p["columns"]], ["payment_mode", "amount", "beneficiary_account", "ifsc", "beneficiary_name", "debit_account"])
        t = self.ok(self.c.post("/api/payroll/bank-templates", json={"name": "My Axis", "bank": "AXIS", "file_type": "csv", "columns": p["columns"],
                                                                        "options": {"same_bank_ifsc": "UTIB"}})).json()
        self.assertEqual(t["file_type"], "csv")
        self.assertEqual(self.c.post("/api/payroll/bank-templates", json={"name": "bad", "columns": [{"header": "x", "field": "amount"}]}).status_code, 400)


class TaxTests(unittest.TestCase):
    cfg = tx.DEFAULT_TAX

    def test_new_regime_rebate_and_marginal_relief(self):
        self.assertEqual(tx.tax_on(1200000, "new", self.cfg)["total"], 0)
        r = tx.tax_on(1210000, "new", self.cfg)               # tax can't exceed the 10,000 over the limit
        self.assertEqual(r["total"], 10400.0)                   # 10,000 + 4% cess
        self.assertEqual(tx.tax_on(2400000, "new", self.cfg)["total"], 312000.0)   # 300,000 + cess

    def test_old_regime_with_declarations(self):
        a = tx.compute_annual(regime="old", cfg=self.cfg, gross=900000, basic=450000, hra=180000, pf=54000, pt=2400,
                              decl={"sec80c": 100000, "rent_paid_annual": 240000}, metro=False)
        # HRA exempt = min(180000, 240000-45000, 180000) = 180000 ; 80C capped 150000 (incl PF)
        self.assertEqual(a["hra_exempt"], 180000.0)
        self.assertEqual(a["taxable"], 900000 - 180000 - 50000 - 2400 - 150000)

    def test_fy_helpers(self):
        self.assertEqual(tx.fy_of("2026-11"), "2026-27")
        self.assertEqual(tx.fy_of("2027-02"), "2026-27")
        self.assertEqual(len(tx.fy_periods("2026-27")), 12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
