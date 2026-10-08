"""Isolated screen-pop tests. No live database or ViciDial calls are used."""
import csv
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_temp = tempfile.TemporaryDirectory(prefix="screenpop-test-")
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(_temp.name) / "unused.db")

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app import models
from app.database import Base, get_db, engine as configured_engine
from app.deps import get_current_user
from app.routers.integrations import router
from app.routers import realtime
from app.vicidial_live import parse_agent_status, read_agent_status, LiveCallError


def wire(**changes):
    row = dict(status="INCALL", call_id="M123456", lead_id="44", campaign_id="RECOVER",
               calls_today="1", full_name="Agent, One", user_group="AGENTS", user_level="3",
               pause_code="", real_time_sub_status="", phone_number="9999999999",
               vendor_lead_code="1", session_id="8600051")
    row.update(changes)
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(row.keys())
    writer.writerow(row.values())
    return stream.getvalue()


class ScreenPopTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.actor = models.User(name="Agent", email="caller@example.test", emp_code="TC001", branch="Vizag", role="telecaller", is_active=True)
        self.db.add(self.actor)
        self.db.flush()
        self.conn = models.DialerConnection(kind="vicidial", name="Test", api_key="test-integration-key", base_url="https://dialer.example.test", branch="Vizag", enabled=True,
            capabilities={"vici_user": "api-test", "vici_pass": "test-only-secret", "agent_map": {"TC001": "8001"}})
        self.case = models.Case(customer_name="Test customer", account_no="A1", bank="ICICI", product="FR", branch="Vizag", assigned_caller_id=self.actor.id)
        self.db.add_all([self.conn, self.case])
        self.db.commit()
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.include_router(realtime.router)
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.app.dependency_overrides[get_current_user] = lambda: self.actor
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def poll(self, **changes):
        with patch("app.vicidial_live.read_agent_status", return_value=parse_agent_status(wire(vendor_lead_code=str(self.case.id), **changes))) as read:
            response = self.client.get("/api/integration/vicidial/my-live-call?agent_user=somebody-else")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.headers["cache-control"])
        return response.json(), read

    def test_connected_uses_authenticated_agent_and_exact_case(self):
        result, read = self.poll()
        self.assertEqual(result["state"], "connected")
        self.assertEqual(result["case_id"], self.case.id)
        self.assertEqual(read.call_args.args[1], "8001")
        self.assertNotIn("test-only-secret", str(result))
        self.assertNotIn("phone_number", result)

    def test_repeated_poll_same_call_and_redial_distinct(self):
        first, _ = self.poll()
        second, _ = self.poll()
        redial, _ = self.poll(call_id="M999")
        self.assertEqual(first["event_id"], second["event_id"])
        self.assertNotEqual(first["event_id"], redial["event_id"])

    def test_non_connected_states_do_not_open(self):
        for state in ["READY", "PAUSED", "QUEUE", "CLOSER", "DISPO"]:
            result, _ = self.poll(status=state)
            self.assertNotIn("case_id", result)
        for sub in ["RING", "DIAL", "DEAD", "DISPO", "PREVIEW", "UNKNOWN"]:
            result, _ = self.poll(real_time_sub_status=sub)
            self.assertNotIn("case_id", result)

    def test_unassigned_removed_previous_month_and_cross_branch_blocked(self):
        for field, value in [("assigned_caller_id", None), ("removed", True), ("period", "2000-01"), ("branch", "Hyderabad")]:
            old = getattr(self.case, field)
            setattr(self.case, field, value)
            self.db.commit()
            result, _ = self.poll()
            self.assertEqual(result["state"], "unavailable", field)
            self.assertNotIn("case_id", result)
            setattr(self.case, field, old)
            self.db.commit()

    def test_disabled_or_other_branch_never_contacts_dialer(self):
        self.conn.enabled = False
        self.db.commit()
        result, read = self.poll()
        self.assertEqual(result["state"], "disabled")
        read.assert_not_called()
        self.conn.enabled = True
        self.conn.branch = "Hyderabad"
        self.db.commit()
        result, read = self.poll()
        self.assertEqual(result["state"], "disabled")
        read.assert_not_called()

    def test_branch_specific_preferred_over_global(self):
        self.db.add(models.DialerConnection(kind="vicidial", name="Global", api_key="test-global", base_url="https://global.example.test", enabled=True))
        self.db.commit()
        _, read = self.poll()
        self.assertEqual(read.call_args.args[0].id, self.conn.id)

    def test_duplicate_connections_fail_closed(self):
        self.db.add(models.DialerConnection(kind="vicidial", name="Duplicate", api_key="test-duplicate", base_url="https://duplicate.example.test", branch="Vizag", enabled=True))
        self.db.commit()
        result, read = self.poll()
        self.assertEqual(result["state"], "error")
        read.assert_not_called()

    def test_duplicate_agent_mapping_fails_closed(self):
        self.db.add(models.User(name="Other", email="other@example.test", emp_code="TC002", role="telecaller", branch="Vizag", is_active=True))
        self.conn.capabilities = {**self.conn.capabilities, "agent_map": {"TC001": "8001", "TC002": "8001"}}
        self.db.commit()
        result, read = self.poll()
        self.assertEqual(result["state"], "error")
        read.assert_not_called()

    def test_missing_identity_does_not_guess_by_phone(self):
        for value in ["", "--A--vendor_lead_code--B--", "A123", "1.0", "-1", "0", "9" * 30]:
            with patch("app.vicidial_live.read_agent_status", return_value=parse_agent_status(wire(vendor_lead_code=value))):
                result = self.client.get("/api/integration/vicidial/my-live-call").json()
            self.assertEqual(result["state"], "unmatched")

    def test_csv_headers_and_quoted_names(self):
        row = parse_agent_status(wire())
        self.assertEqual(row["full_name"], "Agent, One")
        self.assertEqual(row["vendor_lead_code"], "1")
        for text in ["", "<html>Login</html>", "INCALL|1|2", "status,call_id\nINCALL,x", wire() + wire()]:
            with self.assertRaises(LiveCallError):
                parse_agent_status(text)

    def test_logged_out_and_permission_errors(self):
        self.assertEqual(parse_agent_status("ERROR: agent_status AGENT NOT LOGGED IN - secret")['status'], "LOGGED_OUT")
        with self.assertRaises(LiveCallError) as caught:
            parse_agent_status("ERROR: USER DOES NOT HAVE PERMISSION secret")
        self.assertNotIn("secret", str(caught.exception))

    def test_upstream_uses_post_and_verified_tls(self):
        reply = httpx.Response(200, text=wire(), request=httpx.Request("POST", "https://dialer.example.test"))
        with patch("app.vicidial_live.httpx.Client") as client:
            client.return_value.__enter__.return_value.post.return_value = reply
            self.assertEqual(read_agent_status(self.conn, "8001")["status"], "INCALL")
            self.assertNotEqual(client.call_args.kwargs.get("verify"), False)
            args = client.return_value.__enter__.return_value.post.call_args
            self.assertNotIn("pass=", args.args[0])
            self.assertEqual(args.kwargs["data"]["function"], "agent_status")
            self.assertEqual(args.kwargs["data"]["agent_user"], "8001")

    def test_upstream_failure_is_sanitized_and_retryable(self):
        with patch("app.vicidial_live.httpx.Client", side_effect=httpx.ConnectError("secret-address")):
            result = self.client.get("/api/integration/vicidial/my-live-call").json()
        self.assertEqual(result["state"], "error")
        self.assertEqual(result["poll_after_ms"], 15000)
        self.assertNotIn("secret-address", str(result))

    def test_authentication_required(self):
        del self.app.dependency_overrides[get_current_user]
        self.assertEqual(self.client.get("/api/integration/vicidial/my-live-call").status_code, 401)

    def start_call(self, **changes):
        params = dict(key="test-integration-key", agent="8001", case=str(self.case.id), call_id="M123456")
        params.update(changes)
        return self.client.get('/api/integration/vicidial/start-call', params=params)

    def test_callback_commits_before_targeted_push_and_deduplicates(self):
        sent = []
        def notify(uid, payload):
            self.assertEqual(self.db.query(models.PredictiveCallEvent).count(), 1)
            sent.append((uid, payload))
        with patch('app.routers.realtime.notify_user', side_effect=notify):
            first = self.start_call(); second = self.start_call()
        self.assertEqual(first.status_code, 200)
        self.assertFalse(first.json()['duplicate'])
        self.assertTrue(second.json()['duplicate'])
        self.assertEqual(sent[0][0], self.actor.id)
        self.assertEqual(set(sent[0][1]), {'type', 'event_id'})
        identity = sent[0][1]['event_id']
        result = self.client.get('/api/integration/vicidial/events/' + identity)
        self.assertEqual(result.json()['case_id'], self.case.id)
        live, _ = self.poll()
        self.assertEqual(live['event_id'], identity)

    def test_callback_rejects_invalid_disabled_unknown_and_unassigned(self):
        with patch('app.routers.realtime.notify_user') as notify:
            for args, status in [({'key': ''}, 401), ({'key': 'bad'}, 401), ({'case': 'abc'}, 422),
                                 ({'call_id': '--A--call_id--B--'}, 422), ({'agent': 'unknown'}, 409)]:
                self.assertEqual(self.start_call(**args).status_code, status)
            self.case.assigned_caller_id = None; self.db.commit()
            self.assertEqual(self.start_call().status_code, 404)
            self.conn.enabled = False; self.db.commit()
            self.assertEqual(self.start_call().status_code, 401)
            notify.assert_not_called()
        self.assertEqual(self.db.query(models.PredictiveCallEvent).count(), 0)

    def test_event_rechecks_permissions_and_owner(self):
        with patch('app.routers.realtime.notify_user'):
            self.start_call()
        event = self.db.query(models.PredictiveCallEvent).one()
        url = '/api/integration/vicidial/events/' + event.event_key
        self.actor = models.User(name='Other', email='other@example.test', emp_code='TC002', role='telecaller', branch='Vizag', is_active=True)
        self.db.add(self.actor); self.db.commit()
        self.assertEqual(self.client.get(url).status_code, 404)
        self.actor = self.db.get(models.User, event.user_id)
        self.case.removed = True; self.db.commit()
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_expired_and_superseded_events_do_not_open(self):
        with patch('app.routers.realtime.notify_user'):
            self.start_call()
            first = self.db.query(models.PredictiveCallEvent).one()
            self.start_call(call_id='M2')
        self.assertEqual(self.client.get('/api/integration/vicidial/events/' + first.event_key).json()['state'], 'expired')
        latest = self.db.query(models.PredictiveCallEvent).order_by(models.PredictiveCallEvent.id.desc()).first()
        latest.created_at = datetime.now(timezone.utc) - timedelta(minutes=3); self.db.commit()
        self.assertEqual(self.client.get('/api/integration/vicidial/events/' + latest.event_key).json()['state'], 'expired')

    def test_setup_url_is_admin_only(self):
        url = f'/api/integration/vicidial/{self.conn.id}/start-call-url'
        self.assertEqual(self.client.get(url).status_code, 403)
        self.actor.role = 'admin'; self.db.commit()
        response = self.client.get(url)
        self.assertIn('no-store', response.headers['cache-control'])
        self.assertTrue(response.json()['start_call_url'].startswith('VARhttp://testserver/api/integration/vicidial/start-call'))
        self.assertIn('--A--call_id--B--', response.json()['start_call_url'])

    def test_real_websocket_receives_targeted_callback(self):
        with patch('app.routers.realtime._socket_identity', return_value=(self.actor.id, self.actor.name, self.actor.role)):
            with self.client as client:
                with client.websocket_connect('/ws?token=test-token') as socket:
                    response = self.start_call()
                    self.assertEqual(response.status_code, 200)
                    message = socket.receive_json()
                    self.assertEqual(message['type'], 'predictive_screenpop')
                    self.assertEqual(len(message['event_id']), 64)
        realtime._loop = None

    def test_socket_identity_checks_active_user(self):
        with patch('app.routers.realtime.SessionLocal', side_effect=lambda: Session(self.engine)), patch('app.routers.realtime.decode_token', return_value={'sub': str(self.actor.id)}):
            self.assertEqual(realtime._socket_identity('token')[0], self.actor.id)
            self.actor.is_active = False; self.db.commit()
            self.assertIsNone(realtime._socket_identity('token'))

    def test_access_log_redacts_query_credentials(self):
        import logging
        from app.log_redaction import CredentialQueryFilter
        record = logging.LogRecord('uvicorn.access', logging.INFO, '', 1, '%s - %s',
            ('client', '/api/integration/vicidial/start-call?key=TESTSECRET&agent=8001&token=JWTSECRET'), None)
        self.assertTrue(CredentialQueryFilter().filter(record))
        self.assertNotIn('TESTSECRET', record.getMessage())
        self.assertNotIn('JWTSECRET', record.getMessage())
        self.assertIn('agent=8001', record.getMessage())

    def test_dual_role_callback_does_not_grant_wrong_view_access(self):
        self.actor.role = 'fos'; self.actor.also_caller = True; self.db.commit()
        with patch('app.routers.realtime.notify_user'):
            self.assertEqual(self.start_call().status_code, 200)
        event = self.db.query(models.PredictiveCallEvent).one()
        self.assertEqual(self.client.get('/api/integration/vicidial/events/' + event.event_key).status_code, 404)
        self.actor.role = 'telecaller'; self.db.commit()
        self.assertEqual(self.client.get('/api/integration/vicidial/events/' + event.event_key).status_code, 200)


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        configured_engine.dispose()
        _temp.cleanup()
