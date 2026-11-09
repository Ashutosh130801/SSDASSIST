"""Services switchboard + AI Assist (scoping, masking, files, actions) with a fake LLM.

Run from app/backend:  .venv/Scripts/python.exe -B tests/test_ai_services.py
"""
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_temp = tempfile.TemporaryDirectory(prefix="ai-test-")
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(_temp.name) / "ai.db")
os.chdir(_temp.name)

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app import ai_llm, models
from app import services as svc
from app.database import SessionLocal
from app.deps import get_current_user
from app.main import app
from app.routers.cases import _current_period

SEEN = []          # every message list the fake LLM received


def fake_llm(script):
    """script: list of steps; each step = list of tool calls [(name, args)] or a final string."""
    steps = list(script)

    def call(conf, system, messages, tools, timeout=90):
        SEEN.append(json.loads(json.dumps(messages, default=str)))
        step = steps.pop(0) if steps else "done"
        if isinstance(step, str):
            return {"content": step, "tool_calls": []}
        return {"content": "", "tool_calls": [{"id": f"c{i}", "name": n, "args": a} for i, (n, a) in enumerate(step)]}
    return call


class AiServicesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db = SessionLocal()
        cls.admin = models.User(name="Admin", email="a@x.test", role="admin", is_active=True)
        cls.fos = models.User(name="Ravi", email="r@x.test", role="fos", is_active=True, emp_code="FO1")
        cls.fos2 = models.User(name="Other FOS", email="o@x.test", role="fos", is_active=True, emp_code="FO2")
        db.add_all([cls.admin, cls.fos, cls.fos2]); db.commit()
        per = _current_period()
        db.add_all([
            models.Case(customer_name="Mine One", account_no="ACC111122223333", phone="9876543210", bank="AXIS", product="X",
                        period=per, assigned_fos_id=cls.fos.id, pending_amount=5000, received_amount=0, paid_status="UNPAID"),
            models.Case(customer_name="Mine Two", account_no="ACC444455556666", phone="9876500000", bank="AXIS", product="X",
                        period=per, assigned_fos_id=cls.fos.id, pending_amount=0, received_amount=3000, paid_status="PAID"),
            models.Case(customer_name="Not Mine", account_no="ACC777788889999", phone="9000000000", bank="ICICI", product="Y",
                        period=per, assigned_fos_id=cls.fos2.id, pending_amount=99999, received_amount=88888, paid_status="UNPAID"),
        ])
        db.commit()
        cls.ids = {u.email: u.id for u in db.query(models.User)}
        db.close()
        cls.c = TestClient(app)

    def as_(self, email):
        db = SessionLocal()
        u = db.get(models.User, self.ids[email])
        app.dependency_overrides[get_current_user] = lambda: u
        return u

    def setUp(self):
        SEEN.clear()

    def test_services_toggle_gate(self):
        self.as_("a@x.test")
        lst = self.c.get("/api/services").json()
        keys = {s["key"]: s for s in lst}
        self.assertIn("ai_assist", keys); self.assertTrue(keys["ai_voice_bot"]["reminder"]); self.assertFalse(keys["ai_voice_bot"]["enabled"])
        self.assertEqual(self.c.put("/api/services/accounts", json={"enabled": False}).status_code, 400)        # required
        self.assertEqual(self.c.put("/api/services/legal", json={"enabled": False}).status_code, 200)
        r = self.c.get("/api/legal")
        self.assertEqual(r.status_code, 423)
        self.c.put("/api/services/legal", json={"enabled": True})
        self.assertNotEqual(self.c.get("/api/legal").status_code, 423)
        self.assertEqual(self.c.put("/api/services/ai_assist", json={"settings": {"daily_limit": "x"}}).status_code, 400)
        self.as_("r@x.test")
        self.assertEqual(self.c.put("/api/services/legal", json={"enabled": False}).status_code, 403)
        self.assertNotIn("settings", self.c.get("/api/services").json()[0])

    def test_ai_scope_and_masking(self):
        self.as_("r@x.test")
        ai_llm.call_llm = fake_llm([[("portfolio_summary", {}), ("search_cases", {"status": "any"})], "You have 2 cases."])
        r = self.c.post("/api/ai/chat", json={"message": "how many cases do I have?"}).json()
        self.assertEqual(r["reply"], "You have 2 cases.")
        tool_msgs = [m for m in SEEN[-1] if m["role"] == "tool"]
        blob = " ".join(m["content"] for m in tool_msgs)
        self.assertIn('"cases": 2', blob)
        self.assertNotIn("Not Mine", blob)                 # other FOS's case never reaches the AI
        self.assertNotIn("99999", blob)                    # nor their amounts (old bug: company-wide totals)
        self.assertNotIn("9876543210", blob)               # phone masked
        self.assertIn("XXXXXX3210", blob)

    def test_files_and_ownership(self):
        self.as_("r@x.test")
        ai_llm.call_llm = fake_llm([[("make_file", {"format": "xlsx", "title": "My unpaid", "source_tool": "search_cases",
                                                    "source_args": json.dumps({"status": "unpaid"})})], "Your file is ready."])
        r = self.c.post("/api/ai/chat", json={"message": "excel of my unpaid cases"}).json()
        self.assertEqual(len(r["files"]), 1)
        tok = r["files"][0]["token"]
        f = self.c.get(f"/api/ai/files/{tok}")
        self.assertEqual(f.status_code, 200)
        ws = load_workbook(io.BytesIO(f.content)).active
        vals = [c for row in ws.iter_rows(values_only=True) for c in row]
        self.assertIn("Mine One", vals); self.assertNotIn("Not Mine", vals)
        self.assertIn("9876543210", vals)                  # the user's own file keeps full numbers
        self.as_("o@x.test")
        self.assertEqual(self.c.get(f"/api/ai/files/{tok}").status_code, 404)
        self.as_("r@x.test")
        ai_llm.call_llm = fake_llm([[("make_document", {"format": "docx", "title": "Visit SOP", "content": "# Steps\n- one\n- two"})], "ok"])
        r = self.c.post("/api/ai/chat", json={"message": "write an SOP"}).json()
        self.assertTrue(r["files"][0]["name"].endswith(".docx"))

    def test_actions_need_confirmation_and_scope(self):
        u = self.as_("r@x.test")
        db = SessionLocal()
        mine = db.query(models.Case).filter_by(customer_name="Mine One").first()
        other = db.query(models.Case).filter_by(customer_name="Not Mine").first()
        ai_llm.call_llm = fake_llm([[("propose_action", {"type": "follow_up", "case_id": mine.id, "date": "2030-01-05", "note": "call back"}),
                                     ("propose_action", {"type": "follow_up", "case_id": other.id, "date": "2030-01-05"})], "Proposed."])
        r = self.c.post("/api/ai/chat", json={"message": "remind me"}).json()
        self.assertEqual(len(r["actions"]), 1)              # the other FOS's case was refused
        db.refresh(mine); self.assertIsNone(mine.follow_up_date)   # nothing changed before confirm
        self.assertEqual(self.c.post(f"/api/ai/actions/{r['actions'][0]['token']}/confirm").status_code, 200)
        db.refresh(mine); self.assertEqual(mine.follow_up_date, date(2030, 1, 5))
        self.assertEqual(self.c.post(f"/api/ai/actions/{r['actions'][0]['token']}/confirm").status_code, 400)
        # conversation memory
        conv = r["conversation_id"]
        ai_llm.call_llm = fake_llm(["again"])
        self.c.post("/api/ai/chat", json={"message": "and now?", "conversation_id": conv})
        self.assertTrue(any(m["role"] == "user" and m["content"] == "remind me" for m in SEEN[-1]))
        self.as_("o@x.test")
        self.assertEqual(self.c.get(f"/api/ai/conversations/{conv}").status_code, 404)

    def test_hr_has_no_case_access(self):
        db = SessionLocal()
        hr = models.User(name="HR", email="hr@x.test", role="hr", is_active=True); db.add(hr); db.commit()
        self.ids["hr@x.test"] = hr.id
        self.as_("hr@x.test")
        ai_llm.call_llm = fake_llm([[("search_cases", {})], "no access"])
        self.c.post("/api/ai/chat", json={"message": "cases?"})
        self.assertIn("no access to case data", [m for m in SEEN[-1] if m["role"] == "tool"][0]["content"])

    def test_tools_forgiving_and_data_map(self):
        from app import ai_tools
        from app.routers.ai import _data_context, _CTX_CACHE
        db = SessionLocal()
        fos = db.get(models.User, self.ids["r@x.test"])
        adm = db.get(models.User, self.ids["a@x.test"])
        r = ai_tools.run_tool(db, fos, "search_cases", {"bank": "Axis Bank Ltd"})          # fuzzy bank name
        self.assertEqual(r["total_matching"], 2)
        r = ai_tools.run_tool(db, fos, "search_cases", {"bank": "HDFC"})
        self.assertEqual(r["total_matching"], 0)
        self.assertIn("AXIS", r["why_empty"]["banks_available"])                            # tells the AI what exists
        self.assertEqual(ai_tools.run_tool(db, fos, "search_cases", {"status": "pending"})["total_matching"], 1)   # synonym
        # month with no data yet → latest month with data, and it says so
        db.add(models.Case(customer_name="Old", account_no="OLD1", bank="RBL", product="CC", period="2020-01", paid_status="UNPAID"))
        db.commit()
        r = ai_tools.run_tool(db, adm, "search_cases", {"month": "2020-01"})
        self.assertEqual(r["total_matching"], 1)
        _CTX_CACHE.clear()
        ctx = _data_context(db, fos)
        self.assertIn("AXIS / X", ctx); self.assertNotIn("ICICI", ctx)                     # only what the FOS can see
        self.assertIn("Ravi", ctx)
        ov = ai_tools.run_tool(db, adm, "data_overview", {})
        self.assertTrue(any(m["month"] == "2020-01" for m in ov["months"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
