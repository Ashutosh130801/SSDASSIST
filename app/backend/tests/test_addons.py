"""🧩 Add-ons: compliance, payment links, outreach, settlement, smart allocation, notices, analytics, billing,
skip tracing, open API & webhooks. Isolated sqlite; external providers faked.

Run from app/backend:  python -B tests/test_addons.py
"""
import hashlib
import hmac
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_temp = tempfile.TemporaryDirectory(prefix="addons-test-")
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(_temp.name) / "addons.db")
os.environ["RAZORPAY_WEBHOOK_SECRET"] = "whtest"
os.environ["UPI_VPA"] = "ssd@upi"
os.chdir(_temp.name)

from fastapi.testclient import TestClient
from openpyxl import Workbook

from app import models, webhooks_out
from app import services as svc
from app.config import get_settings
from app.database import SessionLocal
from app.deps import get_current_user
from app.main import app
from app.routers import compliance, outreach, paylinks
from app.routers.cases import _current_period, _last_period

get_settings.cache_clear() if hasattr(get_settings, "cache_clear") else None


class AddonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db = SessionLocal()
        U = lambda n, e, r, **k: models.User(name=n, email=e, role=r, is_active=True, **k)
        cls.users = [U("Admin", "a@x", "admin"), U("Mgr", "m@x", "manager", branch="VIZAG"), U("TL", "t@x", "teamlead"),
                     U("Ravi FOS", "f@x", "fos", branch="VIZAG", emp_code="F1"), U("Sita FOS", "f2@x", "fos", branch="VIZAG", emp_code="F2"),
                     U("Caller", "c@x", "telecaller", branch="VIZAG", emp_code="C1")]
        db.add_all(cls.users); db.commit()
        cls.id = {u.email: u.id for u in db.query(models.User)}
        per, last = _current_period(), _last_period()
        close = date.today() + timedelta(days=3)
        mk = lambda **k: models.Case(period=per, bank="AXIS", product="X", bucket="2 BKT", paid_status="UNPAID", received_amount=0, **k)
        db.add_all([
            mk(customer_name="Anil Kumar", account_no="AC100001", phone="9876543210", pending_amount=20000, total_outstanding=20000,
               assigned_fos_id=cls.id["f@x"], assigned_caller_id=cls.id["c@x"], address="1 Main Rd", pincode="530001", branch="VIZAG",
               latitude=17.70, longitude=83.30, close_date=close, disposition="RNR"),
            mk(customer_name="Bina Rao", account_no="AC100002", phone="9000000002", pending_amount=50000, total_outstanding=50000,
               address="2 Beach Rd", pincode="530002", branch="VIZAG", latitude=17.72, longitude=83.31),
            mk(customer_name="Chand Das", account_no="AC100003", phone="9000000003", pending_amount=8000, total_outstanding=8000,
               assigned_fos_id=cls.id["f2@x"], address="3 Hill Rd", branch="VIZAG", latitude=17.90, longitude=83.40),
            models.Case(period=last, bank="AXIS", product="X", bucket="3 BKT", customer_name="Anil Kumar", account_no="AC100001",
                        phone="9876543210", alt_phone="9111111111", address="Old house, Gajuwaka", pincode="530001", paid_status="UNPAID",
                        assigned_fos_id=cls.id["f@x"]),
            models.Case(period=per, bank="ICICI", product="PL", customer_name="Anil Kumar", account_no="IC9", phone="9876543210",
                        new_phone="9222222222", pending_amount=1000, paid_status="UNPAID"),
        ])
        db.add(models.LocationPing(officer_id=cls.id["f2@x"], latitude=17.72, longitude=83.31))
        db.commit()
        cls.case = {c.account_no + (c.period or ""): c.id for c in db.query(models.Case)}
        cls.A = cls.case["AC100001" + per]; cls.B = cls.case["AC100002" + per]; cls.C = cls.case["AC100003" + per]
        db.close()
        cls.c = TestClient(app)

    def as_(self, email):
        db = SessionLocal()
        u = db.get(models.User, self.id[email])
        app.dependency_overrides[get_current_user] = lambda: u
        return u

    def on(self, key, settings=None):
        self.as_("a@x")
        r = self.c.put(f"/api/services/{key}", json={"enabled": True, **({"settings": settings} if settings else {})})
        self.assertEqual(r.status_code, 200, r.text)

    # ───────── services
    def test_00_addons_default_off_and_gated(self):
        self.as_("a@x")
        lst = {s["key"]: s for s in self.c.get("/api/services").json()}
        self.assertTrue(lst["ai_assist"]["enabled"]); self.assertFalse(lst["billing"]["enabled"])
        self.assertEqual(self.c.get("/api/billing/rates").status_code, 423)
        self.assertEqual(self.c.get("/pay/whatever").status_code, 423)

    # ───────── compliance
    def test_compliance(self):
        self.on("compliance", {"hours_from": "00:00", "hours_to": "23:59", "max_calls_per_day": 2, "block_uncertified": True})
        self.as_("c@x")
        r = self.c.get(f"/api/compliance/check/{self.A}").json()
        self.assertFalse(r["ok"]); self.assertIn("certificate", " ".join(r["reasons"]))
        self.as_("a@x")
        self.assertEqual(self.c.post("/api/compliance/certifications", json={"user_id": self.id["c@x"], "valid_until": "2099-01-01"}).status_code, 200)
        self.as_("c@x")
        self.assertTrue(self.c.get(f"/api/compliance/check/{self.A}").json()["ok"])
        for _ in range(3):
            self.assertEqual(self.c.post("/api/calls", json={"case_id": self.A, "disposition": "RNR"}).status_code, 200)
        r = self.c.get(f"/api/compliance/check/{self.A}").json()
        self.assertFalse(r["ok"]); self.assertIn("limit 2", r["reasons"][0])
        self.assertEqual(self.c.post("/api/integration/click-to-call", json={"case_id": self.A}).status_code in (403, 404), True)
        self.as_("a@x")
        s = self.c.get("/api/compliance/summary").json()
        self.assertTrue(any(e["action"] == "compliance.violation" for e in s["events"]))   # 3rd call flagged
        # hours rule
        self.on("compliance", {"hours_from": "00:00", "hours_to": "00:01", "block_uncertified": False, "max_calls_per_day": 0})
        self.as_("c@x")
        self.assertIn("hours", self.c.get(f"/api/compliance/check/{self.A}").json()["reasons"][0])
        # DPDP request + erase guard (open account can't be erased)
        self.as_("a@x")
        rid = self.c.post("/api/compliance/requests", json={"kind": "erasure", "requester": "Anil", "case_id": self.A}).json()["id"]
        r = self.c.post(f"/api/compliance/requests/{rid}/close", json={"status": "done", "erase": True, "confirm": "ERASE"})
        self.assertEqual(r.status_code, 400)
        self.on("compliance", {"hours_from": "00:00", "hours_to": "23:59"})
        db = SessionLocal(); svc.save(db, "compliance", False, None); db.commit(); db.close()

    # ───────── payment links
    def test_paylinks_webhook_and_statement(self):
        self.on("payments", {"provider": "razorpay", "min_amount": 100})
        calls = []
        def fake(method, path, body):
            calls.append((method, path, body)); return {"id": "plink_1", "short_url": "https://rzp.io/i/x"}
        paylinks._transport = fake
        self.as_("c@x")
        r = self.c.post("/api/paylinks", json={"case_id": self.A, "amount": 5000})
        self.assertEqual(r.status_code, 200, r.text)
        link = r.json(); self.assertEqual(calls[0][2]["amount"], 500000)
        self.assertEqual(self.c.post("/api/paylinks", json={"case_id": self.C}).status_code, 404)   # not his case
        page = self.c.get(f"/pay/{link['token']}")
        self.assertEqual(page.status_code, 200); self.assertIn("rzp.io", page.text); self.assertNotIn("9876543210", page.text)
        ev = {"event": "payment_link.paid", "payload": {"payment_link": {"entity": {"id": "plink_1"}},
                                                        "payment": {"entity": {"id": "pay_1", "amount": 500000, "acquirer_data": {"rrn": "123456789012"}}}}}
        raw = json.dumps(ev).encode()
        bad = self.c.post("/api/paylinks/webhook", content=raw, headers={"X-Razorpay-Signature": "nope"})
        self.assertEqual(bad.status_code, 400)
        sig = hmac.new(b"whtest", raw, hashlib.sha256).hexdigest()
        self.assertTrue(self.c.post("/api/paylinks/webhook", content=raw, headers={"X-Razorpay-Signature": sig}).json()["applied"])
        self.assertFalse(self.c.post("/api/paylinks/webhook", content=raw, headers={"X-Razorpay-Signature": sig}).json()["applied"])
        db = SessionLocal(); case = db.get(models.Case, self.A)
        self.assertEqual(float(case.received_amount), 5000.0); db.close()
        # manual UPI + statement reconciliation (+ customer UTR)
        self.on("payments", {"provider": "manual_upi"})
        self.as_("c@x")
        l2 = self.c.post("/api/paylinks", json={"case_id": self.A, "amount": 2000}).json()
        self.assertIn("upi://pay", self.c.get(f"/pay/{l2['token']}").text)
        self.c.post(f"/pay/{l2['token']}/utr", data={"utr": "998877665544"})
        csv = "Date,Narration,Ref No,Credit\n01-01-2026,UPI/ANIL/xyz,998877665544,2000\n01-01-2026,NEFT other,555,700\n"
        self.as_("m@x")
        pv = self.c.post("/api/paylinks/reconcile/preview", files={"file": ("st.csv", csv.encode(), "text/csv")}).json()
        self.assertEqual(pv["matched"], 1)
        self.assertEqual(self.c.post("/api/paylinks/reconcile/apply", json={"lines": pv["lines"]}).json()["applied"], 1)
        self.assertEqual(self.c.post("/api/paylinks/reconcile/apply", json={"lines": pv["lines"]}).json()["applied"], 0)  # once only
        db = SessionLocal(); self.assertEqual(float(db.get(models.Case, self.A).received_amount), 7000.0); db.close()
        paylinks._transport = None

    # ───────── outreach
    def test_outreach(self):
        self.on("outreach", {"daily_cap": 1})
        self.as_("m@x")
        bad = self.c.post("/api/outreach/journeys", json={"name": "x", "trigger": "close", "steps": [{"offset": 3, "channel": "fax", "text": "hi"}]})
        self.assertEqual(bad.status_code, 400)
        j = {"name": "Before close", "trigger": "close", "filters": {"bank": "AXIS"},
             "steps": [{"offset": 3, "channel": "whatsapp", "text": "Dear {name}, ₹{amount} due on {bank} a/c {account_last4}"},
                       {"offset": 3, "channel": "sms", "text": "second same-day message"}]}
        self.assertEqual(self.c.post("/api/outreach/journeys", json=j).status_code, 200)
        r = self.c.post("/api/outreach/run", json={}).json()
        self.assertEqual(r["created"], 2)
        msgs = self.c.get("/api/outreach/messages").json()
        st = sorted(m["status"] for m in msgs)
        self.assertEqual(st, ["manual", "skipped"])                     # no provider → manual; daily cap 1 → second skipped
        man = [m for m in msgs if m["status"] == "manual"][0]
        self.assertIn("Dear Anil", man["text"]); self.assertIn("a/c 0001", man["text"])
        self.assertEqual(self.c.post("/api/outreach/run", json={}).json()["created"], 0)    # never twice
        self.assertEqual(self.c.post(f"/api/outreach/messages/{man['id']}/done").status_code, 200)
        self.as_("f@x")
        self.assertEqual(self.c.get("/api/outreach/journeys").status_code, 403)

    # ───────── settlement
    def test_settlement(self):
        self.on("settlement", {"caller_max_waiver_pct": 5, "teamlead_max_waiver_pct": 10, "manager_max_waiver_pct": 30})
        db = SessionLocal(); c = db.get(models.Case, self.C); c.received_amount = 0; c.pending_amount = 8000; db.commit(); db.close()
        self.as_("f2@x")
        r = self.c.post("/api/settlements", json={"case_id": self.C, "offer_amount": 6000, "reason": "job loss"})   # 25% waiver
        self.assertEqual(r.status_code, 200, r.text); r = r.json()
        self.assertEqual(r["status"], "pending"); self.assertEqual(r["needs_role"], "manager")
        self.assertEqual(self.c.post("/api/settlements", json={"case_id": self.C, "offer_amount": 7000}).status_code, 400)  # one open
        self.assertEqual(self.c.post(f"/api/settlements/{r['id']}/decide", json={"approve": True}).status_code, 403)
        self.as_("m@x")
        self.assertEqual(self.c.post(f"/api/settlements/{r['id']}/decide", json={"approve": True}).status_code, 200)
        pdf = self.c.get(f"/api/settlements/{r['id']}/letter.pdf")
        self.assertEqual(pdf.status_code, 200); self.assertTrue(pdf.content.startswith(b"%PDF"))
        self.assertEqual(self.c.post(f"/api/settlements/{r['id']}/status", json={"paid_index": 0}).json()["status"], "completed")
        # bad instalments
        self.assertEqual(self.c.post("/api/settlements", json={"case_id": self.B, "offer_amount": 40000,
                                                               "installments": [{"due": "2030-01-01", "amount": 100}]}).status_code, 400)

    # ───────── smart allocation + route
    def test_smart(self):
        self.on("smart_allocation", {"fos_capacity": 5})
        self.as_("m@x")
        sc = self.c.get("/api/smart/scores").json()
        self.assertTrue(sc["rows"]); self.assertIn("score", sc["rows"][0])
        pv = self.c.post("/api/smart/allocate/preview", json={"kind": "fos"}).json()
        b = [s for s in pv["suggestions"] if s["case_id"] == self.B][0]
        self.assertEqual(b["user"], "Sita FOS")                       # her last GPS ping is right next to case B
        self.assertEqual(self.c.post("/api/smart/allocate/apply", json={"kind": "fos", "items": [b]}).json()["applied"], 1)
        db = SessionLocal(); self.assertEqual(db.get(models.Case, self.B).assigned_fos_id, self.id["f2@x"]); db.close()
        self.as_("f2@x")
        rt = self.c.get("/api/smart/route").json()
        self.assertEqual({s["case_id"] for s in rt["stops"]}, {self.B, self.C})
        self.assertEqual(rt["stops"][0]["case_id"], self.B)          # nearest first from her location
        self.assertEqual(self.c.post("/api/smart/allocate/preview", json={"kind": "fos"}).status_code, 403)

    # ───────── legal notices
    def test_notices(self):
        self.on("legal_notices", {"signatory": "Adv. K. Rao", "reply_days": 15})
        self.as_("a@x")
        self.assertEqual(self.c.post("/api/notices/batches", json={"kind": "demand"}).status_code, 400)   # no selection
        b = self.c.post("/api/notices/batches", json={"kind": "demand", "case_ids": [self.A, self.C]}).json()
        self.assertEqual(b["count"], 2)
        pdf = self.c.get(f"/api/notices/batches/{b['id']}/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        det = self.c.get(f"/api/notices/batches/{b['id']}").json()
        wb = Workbook(); ws = wb.active; ws.append(["Ref No", "Status", "Mode", "Tracking No"])
        ws.append([det["notices"][0]["ref_no"], "dispatched", "speed post", "EE123IN"]); ws.append(["LN/BAD", "delivered"])
        buf = io.BytesIO(); wb.save(buf)
        r = self.c.post(f"/api/notices/batches/{b['id']}/tracking", files={"file": ("t.xlsx", buf.getvalue())}).json()
        self.assertEqual(r["updated"], 1); self.assertEqual(len(r["errors"]), 1)
        det = self.c.get(f"/api/notices/batches/{b['id']}").json()
        self.assertEqual(det["notices"][0]["tracking_no"], "EE123IN"); self.assertEqual(det["notices"][0]["mode"], "speed_post")

    # ───────── analytics
    def test_insights(self):
        self.on("analytics")
        self.as_("m@x")
        r = self.c.get("/api/insights").json()
        self.assertIn("forecast", r); self.assertTrue(r["resolution"])
        self.assertEqual(r["rolls"]["counts"].get("rolled_back"), 1)      # AC100001: 3 BKT → 2 BKT
        self.as_("f@x")
        self.assertEqual(self.c.get("/api/insights").status_code, 403)

    # ───────── billing
    def test_billing(self):
        self.on("billing", {"gst_rate": 18, "invoice_prefix": "SSD"})
        self.as_("a@x")
        self.assertEqual(self.c.post("/api/billing/rates", json={"bank": "AXIS", "basis": "percent", "rate": 10}).status_code, 200)
        self.assertEqual(self.c.post("/api/billing/rates", json={"bank": "AXIS", "basis": "fixed", "rate": 1000}).status_code, 200)
        db = SessionLocal(); c = db.get(models.Case, self.C); c.received_amount = 5000; db.commit(); db.close()
        per = _current_period()
        inv = self.c.post("/api/billing/invoices", json={"bank": "AXIS", "period": per}).json()
        self.assertGreater(inv["subtotal"], 1000); self.assertAlmostEqual(inv["gst"], round(inv["subtotal"] * 0.18, 2), places=2)
        self.assertEqual(self.c.post("/api/billing/invoices", json={"bank": "AXIS", "period": per}).status_code, 400)
        iss = self.c.post(f"/api/billing/invoices/{inv['id']}/status", json={"status": "issued"}).json()
        self.assertTrue(iss["number"].startswith("SSD/"))
        self.assertEqual(self.c.put(f"/api/billing/invoices/{inv['id']}", json={"bill_to": "x"}).status_code, 400)
        self.assertTrue(self.c.get(f"/api/billing/invoices/{inv['id']}.pdf").content.startswith(b"%PDF"))
        self.as_("m@x")
        self.assertEqual(self.c.get("/api/billing/rates").status_code, 403)

    # ───────── skip tracing
    def test_skiptrace(self):
        self.on("skip_tracing")
        self.as_("c@x")
        r = self.c.get(f"/api/skiptrace/case/{self.A}").json()
        ph = {p["value"] for p in r["phones"]}
        self.assertIn("9111111111", ph); self.assertIn("9222222222", ph)
        self.assertTrue(any("Gajuwaka" in a["value"] for a in r["addresses"]))
        self.assertEqual(self.c.post(f"/api/skiptrace/case/{self.A}/apply", json={"phone": "9999999999"}).status_code, 400)
        self.assertEqual(self.c.post(f"/api/skiptrace/case/{self.A}/apply", json={"phone": "9111111111"}).status_code, 200)
        self.assertEqual(self.c.get(f"/api/skiptrace/case/{self.C}").status_code, 404)        # not his case

    # ───────── open API + webhooks
    def test_open_api(self):
        self.on("open_api")
        self.as_("a@x")
        self.assertEqual(self.c.post("/api/apikeys/webhooks", json={"url": "http://127.0.0.1/x"}).status_code, 400)
        self.assertEqual(self.c.post("/api/apikeys/webhooks", json={"url": "https://10.0.0.5/x"}).status_code, 400)
        db = SessionLocal()
        db.add(models.Webhook(url="https://example.com/hook", events=["payment.received"], secret="s3", active=True)); db.commit(); db.close()
        k = self.c.post("/api/apikeys", json={"name": "Axis feed", "scopes": ["cases:read", "payments:write"], "banks": ["AXIS"]}).json()["key"]
        app.dependency_overrides.pop(get_current_user, None)
        H = {"Authorization": f"Bearer {k}"}
        self.assertEqual(self.c.get("/api/open/v1/cases").status_code, 401)
        cs = self.c.get("/api/open/v1/cases", headers=H).json()["cases"]
        self.assertTrue(cs and all(c["bank"] == "AXIS" for c in cs)); self.assertTrue(all("XXXX" in (c["phone"] or "XXXX") for c in cs))
        self.assertEqual(self.c.get("/api/open/v1/events", headers=H).status_code, 403)
        body = {"account_no": "AC100003", "amount": 500, "reference": "UTR1"}
        self.assertTrue(self.c.post("/api/open/v1/payments", json=body, headers=H).json()["ok"])
        self.assertTrue(self.c.post("/api/open/v1/payments", json=body, headers=H).json()["duplicate"])
        sent = []
        webhooks_out._transport = lambda url, b, h: (sent.append((url, b, h)) or 200)
        db = SessionLocal(); webhooks_out.deliver_pending(db); db.close()
        self.assertTrue(sent)
        url, b, h = sent[-1]
        self.assertEqual(h["X-RecoverIQ-Signature"], "sha256=" + hmac.new(b"s3", b, hashlib.sha256).hexdigest())
        self.assertEqual(json.loads(b)["event"], "payment.received")
        webhooks_out._transport = None


if __name__ == "__main__":
    unittest.main(verbosity=2)
