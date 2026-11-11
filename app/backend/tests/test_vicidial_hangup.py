"""Hang up from RecoverIQ: confirm with agent_status, fall back to Asterisk AMI, never fake 'ended'."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_temp = tempfile.TemporaryDirectory(prefix="hangup-test-")
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(_temp.name) / "unused.db")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models, vicidial_ami
from app.database import Base, get_db
from app.deps import get_current_user
from app.routers import integrations
from app.routers.integrations import router


def st(status="INCALL", call_id="M1109000000000012345"):
    return {"status": status, "call_id": call_id, "lead_id": "1"}


class HangupTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.actor = models.User(name="Agent", email="c@x.test", emp_code="TC001", branch="Vizag", role="telecaller", is_active=True)
        self.db.add(self.actor); self.db.flush()
        self.conn = models.DialerConnection(kind="vicidial", name="T", api_key="k", base_url="https://dialer.test", branch="Vizag",
                                            enabled=True, capabilities={"vici_user": "api", "vici_pass": "pw", "agent_map": {"TC001": "8001"}})
        self.db.add(self.conn); self.db.commit()
        app = FastAPI(); app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[get_current_user] = lambda: self.actor
        self.c = TestClient(app)
        integrations._hangup_sleep = lambda s: None
        self.api_calls = []

    def tearDown(self):
        integrations._hangup_sleep = None
        vicidial_ami._transport = None

    def run_hangup(self, statuses, api_ok=True):
        seq = list(statuses)

        def status(conn, agent):
            return seq.pop(0) if len(seq) > 1 else seq[0]

        def agent_api(conn, agent, fn, value, **k):
            self.api_calls.append((agent, fn, value))
            return (api_ok, "SUCCESS: external_hangup function set - 1|8001" if api_ok else "ERROR: agent_user is not logged in")
        with patch("app.vicidial_live.read_agent_status", side_effect=status), patch("app.vicidial_live.agent_api", side_effect=agent_api):
            return self.c.post("/api/integration/vicidial/my-hangup", json={"case_id": 1})

    def test_answered_call_ends_via_api(self):
        r = self.run_hangup([st(), st(), st("DISPO", "")]).json()
        self.assertTrue(r["ended"]); self.assertEqual(r["method"], "api")
        self.assertEqual(self.api_calls[0], ("8001", "external_hangup", "1"))

    def test_ringing_call_ignored_without_ami_is_reported_not_faked(self):
        r = self.run_hangup([st()]).json()               # stays INCALL with the same call id
        self.assertIs(r["ended"], False)
        self.assertTrue(r["pending"]); self.assertTrue(r["watching"]); self.assertNotIn("warning", r)   # no scary error, keeps hanging up

    def dispo(self, statuses, **body):
        seq = list(statuses)
        sent = []
        with patch("app.vicidial_live.read_agent_status", side_effect=lambda c, a: seq.pop(0) if len(seq) > 1 else seq[0]), \
             patch("app.vicidial_live.agent_api", side_effect=lambda c, a, f, v, **k: sent.append((f, v)) or (True, "SUCCESS")), \
             patch("app.vicidial_live.resume_ready_later"):
            r = self.c.post("/api/integration/vicidial/my-dispo", json={"disposition": "RTP", **body}).json()
        return r, sent

    def test_save_and_end_dispositions_live_call(self):
        r, sent = self.dispo([st("DISPO", "")], was_live=True, call_id="M1109000000000012345")
        self.assertTrue(r["ok"]); self.assertNotIn("warning", r)
        self.assertEqual(sent[0], ("external_status", "NI"))

    def test_save_and_end_returns_at_once_and_keeps_hanging_up(self):
        r, sent = self.dispo([st()], was_live=True, call_id="M1109000000000012345")
        self.assertTrue(r["ok"]); self.assertTrue(r["watching"]); self.assertEqual(len(sent), 1)    # one ViciDial call, no waiting loop

    def test_keep_hanging_up_resends_until_call_gone(self):
        from app import vicidial_live
        seq = [st(), st(), st("DISPO", "")]
        sent = []
        with patch("app.vicidial_live.read_agent_status", side_effect=lambda c, a: seq.pop(0) if len(seq) > 1 else seq[0]), \
             patch("app.vicidial_live.agent_api", side_effect=lambda c, a, f, v, **k: sent.append(f) or (True, "SUCCESS")):
            self.assertTrue(vicidial_live.keep_hanging_up(self.conn, "8001", "M1109000000000012345", every=0.01, for_s=2))
            self.assertFalse(vicidial_live.keep_hanging_up(self.conn, "8001", "M1109000000000012345"))   # one watcher per call
            import time; time.sleep(0.5)
        self.assertEqual(sent, ["external_hangup", "external_hangup"])      # re-sent while ringing, stopped once ended

    def test_ringing_call_ended_via_ami_only_that_call(self):
        caps = dict(self.conn.capabilities); caps.update(ami_host="10.0.0.2", ami_user="riq", ami_secret="s")
        self.conn.capabilities = caps; self.db.commit()
        seen = []
        vicidial_ami._transport = lambda h, p, u, s, cid: (seen.append(cid) or ["SIP/carrier-0000001a"])
        r = self.run_hangup([st()]).json()
        self.assertTrue(r["ended"]); self.assertEqual(r["method"], "ami")
        self.assertEqual(seen, ["M1109000000000012345"])

    def test_api_refused_and_no_fallback_is_an_error(self):
        self.assertEqual(self.run_hangup([st()], api_ok=False).status_code, 502)

    def test_ami_parser_matches_call_id(self):
        raw = (b"Event: CoreShowChannel\r\nChannel: SIP/8001-00000001\r\nCallerIDName: 8001\r\n\r\n"
               b"Event: CoreShowChannel\r\nChannel: SIP/carrier-0000001a\r\nCallerIDName: M1109000000000012345\r\n\r\n")
        blocks = vicidial_ami._blocks(raw)
        hits = [b["Channel"] for b in blocks if "M1109000000000012345" in (b.get("CallerIDName", ""),)]
        self.assertEqual(hits, ["SIP/carrier-0000001a"])          # never the agent's own phone

    def test_secret_not_returned(self):
        caps = dict(self.conn.capabilities); caps.update(ami_secret="topsecret")
        self.conn.capabilities = caps; self.db.commit()
        out = integrations._conn_out(self.conn)
        self.assertNotIn("topsecret", str(out)); self.assertTrue(out["capabilities"]["ami_secret_set"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
