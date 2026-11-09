"""AI provider registry: presets, qwen3 thinking off, backup provider, model list, admin Test button."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_t = tempfile.TemporaryDirectory(prefix="aiprov-")
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(_t.name) / "p.db")
os.chdir(_t.name)

import httpx
from fastapi.testclient import TestClient

from app import ai_llm, models
from app.database import SessionLocal
from app.deps import get_current_user
from app.main import app


class Resp:
    def __init__(self, data, code=200):
        self._d, self.status_code, self.text = data, code, json.dumps(data)

    def json(self):
        return self._d

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("x", request=None, response=self)


def chat_reply(content="", calls=None):
    msg = {"content": content}
    if calls:
        msg["tool_calls"] = [{"id": "c1", "type": "function", "function": {"name": n, "arguments": "{}"}} for n in calls]
    return Resp({"choices": [{"message": msg}]})


class ProviderTests(unittest.TestCase):
    def test_default_is_local_qwen3_with_thinking_off(self):
        st = ai_llm.provider_status({})
        self.assertEqual((st["provider"], st["model"], st["local"], st["configured"]), ("ollama", "qwen3:4b", True, True))
        self.assertEqual(ai_llm.provider_status({"provider": "local"})["provider"], "ollama")     # old saved value
        seen = {}
        def post(url, json=None, headers=None, timeout=None):
            seen.update(url=url, body=json, headers=headers)
            return chat_reply("<think>long reasoning</think>Hello")
        with patch("app.ai_llm.httpx.post", side_effect=post):
            r = ai_llm.call_llm({}, "SYS", [{"role": "user", "content": "hi"}], [])
        self.assertEqual(r["content"], "Hello")                                   # reasoning stripped
        self.assertEqual(seen["url"], "http://127.0.0.1:11434/v1/chat/completions")
        self.assertIs(seen["body"]["think"], False)
        self.assertTrue(seen["body"]["messages"][0]["content"].endswith("/no_think"))
        self.assertNotIn("Authorization", seen["headers"])                         # no key sent to a local server

    def test_cloud_needs_key_and_uses_bearer(self):
        self.assertFalse(ai_llm.provider_status({"provider": "groq"})["configured"])
        seen = {}
        def post(url, json=None, headers=None, timeout=None):
            seen.update(url=url, headers=headers, body=json); return chat_reply("ok")
        with patch("app.ai_llm.httpx.post", side_effect=post):
            ai_llm.call_llm({"provider": "groq", "groq_api_key": "gsk_x"}, "S", [{"role": "user", "content": "q"}], [])
        self.assertEqual(seen["url"], "https://api.groq.com/openai/v1/chat/completions")
        self.assertEqual(seen["headers"]["Authorization"], "Bearer gsk_x")
        self.assertNotIn("think", seen["body"])                                    # only for local servers

    def test_backup_provider_answers_when_main_down(self):
        conf = {"provider": "ollama", "fallback_provider": "openai", "openai_api_key": "sk", "fallback_model": "gpt-4o-mini"}
        def post(url, json=None, headers=None, timeout=None):
            if "11434" in url:
                raise httpx.ConnectError("refused")
            return chat_reply("from backup")
        with patch("app.ai_llm.httpx.post", side_effect=post), patch("app.ai_llm.time.sleep"):
            r = ai_llm.call_llm(conf, "S", [{"role": "user", "content": "q"}], [])
        self.assertEqual((r["content"], r["provider_used"]), ("from backup", "openai"))

    def test_list_models_and_admin_test_button(self):
        db = SessionLocal()
        a = models.User(name="Admin", email="a@x", role="admin", is_active=True)
        m = models.User(name="Mgr", email="m@x", role="manager", is_active=True)
        db.add_all([a, m]); db.commit()
        aid, mid = a.id, m.id
        c = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: SessionLocal().get(models.User, mid)
        self.assertEqual(c.get("/api/ai/providers/models?provider=ollama").status_code, 403)
        app.dependency_overrides[get_current_user] = lambda: SessionLocal().get(models.User, aid)
        with patch("app.ai_llm.httpx.get", return_value=Resp({"data": [{"id": "qwen3:4b"}, {"id": "llama3.2:3b"}]})):
            self.assertEqual(c.get("/api/ai/providers/models?provider=ollama").json()["models"], ["llama3.2:3b", "qwen3:4b"])
        replies = [chat_reply("", ["whoami"]), chat_reply("You are Admin.")]
        with patch("app.ai_llm.httpx.post", side_effect=lambda *a, **k: replies.pop(0)):
            r = c.post("/api/ai/providers/test", json={}).json()
        self.assertTrue(r["ok"]); self.assertEqual(r["answer"], "You are Admin.")
        with patch("app.ai_llm.httpx.post", return_value=chat_reply("I am a chatbot")):
            r = c.post("/api/ai/providers/test", json={}).json()
        self.assertFalse(r["ok"]); self.assertEqual(r["step"], "tools")             # model can't drive AI Assist


if __name__ == "__main__":
    unittest.main(verbosity=2)
