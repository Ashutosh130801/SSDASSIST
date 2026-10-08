"""Isolated database and mocked HTTP. Never places a real call."""
import unittest
from unittest.mock import patch
import httpx
import test_predictive_screenpop as fixture


class TestCallTests(unittest.TestCase):
    def setUp(self):
        fixture.ScreenPopTests.setUp(self)
        self.actor.role = "admin"
        self.db.commit()
        self.url = f"/api/integration/vicidial/{self.conn.id}/test-call"
        self.body = dict(agent_user="8002", phone_number="9876543210", phone_code="91", confirmed=True)

    tearDown = fixture.ScreenPopTests.tearDown

    def send(self, text="SUCCESS: external_dial function set", status=200, error=None):
        with patch("app.vicidial_test_call.httpx.Client") as factory:
            outbound = factory.return_value.__enter__.return_value
            outbound.post.return_value = httpx.Response(status, text=text)
            if error:
                outbound.post.side_effect = error
            response = self.client.post(self.url, json=self.body)
        return response, factory, outbound

    def test_exact_connection_no_case_link(self):
        self.db.add(fixture.models.DialerConnection(kind="vicidial", name="Other", base_url="https://wrong.example.test", api_key="other", enabled=True))
        self.db.commit()
        response, factory, outbound = self.send()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertNotIn("verify", factory.call_args.kwargs)
        self.assertFalse(factory.call_args.kwargs["follow_redirects"])
        outbound.post.assert_called_once()
        self.assertEqual(outbound.post.call_args.args[0], "https://dialer.example.test/agc/api.php")
        params = outbound.post.call_args.kwargs["data"]
        self.assertEqual(params["agent_user"], "8002")
        self.assertEqual(params["search"], "NO")
        self.assertEqual(params["focus"], "NO")
        self.assertTrue(params["vendor_id"].startswith("RIQTEST"))
        self.assertNotIn("vendor_lead_code", params)
        self.assertNotIn("params", outbound.post.call_args.kwargs)
        self.assertEqual(self.db.query(fixture.models.CallLog).count(), 0)
        record = self.db.query(fixture.models.AuditLog).filter_by(action="vicidial_test_call").one()
        self.assertEqual(record.meta["state"], "accepted")
        self.assertNotIn("9876543210", record.detail)
        self.assertNotIn("test-only-secret", response.text)

    def test_international_number(self):
        self.body["phone_number"] = "+91 (98765) 43210"
        response, _, outbound = self.send()
        self.assertTrue(response.json()["ok"])
        self.assertEqual(outbound.post.call_args.kwargs["data"]["value"], "9876543210")

    def test_validation(self):
        for field, value in [("confirmed", False), ("confirmed", "true"), ("agent_user", "bad@email"),
                             ("phone_number", "abc9876543210"), ("phone_number", "919876543210"),
                             ("phone_number", "+449876543210"), ("phone_number", "123"),
                             ("phone_code", "+91"), ("phone_number", "0000000000")]:
            with self.subTest(field=field, value=value):
                old = self.body[field]
                self.body[field] = value
                response, _, outbound = self.send()
                self.assertIn(response.status_code, (400, 422))
                outbound.post.assert_not_called()
                self.body[field] = old

    def test_disabled_wrong_kind_and_missing(self):
        for field, value, status in [("enabled", False, 409), ("kind", "dialer", 404)]:
            old = getattr(self.conn, field)
            setattr(self.conn, field, value)
            self.db.commit()
            response, _, outbound = self.send()
            self.assertEqual(response.status_code, status)
            outbound.post.assert_not_called()
            setattr(self.conn, field, old)
            self.db.commit()
        self.url = "/api/integration/vicidial/999999/test-call"
        self.assertEqual(self.send()[0].status_code, 404)

    def test_roles(self):
        for role in ["telecaller", "fos", "manager", "teamlead"]:
            self.actor.role = role
            self.db.commit()
            response, _, outbound = self.send()
            self.assertEqual(response.status_code, 403, role)
            outbound.post.assert_not_called()
        self.actor.role = "headoffice"
        self.db.commit()
        self.assertTrue(self.send()[0].json()["ok"])

    def test_unauthenticated(self):
        from app.deps import get_current_user
        del self.app.dependency_overrides[get_current_user]
        response, _, outbound = self.send()
        self.assertEqual(response.status_code, 401)
        outbound.post.assert_not_called()

    def test_missing_credentials(self):
        self.conn.capabilities = {"vici_user": "api-test"}
        self.db.commit()
        response, _, outbound = self.send()
        self.assertEqual(response.status_code, 400)
        outbound.post.assert_not_called()

    def test_rejection_redacted_audited(self):
        response, _, _ = self.send("ERROR: agent_user is not logged in - test-only-secret|9876543210")
        self.assertEqual(response.json()["state"], "rejected")
        self.assertIn("not logged in", response.json()["detail"])
        self.assertNotIn("test-only-secret", response.text)
        self.assertNotIn("9876543210", response.text)
        self.assertEqual(self.db.query(fixture.models.AuditLog).one().meta["state"], "rejected")

    def test_timeout_no_retry(self):
        response, _, outbound = self.send(error=httpx.ReadTimeout("pass=test-only-secret"))
        self.assertEqual(response.json()["state"], "unknown")
        self.assertIn("before retrying", response.json()["detail"])
        self.assertNotIn("test-only-secret", response.text)
        outbound.post.assert_called_once()

    def test_unknown_response_and_redirect(self):
        for status, text in [(200, "<html>test-only-secret login</html>"), (302, "redirect"),
                             (500, "error"), (200, "SUCCESS: some_other_function")]:
            response, _, _ = self.send(text, status)
            self.assertFalse(response.json()["ok"])
            self.assertEqual(response.json()["state"], "unknown")
            self.assertNotIn("test-only-secret", response.text)


if __name__ == "__main__":
    unittest.main()
