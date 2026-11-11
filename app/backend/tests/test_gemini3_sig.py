"""Gemini 3: thought signatures on function calls must be sent back, or Google returns 400."""
import sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import ai_llm


class R:
    def __init__(self, j): self.j, self.status_code, self.text = j, 200, ""
    def json(self): return self.j


class Gemini3Sig(unittest.TestCase):
    def test_signature_round_trip(self):
        sent = []
        def post(url, json=None, **k):
            sent.append(json)
            return R({"candidates": [{"content": {"parts": [
                {"text": "thinking…", "thought": True},
                {"functionCall": {"name": "whoami", "args": {}}, "thoughtSignature": "SIG123"}]}}]})
        with patch("app.ai_llm.httpx.post", side_effect=post):
            r1 = ai_llm._gemini("k", "gemini-3.8-flash", "s", [{"role": "user", "content": "hi"}], [{"name": "whoami"}], 5)
            self.assertEqual(r1["content"], "")                      # thought text never shown
            self.assertEqual(r1["tool_calls"][0]["sig"], "SIG123")
            ai_llm._gemini("k", "gemini-3.8-flash", "s", [{"role": "user", "content": "hi"},
                           {"role": "assistant", "content": "", "tool_calls": r1["tool_calls"]},
                           {"role": "tool", "tool_call_id": "x", "name": "whoami", "content": "{}"}], None, 5)
        fc = sent[1]["contents"][1]["parts"][0]
        self.assertEqual(fc["thoughtSignature"], "SIG123")

    def test_history_without_signature_uses_skip_value(self):
        sent = []
        with patch("app.ai_llm.httpx.post", side_effect=lambda url, json=None, **k: sent.append(json) or R({"candidates": []})):
            ai_llm._gemini("k", "gemini-3.8-flash", "s", [{"role": "user", "content": "hi"},
                           {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "name": "a", "args": {}}]}], None, 5)
        self.assertEqual(sent[0]["contents"][1]["parts"][0]["thoughtSignature"], "skip_thought_signature_validator")


if __name__ == "__main__":
    unittest.main()
