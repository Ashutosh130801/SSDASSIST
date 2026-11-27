"""Team Follow-up role: HR creates a follower (primary role or extra hat with a TF id), adds FOS /
callers, the follower sees ONLY those members' complete performance (read-only), dual-role users
switch views, and nothing changes for the existing roles."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_t = tempfile.TemporaryDirectory(prefix="tfollow-")
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(_t.name) / "t.db")
os.chdir(_t.name)

from fastapi.testclient import TestClient

from app import models
from app.database import SessionLocal
from app.main import app
from app.security import create_access_token


def tok(uid, role, av=None):
    return {"Authorization": "Bearer " + create_access_token(subject=uid, role=role, name="x", active_role=av or role)}


class TeamFollowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db = SessionLocal()
        hr = models.User(name="HR One", email="hr@x", role="hr", is_active=True, emp_code="HR001")
        f1 = models.User(name="Fos One", email="f1@x", role="fos", is_active=True, emp_code="FO001")
        f2 = models.User(name="Fos Two", email="f2@x", role="fos", is_active=True, emp_code="FO002")
        c1 = models.User(name="Caller One", email="c1@x", role="telecaller", is_active=True, emp_code="TC001")
        tl = models.User(name="Lead", email="tl@x", role="teamlead", is_active=True, emp_code="TL001")
        mgr = models.User(name="Mgr", email="m@x", role="manager", branch="VZG", is_active=True, emp_code="MG001")
        db.add_all([hr, f1, f2, c1, tl, mgr]); db.flush()

        def case(i, fos=None, caller=None, bank="AXIS", paid=False):
            return models.Case(customer_name=f"C{i}", account_no=f"AC{i}", bank=bank, product="CC",
                               assigned_fos_id=fos, assigned_caller_id=caller, enr=1000, funding_amount=1000,
                               pending_amount=0 if paid else 1000, team_lead="Lead",
                               paid_status="PAID" if paid else "UNPAID", received_amount=1000 if paid else 0)
        cs = [case(1, fos=f1.id, paid=True), case(2, fos=f1.id, bank="ICICI"), case(3, caller=c1.id),
              case(4, fos=f2.id)]
        db.add_all(cs); db.flush()
        db.add(models.Visit(case_id=cs[0].id, officer_id=f1.id, disposition="PAID", amount_collected=1000))
        db.commit()
        cls.ids = dict(hr=hr.id, f1=f1.id, f2=f2.id, c1=c1.id, tl=tl.id, mgr=mgr.id,
                       case_f1=cs[1].id, case_f2=cs[3].id)
        db.close()
        cls.c = TestClient(app)

    def test_1_primary_follower_flow(self):
        c, ids = self.c, self.ids
        H = tok(ids["hr"], "hr")
        r = c.post("/api/manpower", json={"name": "Follow Pri", "email": "tf@x", "role": "teamfollower"}, headers=H)
        self.assertEqual(r.status_code, 200, r.text)
        fid = r.json()["id"]
        self.assertTrue(r.json()["emp_code"].startswith("FTL"))
        self.assertIn("Field TL", r.json()["all_roles"])
        # add FOS + caller; a team lead (no FOS/caller id) is rejected
        r = c.post(f"/api/team-follow/{fid}/members", json={"member_ids": [ids["tl"]]}, headers=H)
        self.assertEqual(r.status_code, 400)
        r = c.post(f"/api/team-follow/{fid}/members", json={"member_ids": [ids["f1"], ids["c1"]]}, headers=H)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["member_count"], 2)
        self.assertTrue(any(x["id"] == fid for x in c.get("/api/team-follow/followers", headers=H).json()))

        F = tok(fid, "teamfollower")
        r = c.get("/api/team-follow/me/members?month_bucket=all", headers=F)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["totals"]["members"], 2)
        f1row = next(m for m in body["members"] if m["id"] == ids["f1"])
        self.assertEqual(f1row["cases"]["assigned"], 2)        # irrespective of portfolio (AXIS + ICICI)
        self.assertEqual(f1row["money"]["collected_visits"], 1000)
        # complete performance of a member: dashboard, cases, trends, MIS perf, route history
        for url in (f"/api/team/user/{ids['f1']}/dashboard?month_bucket=all", f"/api/team/user/{ids['f1']}/cases",
                    f"/api/team/user/{ids['f1']}/performance", f"/api/mis/employee-trends?user_id={ids['f1']}",
                    f"/api/mis/performance?emp_id={ids['f1']}&role=fos&month_bucket=all",
                    f"/api/tracking/officer/{ids['f1']}/history-dates",
                    f"/api/attendance/user/{ids['f1']}/visits", f"/api/cases/{ids['case_f1']}"):
            self.assertEqual(c.get(url, headers=F).status_code, 200, url)
        self.assertTrue(c.get(f"/api/cases/{ids['case_f1']}", headers=F).json().get("read_only"))
        # NOT a member → blocked everywhere
        for url in (f"/api/team/user/{ids['f2']}/dashboard", f"/api/mis/employee-trends?user_id={ids['f2']}",
                    f"/api/tracking/officer/{ids['f2']}/history-dates", f"/api/attendance/user/{ids['f2']}/visits"):
            self.assertEqual(c.get(url, headers=F).status_code, 403, url)
        self.assertEqual(c.get(f"/api/cases/{ids['case_f2']}", headers=F).status_code, 404)
        # tracking-only view: company-wide screens + writes blocked
        for url in ("/api/analytics/dashboard", "/api/cases", "/api/mis/overview", "/api/manpower"):
            self.assertEqual(c.get(url, headers=F).status_code, 403, url)
        self.assertEqual(c.post("/api/calls", json={"case_id": ids["case_f1"], "disposition": "PTP"}, headers=F).status_code, 403)
        self.assertEqual(c.post("/api/visits", data={"case_id": ids["case_f1"]}, headers=F).status_code, 403)
        self.assertEqual(c.post("/api/cases/remove", json={"ids": [ids["case_f1"]]}, headers=F).status_code, 403)
        # self-service still works
        self.assertEqual(c.get("/api/auth/me", headers=F).status_code, 200)
        # remove a member
        r = c.delete(f"/api/team-follow/{fid}/members/{ids['c1']}", headers=H)
        self.assertEqual(r.json()["member_count"], 1)

    def test_2_extra_hat_and_switch_view(self):
        c, ids = self.c, self.ids
        H = tok(ids["hr"], "hr")
        r = c.patch(f"/api/manpower/{ids['f2']}", json={"also_team_follower": True}, headers=H)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue((r.json().get("tf_emp_code") or "").startswith("FTL"))
        self.assertIn("Field TL", r.json()["all_roles"])
        c.post(f"/api/team-follow/{ids['f2']}/members", json={"member_ids": [ids["f1"]]}, headers=H)
        # as FOS (primary view): own work as before, can't see f1's profile
        FO = tok(ids["f2"], "fos")
        me = c.get("/api/auth/me", headers=FO).json()
        self.assertEqual(set(me["available_views"]), {"fos", "teamfollower"})
        self.assertEqual(c.get(f"/api/team/user/{ids['f1']}/dashboard", headers=FO).status_code, 403)
        # switch view → follower
        r = c.post("/api/auth/switch-view", json={"view": "teamfollower"}, headers=FO)
        self.assertEqual(r.status_code, 200, r.text)
        TFh = {"Authorization": "Bearer " + r.json()["access_token"]}
        self.assertEqual(r.json()["user"]["role"], "teamfollower")
        self.assertEqual(c.get(f"/api/team/user/{ids['f1']}/dashboard", headers=TFh).status_code, 200)
        self.assertEqual(c.get("/api/team-follow/me/members", headers=TFh).json()["totals"]["members"], 1)
        # and back to FOS
        r = c.post("/api/auth/switch-view", json={"view": "fos"}, headers=TFh)
        self.assertEqual(r.json()["user"]["role"], "fos")
        # revoke → view gone
        c.patch(f"/api/manpower/{ids['f2']}", json={"also_team_follower": False}, headers=H)
        self.assertEqual(c.get("/api/auth/me", headers=FO).json()["available_views"], ["fos"])

    def test_3_existing_roles_unchanged(self):
        c, ids = self.c, self.ids
        self.assertEqual(c.get(f"/api/team/user/{ids['f1']}/dashboard", headers=tok(ids["f2"], "fos")).status_code, 403)
        self.assertEqual(c.get("/api/cases", headers=tok(ids["f1"], "fos")).status_code, 200)
        self.assertEqual(c.get("/api/team-follow/followers", headers=tok(ids["f1"], "fos")).status_code, 403)
        self.assertEqual(c.get("/api/team-follow/followers", headers=tok(ids["mgr"], "manager")).status_code, 403)


if __name__ == "__main__":
    unittest.main()
