"""AI Assist upgrade: whole-app data tools (scoped + switchable in Services), visual answers built from real
data, follow-up suggestions, step log, and the floating bot's page context (masked)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_t = tempfile.TemporaryDirectory(prefix="aimore-")
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(_t.name) / "m.db")
os.chdir(_t.name)

from fastapi.testclient import TestClient

from app import ai_tools, audit, models
from app import services as svc
from app.database import SessionLocal
from app.deps import get_current_user
from app.main import app


def as_user(uid):
    app.dependency_overrides[get_current_user] = lambda: SessionLocal().get(models.User, uid)


class AiMoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db = SessionLocal()
        adm = models.User(name="Admin", email="a@x", role="admin", is_active=True)
        fos = models.User(name="Field One", email="f@x", role="fos", is_active=True)
        db.add_all([adm, fos]); db.flush()
        for i in range(6):
            db.add(models.Case(customer_name=f"C{i}", account_no=f"9876543210{i}", bank="AXIS" if i < 4 else "HDFC",
                               product="CC", bucket="X" if i % 2 else "1", enr=1000, pending_amount=1000 - 100 * i,
                               paid_status="PAID" if i < 2 else "UNPAID", assigned_fos_id=fos.id))
        db.flush()
        audit.record(db, adm, "reassign", db.query(models.Case).first(), detail="moved to Field One")
        db.add(models.LegalCase(borrower_name="C1", bank="AXIS", matter_type="Sec 138", status="open"))
        db.commit()
        cls.adm, cls.fos = adm.id, fos.id
        db.close()
        cls.c = TestClient(app)

    def test_new_tools_scoped(self):
        db = SessionLocal()
        adm, fos = db.get(models.User, self.adm), db.get(models.User, self.fos)
        r = ai_tools.run_tool(db, adm, "mis_breakdown", {"group_by": "bank", "bucket": "all"})
        self.assertEqual({x["bank"]: x["cases"] for x in r["rows"]}, {"AXIS": 4, "HDFC": 2})
        self.assertEqual(r["totals"]["paid"], 2)
        self.assertGreaterEqual(ai_tools.run_tool(db, adm, "audit_log", {"period": "today"})["count"], 1)
        self.assertEqual(ai_tools.run_tool(db, adm, "legal_cases", {})["count"], 1)
        with self.assertRaises(ai_tools.ToolError):
            ai_tools.run_tool(db, fos, "audit_log", {})                       # FOS can't see the Audit Log
        self.assertEqual(ai_tools.run_tool(db, fos, "legal_cases", {})["count"], 0)   # not linked to their cases
        db.close()

    def _reply(self, content="", calls=None):
        return {"content": content, "tool_calls": [{"id": f"c{i}", "name": n, "args": a} for i, (n, a) in enumerate(calls or [])]}

    def test_visual_suggestions_page_context(self):
        as_user(self.adm)
        seen = []
        replies = [
            self._reply("", [("make_visual", {"kind": "kpis", "source_tool": "mis_breakdown", "source_args": '{"group_by":"bank","bucket":"all"}',
                                              "fields": "cases,paid,pending"}),
                             ("make_visual", {"kind": "chart", "chart_type": "bar", "title": "By bank", "source_tool": "mis_breakdown",
                                              "source_args": '{"group_by":"bank","bucket":"all"}', "x": "bank", "y": "cases,paid"}),
                             ("make_visual", {"kind": "flow", "steps": "Open MIS > Pick bank > Download"})]),
            self._reply("AXIS has most cases.\nMood: celebrate\nSuggestions: Show HDFC only | Paid % by bucket | Make an Excel"),
        ]

        def fake(conf, system, messages, specs, **kw):
            seen.append((system, [m.get("content") for m in messages], [s["name"] for s in specs]))
            return replies.pop(0)
        with patch("app.ai_llm.call_llm", side_effect=fake):
            r = self.c.post("/api/ai/chat", json={"message": "dashboard of banks", "origin": "bot",
                                                  "page_context": {"section": "mis", "title": "MIS", "text": "Customer C1 phone 9876543210 owes 500"}}).json()
        kinds = [v["kind"] for v in r["visuals"]]
        self.assertEqual(kinds, ["kpis", "chart", "flow"])
        chart = r["visuals"][1]
        self.assertEqual(chart["labels"], ["AXIS", "HDFC"]); self.assertEqual(chart["series"][0]["data"], [4, 2])
        self.assertEqual(r["suggestions"], ["Show HDFC only", "Paid % by bucket", "Make an Excel"])
        self.assertNotIn("Suggestions", r["reply"]); self.assertNotIn("Mood", r["reply"]); self.assertEqual(r["mood"], "celebrate")
        self.assertEqual(len(r["steps"]), 3); self.assertTrue(all(s["ok"] for s in r["steps"]))
        first_user_msg = seen[0][1][-1]
        self.assertIn("SCREEN", first_user_msg); self.assertIn("XXXX3210", first_user_msg); self.assertNotIn("9876543210", first_user_msg)
        self.assertIn("audit_log", seen[0][2]); self.assertIn("make_visual", seen[0][2])
        conv = self.c.get(f"/api/ai/conversations/{r['conversation_id']}").json()
        self.assertEqual(len(conv["messages"][-1]["visuals"]), 3)                  # visuals kept in history

    def test_mood_fallback(self):
        from app.routers.ai import _split_mood
        self.assertEqual(_split_mood("Glad to help!", "thanks a lot")[1], "love")
        self.assertEqual(_split_mood("No cases found for that bank.", "axis cases")[1], "sorry")
        self.assertEqual(_split_mood("Here it is.\nMood: wink", "tip?"), ("Here it is.", "wink"))
        self.assertIsNone(_split_mood("Here are 5 cases.", "show cases")[1])

    def test_services_switch_off_data_area(self):
        db = SessionLocal()
        svc.save(db, "ai_assist", True, {**svc.settings_of(db, "ai_assist"), "data_audit": False, "allow_visuals": False})
        db.commit(); db.close()
        as_user(self.adm)
        specs_seen = []
        with patch("app.ai_llm.call_llm", side_effect=lambda conf, s, m, specs, **k: (specs_seen.append([x["name"] for x in specs]),
                                                                                     self._reply("ok"))[1]):
            self.c.post("/api/ai/chat", json={"message": "who changed what?"})
        self.assertNotIn("audit_log", specs_seen[0]); self.assertNotIn("dpr_uploads", specs_seen[0])
        self.assertNotIn("make_visual", specs_seen[0]); self.assertIn("mis_breakdown", specs_seen[0])
        st = self.c.get("/api/ai/status").json()
        self.assertIn("audit_log", st["tools_off"]); self.assertEqual(st["bot_avatar"], "rivet"); self.assertTrue(st["bot_user_pick"])
        db = SessionLocal()
        svc.save(db, "ai_assist", True, {**svc.settings_of(db, "ai_assist"), "data_audit": True, "allow_visuals": True})
        db.commit(); db.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
