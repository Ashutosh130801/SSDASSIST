"""Bulk actions (and DPR uploads) show as ONE Audit-Log line; the per-case rows stay in each case's History."""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_t = tempfile.TemporaryDirectory(prefix="auditbulk-")
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(_t.name) / "a.db")
os.chdir(_t.name)

# an OLD-style bulk re-allocation (one row per case, same second) written before the app starts
from app.database import Base, SessionLocal, engine
from app import models
Base.metadata.create_all(engine)
_db = SessionLocal()
_u = models.User(name="Old Admin", email="o@x", role="admin", is_active=True); _db.add(_u); _db.flush()
_cs = [models.Case(customer_name=f"O{i}", account_no=f"OLD{i}", bank="AXIS", product="X") for i in range(3)]
_db.add_all(_cs); _db.flush()
_t0 = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
for i, c in enumerate(_cs):
    _db.add(models.AuditLog(at=_t0 + timedelta(milliseconds=200 * i), actor_id=_u.id, actor_name="Old Admin", actor_role="admin",
                            action="reassign", case_id=c.id, bank="AXIS", product="X", field="assigned_fos_id", old_value="A", new_value="B"))
_db.add(models.AuditLog(at=_t0 + timedelta(hours=2), actor_id=_u.id, actor_name="Old Admin", action="reassign", case_id=_cs[0].id))  # lone edit
_db.commit(); _db.close()

from fastapi.testclient import TestClient
from app.deps import get_current_user
from app.main import app


class AuditBulkTests(unittest.TestCase):
    def test_bulk_lines(self):
        db = SessionLocal()
        a = models.User(name="Admin", email="a@x", role="admin", is_active=True)
        f1 = models.User(name="F One", email="f1@x", role="fos", is_active=True)
        f2 = models.User(name="F Two", email="f2@x", role="fos", is_active=True)
        db.add_all([a, f1, f2]); db.flush()
        cs = [models.Case(customer_name=f"C{i}", account_no=f"A{i}", bank="ICICI", product="PL", assigned_fos_id=f1.id) for i in range(4)]
        db.add_all(cs); db.commit()
        ids, aid, f2id = [c.id for c in cs], a.id, f2.id
        app.dependency_overrides[get_current_user] = lambda: SessionLocal().get(models.User, aid)
        c = TestClient(app)
        self.assertEqual(c.post("/api/cases/bulk-reassign", json={"case_ids": ids, "assigned_fos_id": f2id}).json()["updated"], 4)
        self.assertEqual(c.post("/api/cases/bulk-reassign", json={"case_ids": ids[:1], "assigned_fos_id": None}).json()["updated"], 1)
        c.post("/api/cases/remove", json={"ids": ids[2:], "reason": "dup"})
        items = c.get("/api/audit?limit=100").json()["items"]
        acts = [i["action"] for i in items]
        self.assertEqual(acts.count("bulk_reassign"), 2)       # the new one + the old grouped one
        self.assertIn("deallocate", acts)                       # single-case change stays a normal line
        self.assertIn("bulk_delete", acts)
        self.assertNotIn("reassign", acts[:3]); self.assertEqual(acts.count("delete"), 0)
        new = next(i for i in items if i["action"] == "bulk_reassign" and not i["meta"].get("grouped_later"))
        self.assertEqual(new["meta"]["cases"], 4); self.assertNotIn("items", new["meta"])     # light list
        full = c.get(f"/api/audit/{new['id']}").json()
        self.assertEqual(len(full["meta"]["items"]), 4); self.assertEqual(full["meta"]["items"][0]["new"], "F Two")
        self.assertEqual(c.get(f"/api/audit/{new['id']}/items.xlsx").status_code, 200)
        self.assertGreaterEqual(c.get(f"/api/audit?case_id={ids[0]}").json()["total"], 2)       # case history keeps per-case rows
        old = next(i for i in items if i["meta"].get("grouped_later"))
        self.assertEqual(old["meta"]["cases"], 3)
        self.assertEqual(sum(1 for i in items if i["action"] == "reassign"), 1)                  # the lone old edit


if __name__ == "__main__":
    unittest.main(verbosity=2)
