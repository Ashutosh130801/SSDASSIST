# RazorpayX salary payouts — setup (test mode first)

## 1. Get test keys (free, no KYC needed for test mode)
1. Sign up at https://x.razorpay.com and switch the Dashboard to **Test Mode**.
2. **Account Settings → API Keys → Generate Key** → copy Key ID (`rzp_test_…`) and Key Secret.
3. **My Account & Settings → Business banking**: copy the test **account number** (RazorpayX gives a test balance).
4. **Account Settings → Webhooks → Add webhook**
   - URL: `https://recoveriq.ssdenterprises.org.in/api/payouts/webhook/razorpayx`
   - Secret: type any long random text (you'll put the same text in .env)
   - Events: `payout.processed`, `payout.reversed`, `payout.failed`, `payout.rejected`, `payout.updated`, `payout.queued`, `payout.initiated`, `payout.pending`

## 2. Put them in `app/backend/.env` (never in chat, code, or the UI)
```
RAZORPAYX_KEY_ID=rzp_test_xxxxxxxxxxxx
RAZORPAYX_KEY_SECRET=xxxxxxxxxxxxxxxx
RAZORPAYX_ACCOUNT_NUMBER=xxxxxxxxxxxxxxxx
RAZORPAYX_WEBHOOK_SECRET=the-same-text-you-typed-in-the-dashboard
# optional caps (rupees)
PAYOUT_MAX_ITEM_RUPEES=200000
PAYOUT_MAX_BATCH_RUPEES=2500000
```
Restart the backend. Admin → **💸 Salary Payouts** → **Test connection**.

## 3. Going live later
- Complete RazorpayX KYC, fund the business account, generate **live** keys.
- Replace the keys in .env **and** add `RAZORPAYX_ALLOW_LIVE=true` (live keys are refused without it).
- Add the webhook again in Live mode (separate secret).
- Batches approved in test mode can never be sent with live keys (and vice-versa).

## Safety rules (enforced in code — see `app/routers/payouts.py`)
- Admin-only (not HO / techsupport / read-only). Approval needs password + 2FA (if on) + typing the exact total.
- After approval amounts and bank accounts are frozen; changed bank details → that payout is BLOCKED.
- Every payout has a stored idempotency key — resending / timeouts can never pay twice.
- One salary per employee per month across batches.
- Signed webhooks only (HMAC-SHA256), duplicates ignored, late events can't undo a final status.
- Every action is in the Audit Log.

Tests: `python -B tests/test_payouts.py` (fake gateway, no network).
