"""API keys saved in ⚙️ Services: admin-only, encrypted at rest, write-only, .env fallback, used by AI Assist."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_t = tempfile.TemporaryDirectory(prefix="svckeys-")
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(_t.name) / "k.db")
os.chdir(_t.name)

from fastapi.testclient import TestClient

from app import ai_llm, models
from app import services as svc
from app.database import SessionLocal
from app.deps import get_current_user
from app.main import app

KEY = "AIzaSyTEST-secret-value-1234"


class KeyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db = SessionLocal()
        cls.a = models.User(name="A", email="a@x", role="admin", is_active=True)
        cls.m = models.User(name="M", email="m@x", role="manager", is_active=True)
        db.add_all([cls.a, cls.m]); db.commit()
        cls.ids = (cls.a.id, cls.m.id); db.close()
        cls.c = TestClient(app)

    def as_(self, i):
        app.dependency_overrides[get_current_user] = lambda: SessionLocal().get(models.User, i)

    def test_keys(self):
        self.as_(self.ids[1])
        self.assertEqual(self.c.put("/api/services/ai_assist", json={"secrets": {"gemini_api_key": KEY}}).status_code, 403)
        self.as_(self.ids[0])
        self.assertEqual(self.c.put("/api/services/ai_assist", json={"secrets": {"gemini_api_key": KEY}}).status_code, 200)
        row = SessionLocal().get(models.AppSetting, "services")
        self.assertNotIn(KEY, row.value)                                 # encrypted at rest
        lst = self.c.get("/api/services").text
        self.assertNotIn(KEY, lst)                                       # never sent back
        ai = [s for s in json.loads(lst) if s["key"] == "ai_assist"][0]
        self.assertEqual(ai["secrets"]["gemini_api_key"], {"set": True, "source": "app", "hint": "••••1234"})
        db = SessionLocal()
        self.assertEqual(svc.secret(db, "ai_assist", "gemini_api_key"), KEY)
        from app.routers.ai import _conf
        self.assertTrue(ai_llm.provider_status(_conf(db))["configured"])
        audit = db.query(models.AuditLog).filter(models.AuditLog.action == "service.update").all()
        self.assertTrue(any("API keys changed: gemini_api_key" in (a.detail or "") for a in audit))
        self.assertFalse(any(KEY in " ".join(str(getattr(a, c.name)) for c in a.__table__.columns) for a in audit))
        self.c.put("/api/services/ai_assist", json={"settings": {"daily_limit": 50}})   # other saves keep the key
        self.assertEqual(svc.secret(SessionLocal(), "ai_assist", "gemini_api_key"), KEY)
        self.c.put("/api/services/ai_assist", json={"clear_secrets": ["gemini_api_key"]})
        self.assertEqual(svc.secret(SessionLocal(), "ai_assist", "gemini_api_key"), "")   # no .env in tests


if __name__ == "__main__":
    unittest.main(verbosity=2)
