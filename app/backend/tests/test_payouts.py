"""Payout (RazorpayX) safety tests against a fake gateway — never touches the network or the live DB.

Run from app/backend:  .venv/Scripts/python.exe -B tests/test_payouts.py
"""
import hashlib
import hmac
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_temp = tempfile.TemporaryDirectory(prefix="payout-test-")
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(_temp.name) / "unused.db")
os.environ["RAZORPAYX_KEY_ID"] = "rzp_test_ABCDEFGHIJKLMN"
os.environ["RAZORPAYX_KEY_SECRET"] = "testsecret"
os.environ["RAZORPAYX_ACCOUNT_NUMBER"] = "2323230000001234"
os.environ["RAZORPAYX_WEBHOOK_SECRET"] = "whsec"

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models, razorpayx as rx
from app.config import get_settings
from app.database import Base, get_db
from app.deps import get_current_user
from app.routers import payouts as payouts_mod
from app.routers.payouts import router
from app.security import hash_password

get_settings.cache_clear()


class FakeGateway:
    def __init__(self):
        self.payouts = {}        # idempotency key -> payout
        self.calls = []
        self.fail_next = None    # "timeout" | "400"

    def __call__(self, req: httpx.Request):
        self.calls.append((req.method, req.url.path))
        if self.fail_next == "timeout":
            self.fail_next = None
            raise httpx.ReadTimeout("slow", request=req)
        p = req.url.path
        if p.endswith("/contacts"):
            return httpx.Response(200, json={"id": "cont_1"})
        if p.endswith("/fund_accounts"):
            return httpx.Response(200, json={"id": "fa_" + json.loads(req.content)["bank_account"]["account_number"][-4:]})
        if p.endswith("/payouts") and req.method == "GET":
            return httpx.Response(200, json={"items": []})
        if p.endswith("/payouts"):
            if self.fail_next == "400":
                self.fail_next = None
                return httpx.Response(400, json={"error": {"description": "Invalid IFSC"}})
            key = req.headers["X-Payout-Idempotency"]
            body = json.loads(req.content)
            if key not in self.payouts:      # real RazorpayX: same key → same payout
                self.payouts[key] = {"id": f"pout_{len(self.payouts) + 1}", "status": "processing",
                                     "amount": body["amount"], "reference_id": body["reference_id"], "utr": None}
            return httpx.Response(200, json=self.payouts[key])
        if "/payouts/" in p:
            pid = p.rsplit("/", 1)[1]
            for v in self.payouts.values():
                if v["id"] == pid:
                    return httpx.Response(200, json={**v, "status": "processed", "utr": "UTR" + pid})
        return httpx.Response(404, json={})


class PayoutTests(unittest.TestCase):
    def setUp(self):
        payouts_mod.SECTION_LOCKED = False      # the safety tests exercise the unlocked logic
        self.gw = FakeGateway()
        rx._transport = httpx.MockTransport(self.gw)
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.admin = models.User(name="Admin", email="a@x.test", role="admin", is_active=True,
                                 hashed_password=hash_password("pw123456"))
        self.e1 = models.User(name="Ravi Kumar", email="r@x.test", role="fo", is_active=True, emp_code="FO047",
                              bank_account="918010012345671", ifsc_code="UTIB0001234", bank_holder="RAVI KUMAR")
        self.e2 = models.User(name="Lakshmi", email="l@x.test", role="telecaller", is_active=True, emp_code="TC012",
                              bank_account="50100123456789", ifsc_code="HDFC0001234", bank_holder="LAKSHMI")
        self.e3 = models.User(name="No Bank", email="n@x.test", role="telecaller", is_active=True)
        self.db.add_all([self.admin, self.e1, self.e2, self.e3])
        self.db.commit()
        self.actor = self.admin
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: self.actor
        app.dependency_overrides[get_db] = lambda: self.db
        self.c = TestClient(app)

    def tearDown(self):
        rx._transport = None
        self.c.close()
        self.db.close()

    def batch(self, items=None):
        r = self.c.post("/api/payouts/batches", json={"period": "2026-11", "items": items or [
            {"user_id": self.e1.id, "amount": "18305.00"}, {"user_id": self.e2.id, "amount": 14096.5, "mode": "IMPS"}]})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def approve(self, b, total=None, pw="pw123456"):
        return self.c.post(f"/api/payouts/batches/{b['id']}/approve",
                           json={"password": pw, "confirm_total": total if total is not None else b["total"]})

    def hook(self, payload, eid="evt_1", secret="whsec"):
        raw = json.dumps(payload).encode()
        sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        return self.c.post("/api/payouts/webhook/razorpayx", content=raw,
                           headers={"X-Razorpay-Signature": sig, "X-Razorpay-Event-Id": eid, "Content-Type": "application/json"})

    # ───────────────────────────────────────── tests
    def test_section_locked_blocks_everything(self):
        payouts_mod.SECTION_LOCKED = True
        try:
            self.assertEqual(self.c.get("/api/payouts/gateway").status_code, 423)
            self.assertEqual(self.c.post("/api/payouts/batches", json={"period": "2026-11", "items": []}).status_code, 423)
            self.assertEqual(self.hook({"event": "payout.processed"}).status_code, 423)
        finally:
            payouts_mod.SECTION_LOCKED = False
    def test_non_admin_blocked(self):
        for role in ("headoffice", "hr", "techsupport", "it_support_view"):
            self.actor = models.User(id=999, name="x", email="x", role=role, is_active=True)
            self.assertEqual(self.c.get("/api/payouts/batches").status_code, 403, role)

    def test_validation(self):
        r = self.c.post("/api/payouts/batches", json={"period": "2026-11", "items": [
            {"user_id": self.e3.id, "amount": 100}, {"user_id": self.e1.id, "amount": "10.123"}]})
        self.assertEqual(r.status_code, 400)
        r = self.c.post("/api/payouts/batches", json={"period": "2026-11", "items": [{"user_id": self.e1.id, "amount": 9999999}]})
        self.assertEqual(r.status_code, 400)
        r = self.c.post("/api/payouts/batches", json={"period": "2026-11", "items": [{"user_id": self.e1.id, "amount": 1},
                                                                                    {"user_id": self.e1.id, "amount": 1}]})
        self.assertIn("twice", r.text)

    def test_amounts_in_paise(self):
        b = self.batch()
        self.assertEqual(b["total"], 32401.5)
        self.assertEqual(self.db.query(models.PayoutBatch).get(b["id"]).total_paise, 3240150)

    def test_cannot_send_unapproved(self):
        b = self.batch()
        self.assertEqual(self.c.post(f"/api/payouts/batches/{b['id']}/send").status_code, 400)
        self.assertFalse(any(p.endswith("/payouts") and m == "POST" for m, p in self.gw.calls))

    def test_approval_needs_password_and_exact_total(self):
        b = self.batch()
        self.assertEqual(self.approve(b, pw="wrong").status_code, 401)
        self.assertEqual(self.approve(b, total=32401).status_code, 400)
        self.assertEqual(self.approve(b).status_code, 200)
        self.assertEqual(self.approve(b).status_code, 400)       # can't approve twice

    def test_send_and_double_send_pays_once(self):
        b = self.batch(); self.approve(b)
        r = self.c.post(f"/api/payouts/batches/{b['id']}/send").json()
        self.assertEqual(r["status"], "sending")
        self.assertEqual(len(self.gw.payouts), 2)
        self.c.post(f"/api/payouts/batches/{b['id']}/send")      # double click / resend
        self.assertEqual(len(self.gw.payouts), 2)
        posts = [1 for m, p in self.gw.calls if m == "POST" and p.endswith("/payouts")]
        self.assertEqual(len(posts), 2)

    def test_timeout_then_resend_same_key(self):
        b = self.batch([{"user_id": self.e1.id, "amount": 100}]); self.approve(b)
        key = self.db.query(models.PayoutItem).first().idempotency_key
        # first payout call times out (after contact + fund account succeed)
        orig = self.gw.__call__

        def flaky(req, _n=[0]):
            if req.url.path.endswith("/payouts") and req.method == "POST" and _n[0] == 0:
                _n[0] += 1
                orig(req)                      # the gateway DID create it…
                raise httpx.ReadTimeout("lost reply", request=req)   # …but we never heard back
            return orig(req)
        rx._transport = httpx.MockTransport(flaky)
        r = self.c.post(f"/api/payouts/batches/{b['id']}/send").json()
        self.assertEqual(r["items"][0]["status"], "pending")
        self.c.post(f"/api/payouts/batches/{b['id']}/send")
        self.assertEqual(len(self.gw.payouts), 1)                 # still ONE payout
        self.assertEqual(self.db.query(models.PayoutItem).first().idempotency_key, key)

    def test_bank_change_after_approval_blocks(self):
        b = self.batch([{"user_id": self.e1.id, "amount": 100}]); self.approve(b)
        self.e1.bank_account = "111122223333"; self.db.commit()
        r = self.c.post(f"/api/payouts/batches/{b['id']}/send").json()
        self.assertEqual(r["items"][0]["status"], "blocked")
        self.assertEqual(len(self.gw.payouts), 0)

    def test_webhook_signature_dedupe_and_terminal(self):
        b = self.batch([{"user_id": self.e1.id, "amount": 100}]); self.approve(b)
        self.c.post(f"/api/payouts/batches/{b['id']}/send")
        it = self.db.query(models.PayoutItem).first()
        ent = {"id": it.payout_id, "status": "processed", "amount": 10000, "utr": "AXISN123", "reference_id": it.reference_id}
        bad = self.hook({"event": "payout.processed", "payload": {"payout": {"entity": ent}}}, secret="wrong")
        self.assertEqual(bad.status_code, 401)
        self.assertEqual(self.hook({"event": "payout.processed", "payload": {"payout": {"entity": ent}}}).status_code, 200)
        self.db.refresh(it)
        self.assertEqual((it.status, it.utr), ("processed", "AXISN123"))
        self.assertTrue(self.hook({"event": "payout.processed", "payload": {"payout": {"entity": ent}}}).json()["duplicate"])
        # late out-of-order "processing" must not undo processed
        self.hook({"event": "payout.updated", "payload": {"payout": {"entity": {**ent, "status": "processing"}}}}, eid="evt_2")
        self.db.refresh(it); self.assertEqual(it.status, "processed")
        # amount mismatch is ignored
        self.hook({"event": "payout.reversed", "payload": {"payout": {"entity": {**ent, "status": "reversed", "amount": 1}}}}, eid="evt_3")
        self.db.refresh(it); self.assertEqual(it.status, "processed")
        self.assertEqual(self.c.get(f"/api/payouts/batches/{b['id']}").json()["status"], "completed")

    def test_failed_then_retry_needs_password(self):
        b = self.batch([{"user_id": self.e1.id, "amount": 100}]); self.approve(b)
        self.gw.fail_next = "400"
        r = self.c.post(f"/api/payouts/batches/{b['id']}/send").json()
        self.assertEqual(r["items"][0]["status"], "failed")
        iid = r["items"][0]["id"]
        self.assertEqual(self.c.post(f"/api/payouts/items/{iid}/retry", json={"reason": "fixed ifsc", "password": "x"}).status_code, 401)
        r = self.c.post(f"/api/payouts/items/{iid}/retry", json={"reason": "fixed ifsc", "password": "pw123456"}).json()
        self.assertEqual(r["items"][0]["attempt"], 2)
        r = self.c.post(f"/api/payouts/batches/{b['id']}/send").json()
        self.assertEqual(len(self.gw.payouts), 1)
        # refresh pulls processed + UTR
        r = self.c.post(f"/api/payouts/batches/{b['id']}/refresh").json()
        self.assertEqual(r["items"][0]["status"], "processed"); self.assertTrue(r["items"][0]["utr"])

    def test_one_salary_per_period(self):
        b = self.batch([{"user_id": self.e1.id, "amount": 100}])
        r = self.c.post("/api/payouts/batches", json={"period": "2026-11", "items": [{"user_id": self.e1.id, "amount": 100}]})
        self.assertIn("already in another", r.text)
        self.c.post(f"/api/payouts/batches/{b['id']}/cancel", json={})
        self.batch([{"user_id": self.e1.id, "amount": 100}])          # allowed after cancel

    def test_live_key_refused(self):
        os.environ["RAZORPAYX_KEY_ID"] = "rzp_live_ABCDEFGHIJKLMN"; get_settings.cache_clear()
        try:
            self.assertFalse(rx.config_state()["configured"])
            r = self.c.post("/api/payouts/batches", json={"period": "2026-11", "items": [{"user_id": self.e1.id, "amount": 100}]})
            self.assertEqual(r.status_code, 400)
        finally:
            os.environ["RAZORPAYX_KEY_ID"] = "rzp_test_ABCDEFGHIJKLMN"; get_settings.cache_clear()


if __name__ == "__main__":
    unittest.main(verbosity=2)
