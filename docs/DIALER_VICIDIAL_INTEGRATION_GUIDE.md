# Connect RecoverIQ to ViciDial — What to provide & what to do

Your dialer stack is **ViciDial** (a predictive dialer on top of Asterisk + MySQL), and agents talk
on **Zoiper** registered to it. ViciDial already **places calls, records them, and logs dispositions**.
So RecoverIQ just needs to (a) trigger a dial for a case and (b) pull the recording + result back onto
that case. Nothing about your existing ViciDial/Zoiper/Dinstar setup changes.

You said you don't know ViciDial — that's fine. **Give Part A to whoever installed/hosts your ViciDial
(your dialer vendor or admin).** Part B is what happens in the ViciDial admin screens. Part C is what I
build on RecoverIQ. Part D is the test.

---

## PART A — Information to collect (give me these)

Ask your ViciDial admin / vendor for the following. This is all standard for ViciDial; they'll know it.

**1. ViciDial web address**
- The URL you open ViciDial admin on, e.g. `http://123.45.67.89/vicidial/admin.php` — I need the
  base: `http://123.45.67.89/`.
- Whether it's reachable from where RecoverIQ's server runs (same network, or a public IP/VPN).

**2. An API user** (ViciDial user with API access enabled)
- Username + password of a ViciDial user whose **User Level ≥ 8** and **"Agent API Access = 1"** and
  **"Vicidial API = 1"** are enabled (Part B shows where).
- Confirm the **RecoverIQ server's IP is allowed** to call the ViciDial API (ViciDial blocks API by IP).

**3. Recordings**
- Confirm **call recording is ON** for the campaign (Recording = ALLCALLS). 
- The **URL where recordings are served**, e.g. `http://123.45.67.89/RECORDINGS/MP3/` or
  `http://123.45.67.89/RECORDINGS/`. (Open one recording in a browser to confirm it plays.)

**4. Read‑only database access** (best option for pulling recordings + results)
- MySQL host/IP + port (usually 3306), database name (usually **`asterisk`**), and a **read‑only**
  username/password. Confirm the RecoverIQ server IP is allowed to connect to MySQL.
- If they can't give DB access, that's OK — we fall back to ViciDial's non‑agent API for lookups
  (slightly less rich). Tell me which.

**5. Which campaign + list** RecoverIQ cases should dial into
- The **campaign_id** (e.g. `RECOVER1`) agents log into, and a **list_id** we can push cases into as
  leads (e.g. `999`). If none exists, the admin creates an empty list for RecoverIQ (Part B).

**6. Agent mapping**
- The **ViciDial user id** for each collections agent (so RecoverIQ knows "RecoverIQ user X = ViciDial
  agent 1001"). A simple name↔vicidial-user list is enough.

**7. Dial prefix / number format**
- How numbers must be sent to dial out (e.g. do they prepend a `9`, or country code `91`?). Ask the
  admin what an agent types to dial a normal 10‑digit mobile.

**8. (If hosted by a vendor)** — ask them to simply **"enable ViciDial Agent API + Non‑Agent API for
  our server IP, turn on call recording, and give a read‑only DB user."** That one sentence covers most
  of the above.

> That's everything from your side. Send me items 1–7 and I can build and wire the rest.

---

## PART B — What to switch on inside ViciDial (admin screens)

For your admin (menu paths in ViciDial admin.php). ~15 minutes.

1. **Enable API on the user** — Admin → **Users** → open the API user → set:
   - `User Level` = **9**, `Agent API Access` = **1 - Enabled**, `Vicidial API` = **1 - Enabled** → Save.
2. **Allow the RecoverIQ server IP** — Admin → **System Settings** (or the campaign's API settings) →
   add RecoverIQ's server IP to the allowed API IP list.
3. **Turn on recording** — Admin → **Campaigns** → your campaign → Detail → **Recording = ALLCALLS**
   (or ALLFORCE) → Save. Confirm recordings appear under the RECORDINGS URL after a test call.
4. **Create a list for RecoverIQ** (if needed) — Admin → **Lists** → Add a new list (note its
   `list_id`) under your campaign. RecoverIQ will inject cases here as leads.
5. **Confirm DB reachability** — give the RecoverIQ server IP `SELECT` grants on the `asterisk`
   database (tables we read: `vicidial_list`, `vicidial_log`, `vicidial_closer_log`, `recording_log`).

Nothing else in ViciDial needs changing — campaigns, Zoiper, and the Dinstar trunk stay as they are.

---

## PART C — What I build on the RecoverIQ side

You don't do anything here; this is my work once Part A is provided.

1. **Config fields** — a "ViciDial user" field on each RecoverIQ agent + server settings for the
   ViciDial URL, API user/pass, recordings URL, DB creds (all stored server‑side, encrypted).
2. **Connector service** (small, runs next to RecoverIQ):
   - **Click‑to‑call:** RecoverIQ Call button → connector → ViciDial **agent API `external_dial`**
     with the customer number + `vendor_lead_code = case_id`. The agent's Zoiper rings and dials.
   - **Lead push (optional):** send cases into the RecoverIQ list via **non‑agent API `add_lead`** with
     `vendor_lead_code = case_id`, so results map back exactly.
   - **Recording + result poller:** every few seconds, read new finished calls (from `recording_log` +
     `vicidial_log`/`vicidial_closer_log`, joined to `vicidial_list` for the `vendor_lead_code`), and
     **POST to RecoverIQ `/api/integration/calls`** with the recording URL, disposition, duration, agent.
3. **Case history player** — add `recording_url` to the call log + a small **audio player** in the case
   History timeline, so a finished call is playable right on the case.
4. **Connections entry** — register the connector in RecoverIQ → Connections (already‑built screen), so
   the Call buttons/panels light up.

---

## PART D — Test (once wired)

1. Log an agent into ViciDial (Zoiper connected) as usual.
2. In RecoverIQ, open a case → **📞 Call** → the agent's Zoiper rings and dials the customer via the
   Dinstar SIMs.
3. Talk, then hang up.
4. Within a few seconds the case **History** shows the call with **disposition + a playable recording**.
5. If manual dials (typed in ViciDial, not from RecoverIQ) should also attach, the connector matches
   them by number + agent + time.

---

## Notes / expectations

- **Correlation:** pushing `vendor_lead_code = case_id` (Part C) makes recording↔case matching exact.
  Without it, matching is by phone number + time (approximate).
- **Concurrency:** still capped by your Dinstar SIM/channel count — ViciDial already respects that.
- **Security:** keep ViciDial + DB on the LAN/VPN; only the connector talks to them. Recordings should
  be served behind auth or reached server‑to‑server, not exposed publicly.
- **Recording format:** ViciDial serves WAV and/or MP3; the player handles both.

---

### The short version of what you must provide
1. ViciDial URL (+ is it reachable from our server)  
2. API user + password (API access enabled, our IP allowed)  
3. Recordings URL (confirm one plays)  
4. Read‑only MySQL host/db/user/pass (or say "use non‑agent API")  
5. Campaign id + a list id for RecoverIQ  
6. Agent → ViciDial‑user mapping  
7. Dial prefix / number format

Send those and I'll build the connector + the case‑history recording player and wire it into RecoverIQ.
