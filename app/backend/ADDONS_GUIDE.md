# ⚙️ Services & 🧩 Add-ons — setup guide

Two new buttons sit under your name in the top-right corner:

- **⚙️ Services** (Admin only) lists every part of RecoverIQ. You can switch each one on or off and change its settings. When a service is off, it disappears from everyone's menu and its API answers *"turned off by your administrator"*. The data is kept. Services marked *always on* (Accounts, Team, Audit) can't be switched off.
- **🧩 Add-ons** (everyone) opens the extra modules. Each one has its own sub-section. People only see the add-ons their role is allowed to use.

New add-ons start **OFF**. Switch them on in ⚙️ Services when you are ready. AI Assist stays on, because it was already in use.

**API keys** (Gemini / OpenRouter, Razorpay, MSG91 / WhatsApp) can be entered by the Admin in ⚙️ Services → the add-on's ⚙ Settings. They're stored encrypted, never shown again (only the last 4 characters), can be replaced or removed any time, and every change is in the Audit Log. A key set in the server `.env` is used when none is saved in the app. Live Razorpay keys still need `RAZORPAY_ALLOW_LIVE=true` in `.env`. Changing the server's `SECRET_KEY` makes saved keys unreadable — re-enter them.

---

## ✨ AI Assist
It answers questions in plain words, using only the data the user is allowed to see. It can:

- make Excel, PDF and Word files
- write guides, letters and SOPs
- explain how to use RecoverIQ
- suggest actions, such as setting a follow-up. An action runs only after the user taps **Confirm**.

| Setting | Meaning |
|---|---|
| Provider | `local` (your own server), `gemini`, `openrouter` |
| Mask PII | Phone and account numbers reach the AI as `XXXXXX1234`. Files made for the user still contain the full numbers. |
| Daily limit | Questions per user per day |

**Data areas.** AI Assist can also read the Audit Log and DPR upload history, MIS breakdowns and the daily collection trend, litigation and legal notices, settlements and payment links, team leads, and devices. Each user only gets what their role shows on screen. Each area has its own **AI data access** switch in ⚙️ Services → AI Assist.

**Visual answers.** Ask for a *dashboard* or a *chart* and the answer comes back as KPI cards, bar, line or doughnut charts, tables and step diagrams. They are drawn from the real tool results, not from numbers the model typed. Each visual has full-screen, PNG and Excel buttons. Every answer also ends with follow-up suggestions, plus a "steps" toggle that shows which data was read. To turn visuals off, untick **Allow visual answers**.

**Floating helper bot.** A small robot sits bottom-right on every page. You can drag it anywhere, and it remembers where you put it. Click it to open the chat. It reads the open page as text (with the same masking), so it can explain the screen, answer about it and guide you. In Services you can:
- turn the bot off
- stop it reading pages
- pick its look: **CSS 3D** (default, light) or **Full 3D (three.js)** (richer, heavier on low-end PCs)

### Running an open-weight model on the server PC (no data leaves the office)
1. Install **Ollama** from https://ollama.com (Windows installer).
2. Download a model that can call tools. Pick one by how much memory you have:
   - `ollama pull qwen2.5:14b` for about 16 GB of RAM or VRAM (recommended)
   - `ollama pull qwen2.5:7b` for 8 GB
   - `ollama pull llama3.1:8b` is another 8 GB option
3. Ollama serves `http://127.0.0.1:11434/v1` automatically.
4. In ⚙️ Services → AI Assist, set the provider to **Local model**, the model to `qwen2.5:14b`, and the URL to `http://127.0.0.1:11434/v1`.

A GPU (for example an RTX 3060 12 GB or better) makes answers come back in seconds. On a CPU alone, expect 20–60 s per answer.
**vLLM** and **LM Studio** also work, because they serve the same OpenAI-compatible `/v1` API.

## 🛡️ Compliance guardrails
- **Contact hours.** RBI fair-practice default is 08:00–19:00. Dialling (click-to-call) outside these hours is **blocked**. Calls and visits *logged* outside the hours are kept but **flagged**.
- **Attempt caps.** Limits on calls per customer per day and visits per week.
- **Agent certification register** (for example IIBF DRA), with expiry dates. You can optionally block agents who are not certified.
- **DPDP data requests**: access, correction, erasure or grievance, each with a due date. Erasure is allowed only after the account is closed or paid. Only Admin can do it, and you must type `ERASE` to confirm.
- **Retention.** You can erase the personal details of old cases after N months. Amounts and history stay, so MIS still works.

## 💳 Payment links & auto-reconciliation
```
RAZORPAY_KEY_ID=rzp_test_xxx
RAZORPAY_KEY_SECRET=xxx
RAZORPAY_WEBHOOK_SECRET=choose-a-long-random-string
PUBLIC_BASE_URL=https://recoveriq.ssdenterprises.org.in
# RAZORPAY_ALLOW_LIVE=true   ← only after testing; live keys are refused until this is set
UPI_VPA=yourcompany@axisbank          # for "Plain UPI link" mode
```
- In the Razorpay Dashboard → Webhooks, add `https://<your domain>/api/paylinks/webhook`. Use the same secret as `RAZORPAY_WEBHOOK_SECRET` and tick the events `payment_link.paid` and `payment_link.partially_paid`. Paid links then post into the case on their own, once only.
- **Plain UPI** mode costs nothing. To reconcile, upload your bank statement in **Reconcile statement**. Credits are matched by the link note, the UTR the customer reported, or the account number plus the amount.
- **The customer's page** is `/pay/<token>`. It shows a masked name, the last 4 digits of the account, the amount due, a pay button, and a box for entering a UTR. It never shows the full phone number or account number.

## 📣 Digital outreach journeys
Triggers:
- days before the close date
- days around the PTP date
- a day of the month

Steps can be WhatsApp or SMS messages, with placeholders. Each message is created at most once and follows the daily cap and the contact hours.

Without a provider, messages go to **"To send by hand"**. Send them with one click on WhatsApp, or export them as a CSV.

Optional providers (in `.env`):
```
WHATSAPP_TOKEN=...   WHATSAPP_PHONE_ID=...    # WhatsApp Cloud API — also set the approved template name in Services
MSG91_AUTH_KEY=...                            # SMS — also set the DLT flow/template id in Services
```
To run journeys every day at 10 am, turn on **Run journeys automatically** in Services.

## 🤝 Settlement / OTS
- An offer is checked against the outstanding amount on the case. The waiver % decides who has to approve it, based on the limits set in Services.
- Nobody can approve their own offer. Admin's offers are approved automatically.
- Each offer can have instalments, ticked off as they are paid, and a PDF settlement letter.
- An offer never changes the balance. The money still comes in through payments, DPR or payment links.

## 🧠 Smart allocation & route plan
- **Likelihood-to-pay score.** Shown with the reasons behind it and the best time to call.
- **Allocation suggestions.** FOS are picked by distance from their last GPS point and capacity. Callers are picked by workload. Nothing changes until you review the list and click **Allocate**. The normal reassign rules and audit apply.
- **Route plan.** Visits with a PTP due come first, then the highest score, then the nearest next stop. You can open the whole route in Google Maps.

## 📨 Legal notices (bulk)
- Templates: demand, Sec 138 NI Act, pre-arbitration, and pre-SARFAESI. All are editable. **Have your advocate approve the wording.**
- Each batch is one PDF, with a reference number per notice.
- Mark notices as dispatched, delivered or returned, or upload the tracking sheet. Every notice is recorded in the case history.

## 📊 Advanced analytics
- Resolution by bank, product and bucket
- Roll-back or roll-forward (the same account, last month compared with this month)
- Contact rate and the share of PTPs kept
- Best hours to call
- Agent productivity
- Month-end forecast

## 🧾 Agency billing & invoices
- Commission rates per bank, product and bucket. A rate can be a % of collection, ₹ per paid case, or a fixed monthly fee.
- Invoices go draft → issued (number `PREFIX/FY/0001`) → paid.
- The invoice PDF shows GST split into CGST+SGST, or as IGST.

## 🔎 Skip tracing
Finds other numbers and addresses for customers you can't reach, using **only your own data**:
- the same customer's other loans
- numbers your team updated
- addresses found on visits

**Use as new number** saves the lead to the case and records it in the history.

## 🔌 Open API & webhooks
- **API keys.** Each key is shown once and stored as a hash. Give each key scopes (`cases:read`, `payments:write`, `events:read`, `pii`) and, if you want, limit it to certain banks.
  ```
  curl -H "Authorization: Bearer riq_xxx" https://<domain>/api/open/v1/cases?bank=AXIS
  curl -X POST -H "Authorization: Bearer riq_xxx" -H "Content-Type: application/json" \
       -d '{"account_no":"AC123","amount":5000,"mode":"NEFT","reference":"UTR123"}' https://<domain>/api/open/v1/payments
  ```
  Payments are idempotent by `reference`, so sending the same call twice is safe.
- **Webhooks.** Only public `https` addresses are accepted. Each delivery is signed with `X-RecoverIQ-Signature: sha256=HMAC(secret, body)`. Failed deliveries are retried up to 6 times.
- Events: `payment.received`, `ptp.created`, `call.logged`, `visit.logged`, `settlement.approved`, `paylink.paid`.

## 🔔 Coming soon (shown as reminder cards)
- **AI on calls**: transcripts, PTP and dispute detection, quality scores. This needs the call-audio integration.
- **AI voice bot**: reminder and PTP-confirmation calls in Telugu, Hindi and English.
