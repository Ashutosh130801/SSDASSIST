"""Explicit administrator test calls; never associate them with collection cases."""
import re
from urllib.parse import quote, quote_plus, urlsplit
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from fastapi import HTTPException


class TestCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_user: str = Field(strict=True, min_length=1, max_length=20)
    phone_number: str = Field(strict=True, min_length=1, max_length=40)
    phone_code: str = Field(strict=True, min_length=1, max_length=3)
    confirmed: StrictBool = False


def validate_test_call(body):
    if not body.confirmed:
        raise HTTPException(400, "Confirm permission to place this real test call first.")
    agent = body.agent_user.strip()
    code = body.phone_code.strip()
    raw = body.phone_number.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,20}", agent):
        raise HTTPException(400, "Enter a valid ViciDial agent user ID (not an email or SIP address).")
    if not re.fullmatch(r"[1-9][0-9]{0,2}", code):
        raise HTTPException(400, "Enter a country code of 1–3 digits, without +.")
    if not re.fullmatch(r"\+?[0-9 ()-]+", raw):
        raise HTTPException(400, "Enter a phone number using digits, spaces, brackets or hyphens only.")
    phone = re.sub(r"[^0-9]", "", raw)
    if raw.startswith("+"):
        if not phone.startswith(code):
            raise HTTPException(400, "The international number does not match the selected country code.")
        phone = phone[len(code):]
    if not 6 <= len(phone) <= 14 or len(code + phone) > 15:
        raise HTTPException(400, "Enter a valid national number; supply its country code separately.")
    if code == "91" and not re.fullmatch(r"[1-9][0-9]{9}", phone):
        raise HTTPException(400, "For country code 91, enter 10 digits without a leading 0 or 91, or use +91 followed by 10 digits.")
    return agent, code, phone


def send_test_call(conn, agent, code, phone):
    caps = conn.capabilities or {}
    if not caps.get("vici_user") or not caps.get("vici_pass"):
        raise HTTPException(400, "Save this connection's ViciDial API username and password first.")
    base = conn.base_url.rstrip("/")
    parts = urlsplit(base)
    if parts.scheme not in ("https", "http") or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise HTTPException(400, "Correct the saved ViciDial base URL before testing.")
    params = {"function": "external_dial", "source": "recoveriq-test",
              "user": caps["vici_user"], "pass": caps["vici_pass"],
              "agent_user": agent, "value": phone, "phone_code": code,
              "search": "NO", "preview": "NO", "focus": "NO",
              # Non-numeric vendor ID ensures legacy disposition callbacks cannot match a case.
              "vendor_id": "RIQTEST" + uuid4().hex[:12]}
    try:
        # No credential-bearing query string, redirects, disabled TLS checks, or automatic retries.
        with httpx.Client(timeout=10.0, follow_redirects=False) as client:
            response = client.post(base + "/agc/api.php", data=params)
        if response.status_code != 200:
            return {"ok": False, "state": "unknown", "detail": f"ViciDial returned HTTP {response.status_code}. Check the agent session before retrying; the call may have been submitted."}
        text = response.text.strip()
        if text.startswith("SUCCESS: external_dial"):
            return {"ok": True, "state": "accepted", "detail": "ViciDial accepted the dial command. Verify ringing and two-way audio; acceptance does not mean the customer answered."}
        if text.startswith("ERROR:"):
            # Only the diagnostic prefix, never echoed API arguments/customer details.
            detail = text.splitlines()[0].split("|", 1)[0]
            for secret in (str(caps["vici_pass"]), str(caps["vici_user"]), str(conn.api_key or ""), phone):
                if secret:
                    for value in (secret, quote(secret, safe=""), quote_plus(secret)):
                        detail = detail.replace(value, "[redacted]")
            detail = re.sub(r"[\x00-\x1f\x7f]", " ", detail)[:240]
            return {"ok": False, "state": "rejected", "detail": detail + " — check agent login, campaign/manual-dial settings and Agent API permissions."}
        return {"ok": False, "state": "unknown", "detail": "Unexpected ViciDial response. Check the agent session before retrying; the call may have been submitted."}
    except httpx.HTTPError:
        return {"ok": False, "state": "unknown", "detail": "No confirmed response from ViciDial. Check its URL, network/VPN and TLS certificate, then check the agent session before retrying; the call may have been submitted."}
