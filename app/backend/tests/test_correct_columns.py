"""Correction regression tests; uses an isolated database, never the configured live DB.

Run from app/backend: .venv/Scripts/python.exe -B tests/test_correct_columns.py
Optionally set CORRECTION_WORKBOOK to inspect a real workbook in memory as well.
"""
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_temp = tempfile.TemporaryDirectory(prefix="correct-columns-test-")
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(_temp.name) / "unused.db")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app import models
from app.database import Base, get_db, engine as configured_engine
from app.deps import get_current_user
from app.excel_io import import_workbook, record_to_case_kwargs
from app.routers.imports import router, _correct_scan


def workbook(headers, rows):
    wb = Workbook()
    wb.active.append(headers)
    for row in rows:
        wb.active.append(row)
    stream = io.BytesIO()
    wb.save(stream)
    wb.close()
    return stream.getvalue()


class CorrectColumnsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", poolclass=StaticPool,
                                    connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.actor = models.User(name="Test Admin", email="admin@example.test", role="admin", is_active=True)
        self.db.add(self.actor)
        self.db.commit()
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.dependency_overrides[get_current_user] = lambda: self.actor
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(self.app)
        self.scope = dict(scope_selected="true", scope_bank="ICICI", scope_product="FR", scope_period="2026-10", scope_branch="Vizag")

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def case(self, **kw):
        data = dict(account_no="A001", card_no="C001", customer_name="Test Customer",
                    bank="ICICI", product="FR", period="2026-10", branch="Vizag",
                    address="Old address", received_amount=Decimal("100.00"),
                    remarks="Existing feedback", paid_status="PARTIAL", disposition="PTP",
                    extra={"x_organisation": "Old company", "x_ptp_date": "2026-10-20"})
        data.update(kw)
        cs = models.Case(**data)
        self.db.add(cs)
        self.db.commit()
        return cs

    def post(self, endpoint, data, **form):
        return self.client.post("/api/import/correct/" + endpoint,
                                files={"file": ("correction.xlsx", data)}, data={**self.scope, **form})

    def test_card_only_match_and_selected_source_columns(self):
        cs = self.case(account_no=None)
        officer = models.User(name="Field Test", email="fos@example.test", role="fos", emp_code="FO001", is_active=True)
        self.db.add(officer)
        self.db.flush()
        self.db.add(models.Visit(case_id=cs.id, officer_id=officer.id, note="Keep visit", amount_collected=25))
        self.db.add(models.CallLog(case_id=cs.id, caller_id=self.actor.id, note="Keep call", disposition="PTP"))
        self.db.commit()
        data = workbook(["ACC.NO", "CC NO", "NAMES", "ADD 1", "AREA", "ORGANISATION", "DESIGNATION",
                         "PAID/UNPAID", "STATUS", "RECEIVED AMOUNT", "REMARKS", "PTP DATE", "CARD TYPE"],
                        [[None, "C001", "Test Customer", "New address", "New area", "New company", "Manager",
                          "PAID", "PAID", 900, "Replace feedback", "2026-11-01", "Rubyx"]])
        preview = self.post("preview", data)
        self.assertEqual(preview.status_code, 200, preview.text)
        p = preview.json()
        self.assertEqual(p["accounts_matched"], 1)
        self.assertEqual(p["matched_by_card"], 1)
        self.assertEqual(len(p["detected_columns"]), 13)
        self.assertEqual(cs.address, "Old address")  # preview never writes
        changed = {c["field"] for c in p["columns"]}
        self.assertTrue({"address", "team", "x_organisation", "x_designation"} <= changed)
        self.assertFalse({"received_amount", "paid_status", "remarks", "x_ptp_date"} & changed)
        applied = self.post("apply", data, fields="address,x_organisation,received_amount,remarks,x_ptp_date")
        self.assertEqual(applied.status_code, 200, applied.text)
        self.db.refresh(cs)
        self.assertEqual(cs.address, "New address")
        self.assertEqual(cs.extra["x_organisation"], "New company")
        self.assertEqual(cs.extra["x_ptp_date"], "2026-10-20")
        self.assertIsNone(cs.team)  # unchecked field stays unchanged
        self.assertEqual(cs.received_amount, Decimal("100.00"))
        self.assertEqual(cs.remarks, "Existing feedback")
        self.assertEqual(cs.paid_status, "PARTIAL")
        self.assertEqual(self.db.query(models.Visit).one().note, "Keep visit")
        self.assertEqual(self.db.query(models.CallLog).one().note, "Keep call")

    def test_scope_excludes_other_month_branch_bank_product_and_removed(self):
        target = self.case(account_no=None)
        for change in [dict(period="2026-09"), dict(branch="Other"), dict(bank="AXIS"),
                       dict(product="Other"), dict(removed=True)]:
            self.case(account_no=None, **change)
        data = workbook(["CC NO", "ADD 1"], [["C001", "Updated"]])
        p = self.post("preview", data).json()
        self.assertEqual(p["accounts_matched"], 1)
        r = self.post("apply", data, fields="address")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["cases_changed"], 1)
        self.assertEqual(self.db.query(models.Case).filter(models.Case.address == "Updated").one().id, target.id)

    def test_ambiguous_cards_are_not_applied(self):
        self.case(account_no="A1")
        self.case(account_no="A2")
        data = workbook(["CC NO", "ADD 1"], [["C001", "Updated"]])
        p = self.post("preview", data).json()
        self.assertEqual(p["accounts_matched"], 0)
        self.assertEqual(p["rows_ambiguous"], 1)
        self.assertEqual(self.post("apply", data, fields="address").json()["cases_changed"], 0)

    def test_blank_selected_branch_is_not_a_wildcard(self):
        self.case()
        self.scope["scope_branch"] = ""
        data = workbook(["CC NO", "ADD 1"], [["C001", "Updated"]])
        self.assertEqual(self.post("preview", data).json()["accounts_matched"], 0)
        self.case(branch=None)
        self.assertEqual(self.post("preview", data).json()["accounts_matched"], 1)

    def test_account_is_authoritative_when_present(self):
        cs = self.case()
        data = workbook(["ACC NO", "CC NO", "ADD 1"], [["WRONG", "C001", "Updated"]])
        self.assertEqual(self.post("preview", data).json()["accounts_matched"], 0)
        data = workbook(["ACC NO", "CC NO", "ADD 1"], [["A001", "C-NEW", "Updated"]])
        self.assertEqual(self.post("preview", data).json()["matched_by_account"], 1)
        self.post("apply", data, fields="card_no")
        self.db.refresh(cs)
        self.assertEqual(cs.card_no, "C-NEW")
        self.assertEqual(cs.address, "Old address")

    def test_missing_identifiers_reported_not_silently_skipped(self):
        data = workbook(["NAMES", "ADD 1"], [["Test Customer", "Updated"]])
        p = self.post("preview", data).json()
        self.assertEqual(p["rows_missing_identifier"], 1)
        self.assertEqual(p["rows_no_match"], 1)

    def test_upload_and_corrections_share_aliases_and_unknown_report(self):
        self.case()
        data = workbook(["Loan Account Number", "Credit Card Number", "Customer Name", "Mobile Number",
                         "Address Line 2", "Organisation", "Unmapped custom heading"],
                        [["A001", "C001", "Test Customer", "9000000000", "Second address", "Company", "Value"]])
        records, _ = import_workbook(data)
        fields = record_to_case_kwargs(records[0])
        self.assertEqual(fields["account_no"], "A001")
        self.assertEqual(fields["address2"], "Second address")
        p = self.post("preview", data).json()
        self.assertEqual(p["accounts_matched"], 1)
        self.assertEqual(p["detected_columns"][-1]["use"], "unrecognised")
        self.assertTrue({"phone", "address2", "x_organisation"} <= {c["field"] for c in p["columns"]})

    def test_blank_money_and_alias_do_not_erase_populated_values(self):
        self.case(norm_amount=300)
        data = workbook(["ACC NO", "ACCOUNT NO", "NORM", "ADD 1"], [["A001", None, None, "Updated"]])
        p = self.post("preview", data).json()
        self.assertEqual(p["accounts_matched"], 1)
        self.assertNotIn("norm_amount", {c["field"] for c in p["columns"]})
        data = workbook(["ACC NO", "NORM"], [["A001", 0]])
        self.assertIn("norm_amount", {c["field"] for c in self.post("preview", data).json()["columns"]})

    def test_dual_role_employee_id_matches_upload(self):
        cs = self.case()
        u = models.User(name="Dual role", email="dual@example.test", role="telecaller", emp_code="TC001",
                        also_field_agent=True, fos_emp_code="FO099", is_active=True)
        self.db.add(u)
        self.db.commit()
        data = workbook(["ACC NO", "FOS NAME"], [["A001", "FO099"]])
        p = self.post("preview", data).json()
        self.assertIn("fos_name", {c["field"] for c in p["columns"]})
        r = self.post("apply", data, fields="fos_name")
        self.assertEqual(r.status_code, 200, r.text)
        self.db.refresh(cs)
        self.assertEqual(cs.assigned_fos_id, u.id)

    def test_inactive_and_wrong_role_staff_are_not_assigned(self):
        self.case()
        u = models.User(name="Inactive", email="inactive@example.test", role="fos", emp_code="FO001", is_active=False)
        self.db.add(u)
        self.db.commit()
        data = workbook(["ACC NO", "FOS NAME"], [["A001", "FO001"]])
        p = self.post("preview", data).json()
        self.assertEqual(p["unresolved_assignments"], 1)
        self.assertNotIn("fos_name", {c["field"] for c in p["columns"]})

    def test_no_changes_is_distinct_from_no_match(self):
        self.case()
        data = workbook(["ACC NO", "ADD 1"], [["A001", "Old address"]])
        p = self.post("preview", data).json()
        self.assertEqual(p["accounts_matched"], 1)
        self.assertEqual(p["columns"], [])

    def test_fos_cannot_correct_columns(self):
        self.actor.role = "fos"
        self.db.commit()
        data = workbook(["ACC NO", "ADD 1"], [["A001", "Updated"]])
        self.assertEqual(self.post("preview", data).status_code, 403)
        self.assertEqual(self.post("apply", data, fields="address").status_code, 403)

    @unittest.skipUnless(os.environ.get("CORRECTION_WORKBOOK"), "Optional real workbook not supplied")
    def test_real_workbook_in_isolated_database(self):
        data = Path(os.environ["CORRECTION_WORKBOOK"]).read_bytes()
        metadata = {}
        records, _ = import_workbook(data, metadata=metadata)
        self.assertEqual(len(records), 637)
        self.assertEqual(len(metadata["headers"]), 33)
        self.assertTrue(all(h["mapped_field"] for h in metadata["headers"]))
        self.assertTrue(all(not r.get("account_no") and r.get("card_no") for r in records))
        for r in records:
            self.db.add(models.Case(card_no=r["card_no"], bank="ICICI", product="FR", period="2026-10",
                                    branch="Vizag", address="Synthetic old address", customer_name="Test only"))
        self.db.commit()
        p = self.post("preview", data).json()
        self.assertEqual(p["accounts_matched"], 637)
        self.assertEqual(p["matched_by_card"], 637)
        self.assertEqual(p["rows_no_match"], 0)
        self.assertTrue(p["columns"])


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        configured_engine.dispose()
        _temp.cleanup()
