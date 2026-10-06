# Connect RecoverIQ to your existing ViciDial

This lets your callers keep using **Zoiper → ViciDial** exactly as they do today. RecoverIQ
just adds a **Call** button on each case that tells ViciDial to dial, and ViciDial sends the
**disposition + call recording** back onto the case automatically. **No self-hosted dialer is
needed.**

There are three capabilities, and you can turn them on in order:

1. **Click-to-call** — caller clicks *Call* in RecoverIQ → the number dials out on their Zoiper.
2. **Results back** — after each call, ViciDial posts the disposition + recording link to the case.
3. **Campaign push** (optional, later) — push a portfolio into a ViciDial list for predictive dialing.

---

## What you need before you start

Collect these from your ViciDial admin:

- **ViciDial URL** — the web address/IP of the ViciDial server, e.g. `http://192.168.1.50`
  (use the LAN IP callers already reach; add `https://` only if your ViciDial has SSL).
- **An API user + password** — a ViciDial user with, in *Admin → Users → (that user)*:
  - `User Level` = **8** or **9**
  - `API Access` = **1**
  - `Agent API Access` = **1**
  This is the account RecoverIQ logs in as. Don't reuse a normal agent login.
- **Each caller's ViciDial agent user id** — the login your callers type into the ViciDial agent
  screen (e.g. `8001`). You'll map each RecoverIQ employee code to it (e.g. `TC001 = 8001`). If your
  ViciDial agent logins are the *same* as the RecoverIQ emp codes, you can skip the map.
- *(For campaign push only)* a **List ID** and **Campaign ID** in ViciDial to load leads into.
- *(For recordings)* the **recording URL base** — where ViciDial serves recordings over the web,
  usually `http://<vici-ip>/RECORDINGS/MP3` (ViciDial must have web recording access enabled).

---

## Step 1 — Save the connection in RecoverIQ

1. Log in to RecoverIQ as **Admin** or **Head Office**.
2. Go to **Connections** (🔌 in the menu).
3. In the **☎️ ViciDial (existing office dialer)** card, fill in:
   - **ViciDial URL**, **API user**, **API password**
   - **Phone code** (India = `91`)
   - **Source tag** — leave as `recoveriq`
   - **Recording URL base** — e.g. `http://192.168.1.50/RECORDINGS/MP3` (optional but needed to
     play recordings inside RecoverIQ)
   - **List ID / Campaign ID** — only if you'll use campaign push
   - **Agent map** — one line per caller, `EMPCODE=viciuser`, e.g.
     ```
     TC001=8001
     TC002=8002
     ```
4. Click **Save ViciDial connection**.
5. A **Dispo Call URL** box appears — **copy it** (Step 3 uses it).
6. Click **Test** on the connection row — it should say *Reachable ✓*. If not, re-check the URL and
   API user level/flags.

You can edit any field later and save again. Leave the password blank on a later save to keep the
existing one.

---

## Step 2 — Click-to-call (dials on the caller's Zoiper)

Nothing more to configure. For a call to ring the caller's phone, that caller must be **logged into
the ViciDial agent screen** (`vicidial.php`) with Zoiper registered and sitting in a campaign — the
same way they work today.

In RecoverIQ, opening a case now shows a **Call** button. Clicking it calls ViciDial's agent API
(`external_dial`) for that caller's session, and ViciDial dials the customer and bridges them to the
agent's Zoiper.

If a caller sees *"make sure the agent is logged into the ViciDial agent screen"*, they simply need
to log into ViciDial first.

---

## Step 3 — Get disposition + recording back (one-time ViciDial setting)

So that every call's outcome and recording flow back onto the case:

1. In **ViciDial Admin → Campaigns →** (the campaign your callers use).
2. Find **"Dispo Call URL"** (sometimes under campaign detail / web form settings).
3. Paste the **Dispo Call URL** you copied in Step 1. It looks like:
   ```
   https://<your-recoveriq-domain>/api/integration/vicidial/dispo?key=XXXX&case=--A--vendor_lead_code--B--&dispo=--A--dispo--B--&rec=--A--recording_filename--B--&agent=--A--user--B--&phone=--A--phone_number--B--&len=--A--talk_sec--B--
   ```
   ViciDial fills in the `--A--…--B--` tokens automatically for each call.
4. Save the campaign.

From then on, after a caller dispositions a call in ViciDial, RecoverIQ records a call entry on the
case with the **disposition** and a **🎙 recording link** (if the recording base is set). Matching
works because click-to-call tags each call with `vendor_lead_code = the RecoverIQ case id`.

> Note: the case is matched by `vendor_lead_code`. Click-to-call sets this for you. For
> campaign-pushed leads it's set at push time (Step 4).

---

## Step 4 — Campaign / predictive push (optional, later)

To hand a whole portfolio to ViciDial for auto-dialing:

1. Make sure **List ID** (and Campaign) are set on the connection (Step 1), and the ViciDial
   campaign is set to the dial method you want (RATIO / ADAPT) and is **active**.
2. In RecoverIQ **Portfolios**, filter to the bank/product/month you want to call.
3. Click **☎ Send to ViciDial** → confirm. RecoverIQ injects those cases into the ViciDial list as
   leads (`add_lead`), each tagged with its case id.
4. ViciDial predictive-dials the list and connects answered calls to logged-in agents. Outcomes and
   recordings still flow back via the Step 3 Dispo URL.

Leads are de-duplicated against the list, paid/closed cases are skipped, and numbers are normalised.

---

## Credentials summary (what goes where)

| Setting | Where to get it | Used for |
|---|---|---|
| ViciDial URL | Your ViciDial server address | all |
| API user + password | ViciDial user, level 8–9, API+Agent API = 1 | click-to-call, push, test |
| Agent map (emp=viciuser) | Your caller ↔ ViciDial agent logins | click-to-call targeting |
| List ID / Campaign ID | ViciDial admin | campaign push |
| Recording URL base | ViciDial recordings web path | playing recordings in RecoverIQ |
| Dispo Call URL | Generated by RecoverIQ (Step 1) | results/recordings back |

---

## Troubleshooting

- **Call button says "no agent mapped"** → add the caller's `EMPCODE=viciuser` line in the agent map.
- **"agent not logged in"** → the caller must log into the ViciDial agent screen first.
- **Test fails** → check the ViciDial URL is reachable from the RecoverIQ server, and the API user
  has level 8–9 with API + Agent API access = 1.
- **No recordings appear** → set the Recording URL base, and confirm ViciDial serves recordings over
  the web (web recording access enabled) and the filename token is in the Dispo URL.
- **Results not coming back** → confirm the Dispo Call URL is pasted on the *active* campaign and
  that your RecoverIQ domain is reachable from the ViciDial server.
