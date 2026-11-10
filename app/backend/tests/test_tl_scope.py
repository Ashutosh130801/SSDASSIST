"""Team-lead scoping: own members only, case-scoped performance with the split by lead, read-only
peer view for shared portfolios, write guard, and a team lead's Audit Log scope."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_t = tempfile.TemporaryDirectory(prefix="tlscope-")
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(_t.name) / "t.db")
os.chdir(_t.name)

from fastapi.testclient import TestClient

from app import audit, models
from app.database import SessionLocal
from app.deps import get_current_user
from app.main import app


def as_user(uid):
    app.dependency_overrides[get_current_user] = lambda: SessionLocal().get(models.User, uid)


class TLScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db = SessionLocal()
        A = models.User(name="Lead A", email="la@x", role="teamlead", is_active=True)
        B = models.User(name="Lead B", email="lb@x", role="teamlead", is_active=True)
        F = models.User(name="Shared Fos", email="f@x", role="fos", is_active=True)
        G = models.User(name="B Only Fos", email="g@x", role="fos", is_active=True)
        adm = models.User(name="Admin", email="ad@x", role="admin", is_active=True)
        db.add_all([A, B, F, G, adm]); db.flush()

        def case(i, tl, fos, bank="AXIS", product="CC", paid=False):
            return models.Case(customer_name=f"C{i}", account_no=f"AC{i}", bank=bank, product=product,
                               team_lead=tl, assigned_fos_id=fos, enr=1000, funding_amount=1000,
                               paid_status="PAID" if paid else "UNPAID", received_amount=1000 if paid else 0)
        a_cases = [case(i, "Lead A", F.id, paid=(i == 0)) for i in range(4)]
        b_cases = [case(10 + i, "Lead B", F.id) for i in range(2)]
        g_case = case(20, "Lead B", G.id)
        other = case(30, "Lead B", F.id, bank="ICICI", product="PL")     # a portfolio Lead A doesn't work
        db.add_all(a_cases + b_cases + [g_case, other]); db.flush()
        db.add(models.Visit(case_id=b_cases[0].id, officer_id=F.id, disposition="PTP"))
        db.add(models.Visit(case_id=a_cases[1].id, officer_id=F.id, disposition="RTP"))
        # audit: F works on a B case (A must NOT see), on an A case (A sees), and logs in (A sees)
        audit.record(db, F, "visit", b_cases[0], detail="visit on B case")
        audit.record(db, F, "visit", a_cases[1], detail="visit on A case")
        audit.record(db, F, "login", None, entity_type="user", detail="F logged in")
        bt = audit.Batch(db, adm, "reassign", "Re-allocation")
        for c in (a_cases[2], b_cases[1]):
            bt.record("reassign", c, field="assigned_fos_id", old="x", new="y")
        bt.close("x → y")
        db.commit()
        cls.ids = dict(A=A.id, B=B.id, F=F.id, G=G.id, adm=adm.id, a0=a_cases[0].id, b0=b_cases[0].id,
                       other=other.id)
        db.close()
        cls.c = TestClient(app)

    def test_performance_own_members_scoped_and_split(self):
        i = self.ids; as_user(i["A"])
        r = self.c.get(f"/api/mis/performance?emp_id={i['F']}&role=fos&month_bucket=all")
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["totals"]["count"], 4)                              # only Lead A's cases
        self.assertEqual([p["label"] for p in d["portfolios"]], ["AXIS CC"])  # ICICI PL hidden entirely
        sp = d["portfolios"][0]["split"]
        self.assertEqual(sp["total"], 6)
        me, other = sp["rows"]
        self.assertTrue(me["is_me"]); self.assertEqual((me["count"], me["paid"], me["visits"]), (4, 1, 1))
        self.assertEqual((other["lead"], other["count"], other["visits"]), ("Lead B", 2, 1))
        lb = d["portfolios"][0]["leaderboard"]
        self.assertEqual(sum(x["count"] for x in lb), 4)                        # leaderboard = own cases only
        # not a member of Lead A
        self.assertEqual(self.c.get(f"/api/mis/performance?emp_id={i['G']}&month_bucket=all").status_code, 403)
        self.assertEqual(self.c.get(f"/api/mis/employee-trends?user_id={i['G']}").status_code, 403)

    def test_peer_performance_read_only(self):
        i = self.ids; as_user(i["A"])
        r = self.c.get(f"/api/mis/performance?emp_id={i['G']}&month_bucket=all&peer_lead={i['B']}")
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertTrue(d["read_only"]); self.assertEqual(d["totals"]["count"], 1)
        # F on B's cases: only the shared portfolio (AXIS CC) counts, not ICICI PL
        d = self.c.get(f"/api/mis/performance?emp_id={i['F']}&month_bucket=all&peer_lead={i['B']}").json()
        self.assertEqual(d["totals"]["count"], 2)

    def test_peer_case_read_only_and_write_guard(self):
        i = self.ids; as_user(i["A"])
        r = self.c.get(f"/api/cases/{i['b0']}")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["read_only"]); self.assertEqual(r.json()["read_only_lead"], "Lead B")
        self.assertEqual(self.c.get(f"/api/cases/{i['b0']}/timeline").status_code, 200)
        self.assertFalse(self.c.get(f"/api/cases/{i['a0']}").json().get("read_only"))
        self.assertEqual(self.c.get(f"/api/cases/{i['other']}").status_code, 404)    # portfolio not shared
        w = self.c.post("/api/templates/log", json={"case_id": i["b0"], "text": "hi"})
        self.assertEqual(w.status_code, 403); self.assertIn("Read-only", w.json()["detail"])
        self.assertEqual(self.c.post("/api/templates/log", json={"case_id": i["a0"], "text": "hi"}).status_code, 200)
        as_user(i["adm"])
        acts = [x["action"] for x in self.c.get("/api/audit?limit=200").json()["items"]]
        self.assertIn("peer_view", acts)

    def test_branch_only_matters_for_location_specific_portfolio(self):
        db = SessionLocal()
        i = self.ids
        loc = models.ImportBatch(filename="vizag.xlsx", bank="HDFC", product="AL", branch="Vizag")
        db.add(loc); db.flush()
        # Lead A works HDFC AL only in Hyderabad (no location chosen at upload)
        db.add(models.Case(customer_name="A-hyd", account_no="H1", bank="HDFC", product="AL", branch="Hyderabad", team_lead="Lead A"))
        # Lead B: one case whose branch was filled by FOS/pincode, one from a Vizag-specific upload
        free = models.Case(customer_name="B-free", account_no="H2", bank="HDFC", product="AL", branch="Vizag", team_lead="Lead B")
        pinned = models.Case(customer_name="B-loc", account_no="H3", bank="HDFC", product="AL", branch="Vizag",
                             team_lead="Lead B", import_batch_id=loc.id)
        db.add_all([free, pinned]); db.commit()
        fid, pid = free.id, pinned.id; db.close()
        as_user(i["A"])
        r = self.c.get(f"/api/cases/{fid}")
        self.assertEqual(r.status_code, 200, r.text); self.assertTrue(r.json()["read_only"])   # branch ignored
        self.assertEqual(self.c.get(f"/api/cases/{pid}").status_code, 404)                     # Vizag-only portfolio

    def test_audit_scope_for_lead(self):
        i = self.ids; as_user(i["A"])
        items = self.c.get("/api/audit?limit=200").json()["items"]
        details = [x["detail"] for x in items]
        self.assertIn("visit on A case", details)
        self.assertIn("F logged in", details)
        self.assertNotIn("visit on B case", details)
        bulk = next(x for x in items if x["action"] == "bulk_reassign")
        full = self.c.get(f"/api/audit/{bulk['id']}").json()
        self.assertEqual(len(full["meta"]["items"]), 1)            # only Lead A's case in the popup
        self.assertIn("trimmed_note", full["meta"])
        as_user(i["adm"])
        self.assertEqual(len(self.c.get(f"/api/audit/{bulk['id']}").json()["meta"]["items"]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
