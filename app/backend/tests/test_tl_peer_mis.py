"""Team lead MIS: pick yourself (default) or another lead on the SAME portfolio (read-only, audited);
no 'All'; leads on other portfolios refused. Portfolios list is month-wise."""
import os, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_t = tempfile.TemporaryDirectory(prefix="tlpeermis-")
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(_t.name) / "t.db")
os.chdir(_t.name)

from fastapi.testclient import TestClient
from app import models
from app.database import SessionLocal
from app.deps import get_current_user
from app.main import app
from app.routers.cases import _current_period, _last_period


def as_user(uid):
    app.dependency_overrides[get_current_user] = lambda: SessionLocal().get(models.User, uid)


class PeerMis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db = SessionLocal()
        A = models.User(name="Lead A", email="a@x", emp_code="TL1", role="teamlead", is_active=True)
        B = models.User(name="Lead B", email="b@x", emp_code="TL2", role="teamlead", is_active=True)
        C = models.User(name="Lead C", email="c@x", emp_code="TL3", role="teamlead", is_active=True)
        db.add_all([A, B, C]); db.flush()
        cur, last = _current_period(), _last_period()
        def case(i, tl, bank="AXIS", product="CC", per=cur, paid=False):
            return models.Case(customer_name=f"C{i}", account_no=f"AC{i}", bank=bank, product=product, period=per,
                               team_lead=tl, enr=1000, funding_amount=1000,
                               paid_status="PAID" if paid else "UNPAID", received_amount=1000 if paid else 0)
        db.add_all([case(1, "Lead A"), case(2, "Lead A", per=last), case(3, "Lead B"), case(4, "Lead B"),
                    case(5, "Lead B", paid=True), case(6, "Lead C", bank="ICICI", product="PL")])
        db.commit()
        cls.ids = dict(A=A.id, B=B.id, C=C.id); cls.cur, cls.last = cur, last
        db.close(); cls.c = TestClient(app)

    def test_options_only_individual_leads_on_portfolio(self):
        as_user(self.ids["A"])
        o = self.c.get("/api/mis/tl-options?bank=AXIS&product=CC").json()
        self.assertEqual([x["name"] for x in o], ["Lead A", "Lead B"])      # me first, no 'All', no Lead C
        self.assertTrue(o[0]["is_me"])

    def test_default_is_own_mis_and_peer_is_read_only(self):
        as_user(self.ids["A"])
        own = self.c.get("/api/mis?bank=AXIS&product=CC&month_bucket=current").json()
        self.assertNotIn("read_only", own)
        peer = self.c.get(f"/api/mis?bank=AXIS&product=CC&month_bucket=current&peer_lead={self.ids['B']}")
        self.assertEqual(peer.status_code, 200, peer.text)
        p = peer.json()
        self.assertTrue(p["read_only"]); self.assertEqual(p["viewing_lead"]["name"], "Lead B")
        self.assertNotEqual(own, p)
        db = SessionLocal()
        self.assertTrue(db.query(models.AuditLog).filter(models.AuditLog.action == "peer_view").count() >= 1)
        db.close()

    def test_lead_on_other_portfolio_refused(self):
        as_user(self.ids["A"])
        self.assertEqual(self.c.get(f"/api/mis?bank=AXIS&product=CC&peer_lead={self.ids['C']}").status_code, 403)
        self.assertEqual(self.c.get(f"/api/mis?bank=ICICI&product=PL&peer_lead={self.ids['C']}").status_code, 403)
        self.assertEqual(self.c.get(f"/api/cases/filter-options?bank=ICICI&product=PL&peer_lead={self.ids['C']}").status_code, 403)

    def test_portfolios_month_wise(self):
        as_user(self.ids["A"])
        allp = self.c.get("/api/team/portfolios").json()
        self.assertEqual([p["period"] for p in allp], [self.cur, self.last])          # newest month first
        cur = self.c.get("/api/team/portfolios?month_bucket=current").json()
        self.assertEqual(len(cur), 1); self.assertEqual(cur[0]["count"], 1)
        leads = self.c.get(f"/api/team/portfolio/leads?bank=AXIS&product=CC&branch=&month_bucket={self.cur}").json()
        self.assertEqual({l["name"]: l["count"] for l in leads}, {"Lead A": 1, "Lead B": 3})


if __name__ == "__main__":
    unittest.main()
