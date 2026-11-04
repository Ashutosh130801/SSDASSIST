"""RazorpayX Payouts client (contacts → fund accounts → payouts) + webhook signature check.

Safety rules baked in here (the router adds approval/locking on top):
  • Keys come only from .env. A live key (rzp_live_) is refused unless RAZORPAYX_ALLOW_LIVE=true.
  • Every payout carries an X-Payout-Idempotency key that we store BEFORE calling — a retry of the same
    request (timeout, crash, double click) returns the SAME payout instead of paying twice.
  • Amounts are integer paise.
Docs: https://razorpay.com/docs/api/x/  (payouts, fund accounts, idempotency, webhooks)
"""
from __future__ import annotations

import hashlib
import hmac

import httpx

from .config import get_settings

BASE = "https://api.razorpay.com/v1"
TERMINAL = {"processed", "reversed", "failed", "rejected", "cancelled"}
# Gateway status → ours. Anything not terminal is "in flight" and must never be re-sent.
STATUS_MAP = {"queued": "queued", "pending": "pending_approval", "processing": "processing",
              "processed": "processed", "reversed": "reversed", "failed": "failed",
              "rejected": "rejected", "cancelled": "cancelled", "scheduled": "queued"}

_transport: httpx.BaseTransport | None = None   # tests inject a MockTransport here


class GatewayError(Exception):
    def __init__(self, msg, status=None, retriable=False):
        super().__init__(msg)
        self.status = status
        self.retriable = retriable


def config_state() -> dict:
    s = get_settings()
    kid = (s.razorpayx_key_id or "").strip()
    mode = "live" if kid.startswith("rzp_live_") else ("test" if kid.startswith("rzp_test_") else "")
    problems = []
    if not kid or not s.razorpayx_key_secret:
        problems.append("RAZORPAYX_KEY_ID / RAZORPAYX_KEY_SECRET not set in .env")
    elif not mode:
        problems.append("RAZORPAYX_KEY_ID must start with rzp_test_ or rzp_live_")
    if mode == "live" and not s.razorpayx_allow_live:
        problems.append("Live key found but RAZORPAYX_ALLOW_LIVE is not true — refusing live payouts")
    if not s.razorpayx_account_number:
        problems.append("RAZORPAYX_ACCOUNT_NUMBER not set in .env")
    acct = s.razorpayx_account_number or ""
    return {"provider": "razorpayx", "configured": not problems, "mode": mode or None, "problems": problems,
            "key_hint": (kid[:9] + "…" + kid[-4:]) if len(kid) > 14 else ("set" if kid else ""),
            "account_hint": ("XXXX" + acct[-4:]) if acct else "",
            "webhook_secret_set": bool(s.razorpayx_webhook_secret)}


def _client() -> httpx.Client:
    st = config_state()
    if not st["configured"]:
        raise GatewayError("; ".join(st["problems"]))
    s = get_settings()
    return httpx.Client(base_url=BASE, auth=(s.razorpayx_key_id.strip(), s.razorpayx_key_secret.strip()),
                        timeout=httpx.Timeout(25.0, connect=10.0), transport=_transport)


def _call(method: str, path: str, json: dict | None = None, headers: dict | None = None, params=None) -> dict:
    try:
        with _client() as c:
            r = c.request(method, path, json=json, headers=headers, params=params)
    except httpx.TimeoutException as e:     # outcome UNKNOWN — caller must keep the same idempotency key
        raise GatewayError(f"Gateway timeout: {e}", retriable=True)
    except httpx.HTTPError as e:
        raise GatewayError(f"Gateway unreachable: {e}", retriable=True)
    try:
        data = r.json()
    except ValueError:
        data = {}
    if r.status_code >= 400:
        err = (data.get("error") or {}) if isinstance(data, dict) else {}
        msg = err.get("description") or err.get("reason") or r.text[:200]
        raise GatewayError(f"RazorpayX {r.status_code}: {msg}", status=r.status_code,
                           retriable=r.status_code in (429, 500, 502, 503, 504))
    return data


def account_number() -> str:
    return (get_settings().razorpayx_account_number or "").strip()


def ping() -> dict:
    """Cheapest authenticated call: list 1 payout on our account. Proves keys + account number."""
    _call("GET", "/payouts", params={"account_number": account_number(), "count": 1})
    return config_state()


def create_contact(name: str, ref: str, email: str | None = None, phone: str | None = None) -> str:
    body = {"name": name[:50], "type": "employee", "reference_id": ref[:40]}
    if email:
        body["email"] = email
    if phone and phone.isdigit():
        body["contact"] = phone[-10:]
    return _call("POST", "/contacts", json=body)["id"]


def create_fund_account(contact_id: str, holder: str, ifsc: str, account: str) -> str:
    body = {"contact_id": contact_id, "account_type": "bank_account",
            "bank_account": {"name": holder[:120], "ifsc": ifsc, "account_number": account}}
    return _call("POST", "/fund_accounts", json=body)["id"]


def create_payout(fund_account_id: str, amount_paise: int, mode: str, purpose: str, reference_id: str,
                  narration: str, idempotency_key: str, notes: dict | None = None) -> dict:
    if not isinstance(amount_paise, int) or amount_paise <= 0:
        raise GatewayError("Amount must be a positive whole number of paise")
    body = {"account_number": account_number(), "fund_account_id": fund_account_id,
            "amount": amount_paise, "currency": "INR", "mode": mode.upper(), "purpose": purpose,
            "queue_if_low_balance": True, "reference_id": reference_id[:40],
            "narration": narration[:30], "notes": notes or {}}
    return _call("POST", "/payouts", json=body, headers={"X-Payout-Idempotency": idempotency_key})


def fetch_payout(payout_id: str) -> dict:
    return _call("GET", f"/payouts/{payout_id}")


def verify_webhook(raw_body: bytes, signature: str | None) -> bool:
    secret = get_settings().razorpayx_webhook_secret or ""
    if not secret or not signature:
        return False
    want = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(want, signature.strip())


def fingerprint(account: str, ifsc: str) -> str:
    return hashlib.sha256(f"{(account or '').strip()}|{(ifsc or '').strip().upper()}".encode()).hexdigest()
