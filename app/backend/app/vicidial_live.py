"""Read-only predictive screen-pop support. Credentials never leave the server.

Wire format: https://vicidial.org/docs/NON-AGENT_API.txt (agent_status).
"""
import csv
import io
import re
import hashlib

import httpx
from sqlalchemy import func

from . import models


class LiveCallError(ValueError):
    """Safe, user-facing error (never an upstream response or credential)."""


def event_key(conn_id, agent, call_id, case_id):
    import json
    return hashlib.sha256(json.dumps([conn_id, agent, call_id, case_id]).encode()).hexdigest()


def agent_for(conn, user):
    code = (user.emp_code or "").strip()
    mapping = (conn.capabilities or {}).get("agent_map") or {}
    if not isinstance(mapping, dict):
        raise LiveCallError("Ask an administrator to correct the ViciDial agent map.")
    mapping = {str(k).strip().upper(): str(v).strip() for k, v in mapping.items()}
    return mapping.get(code.upper(), code)


def connection_for(db, user):
    """Never fall back to an unrelated branch's dialer."""
    rows = db.query(models.DialerConnection).filter(
        models.DialerConnection.kind == "vicidial",
        models.DialerConnection.enabled.is_(True)).all()
    branch = (user.branch or "").strip().casefold()
    specific = [c for c in rows if (c.branch or "").strip().casefold() == branch and branch]
    choices = specific or [c for c in rows if not (c.branch or "").strip()]
    if len(choices) > 1:
        raise LiveCallError("Multiple ViciDial connections cover your branch. Ask an administrator to keep one enabled.")
    return choices[0] if choices else None


def parse_agent_status(text):
    text = text.strip().lstrip("\ufeff")
    if text.startswith("ERROR:"):
        if "AGENT NOT LOGGED IN" in text:
            return {"status": "LOGGED_OUT"}
        if "AGENT NOT FOUND" in text:
            raise LiveCallError("ViciDial agent not found. Check your employee-code mapping in Connections.")
        raise LiveCallError("ViciDial rejected the status request. Check API credentials, agent_status access, View Reports and user-group access.")
    try:
        rows = list(csv.reader(io.StringIO(text)))
        rows = [row for row in rows if any(cell.strip() for cell in row)]
        header = [cell.strip().lower() for cell in rows[0]]
        required = {"status", "call_id", "lead_id", "vendor_lead_code", "real_time_sub_status"}
        if len(rows) != 2 or not required.issubset(header) or len(header) != len(set(header)) or len(rows[1]) != len(header):
            raise ValueError()
        return dict(zip(header, (cell.strip() for cell in rows[1])))
    except (ValueError, IndexError, csv.Error):
        raise LiveCallError("Unexpected ViciDial status response. Check that agent_status supports CSV with headers on your server.") from None


def read_agent_status(conn, agent):
    caps = conn.capabilities or {}
    if not caps.get("vici_user") or not caps.get("vici_pass"):
        raise LiveCallError("ViciDial API credentials are missing. Ask an administrator to update Connections.")
    params = {"function": "agent_status", "source": str(caps.get("source") or "recoveriq")[:20],
              "user": caps["vici_user"], "pass": caps["vici_pass"],
              "agent_user": agent, "stage": "csv", "header": "YES"}
    try:
        # POST keeps credentials out of query strings/access logs. Verify HTTPS certificates;
        # install a trusted certificate on the dialer instead of disabling verification.
        with httpx.Client(timeout=4.0, follow_redirects=False) as client:
            response = client.post(conn.base_url.rstrip("/") + "/vicidial/non_agent_api.php", data=params)
            response.raise_for_status()
        return parse_agent_status(response.text)
    except httpx.HTTPError:
        raise LiveCallError("Cannot reach ViciDial securely. Check the server URL, network/VPN and TLS certificate. Retrying automatically.") from None


def live_call_for(db, user):
    from .routers.cases import _scope

    conn = connection_for(db, user)
    if not conn:
        return {"state": "disabled", "poll_after_ms": 30000}
    agent = agent_for(conn, user)
    if not agent:
        return {"state": "unmapped", "detail": "Set your employee code and ViciDial agent map in Connections.", "poll_after_ms": 30000}
    # A ViciDial identity must belong to one active RecoverIQ employee in this connection.
    mapping = (conn.capabilities or {}).get("agent_map") or {}
    candidate_codes = {str(k).strip().upper() for k, v in mapping.items() if str(v).strip() == agent}
    candidate_codes.add(agent.upper())  # implicit employee-code mapping can also conflict
    others = db.query(models.User).filter(models.User.is_active.is_(True), models.User.id != user.id,
        func.upper(func.trim(models.User.emp_code)).in_(candidate_codes)).all()
    for other in others:
        if agent_for(conn, other) == agent:
            other_conn = connection_for(db, other)
            if other_conn and other_conn.id == conn.id:
                raise LiveCallError("This ViciDial agent is mapped to multiple employees. Ask an administrator to make the mapping unique.")
    row = read_agent_status(conn, agent)
    status = row.get("status", "").upper()
    substatus = row.get("real_time_sub_status", "").upper()
    result = {"state": "waiting", "agent_status": status, "substatus": substatus, "poll_after_ms": 2000}
    if status == "LOGGED_OUT":
        return {**result, "state": "logged_out", "detail": "Sign in to your ViciDial agent/audio session to receive calls.", "poll_after_ms": 10000}
    # INCALL may still refer to a ringing, dead or disposition-stage call. Only a live
    # conversation (including a transferred/parked existing conversation) may pop.
    if status != "INCALL" or substatus not in ("", "3-WAY", "PARK"):
        return result
    ref = row.get("vendor_lead_code", "")
    call_id = row.get("call_id", "")
    if not call_id or not re.fullmatch(r"[0-9]{1,18}", ref) or int(ref) <= 0:
        return {**result, "state": "unmatched", "detail": "Connected lead has no valid RecoverIQ case ID. Push the case from RecoverIQ or correct vendor_lead_code in ViciDial."}
    case = _scope(db.query(models.Case), user).filter(models.Case.id == int(ref)).first()
    if not case or (conn.branch and (case.branch or "").strip().casefold() != conn.branch.strip().casefold()):
        return {**result, "state": "unavailable", "detail": "Connected case is unavailable in your current role/branch. Ask your manager to check allocation and portfolio status."}
    # Use call identity, not phone/lead alone: repeat calls to one customer must pop again.
    return {**result, "state": "connected", "event_id": event_key(conn.id, agent, call_id, case.id),
            "case_id": case.id, "agent_user": agent, "call_id": call_id}
