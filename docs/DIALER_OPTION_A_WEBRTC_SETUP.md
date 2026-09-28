# RecoverIQ In‑App Dialer — Option A (WebRTC softphone over your existing Asterisk + Dinstar)

**Goal:** stop using Zoiper as a separate app. RecoverIQ (web + Android) becomes the softphone: the
agent taps **Call** on a case, the browser/app rings, the customer is dialed out through the Dinstar
UC2000 SIMs, they talk, and the recording lands back on the case.

**What already exists (from your setup):** Zoiper registers and places calls → so an **Asterisk**
SIP server is already in front of the Dinstar, with agent extensions and an outbound route through
the gateway. Option A reuses all of that. The only new things are (1) turning on **WebRTC** in
Asterisk, (2) a **TURN server**, (3) serving RecoverIQ over **HTTPS**, and (4) the in‑app softphone
UI + a small **connector** for recordings.

```
Agent (RecoverIQ web/app, WebRTC)  ──WSS/DTLS‑SRTP──▶  Asterisk  ──SIP trunk──▶  Dinstar UC2000 ──▶ SIM ──▶ customer
                                                          │
                                                    MixMonitor recording
                                                          │
                                                   Connector ──▶ POST /api/integration/calls (recording URL) ──▶ case history
```

---

## Prerequisites / requirements checklist

- [ ] Asterisk 18/20 reachable on the LAN (the one Zoiper already talks to). Confirm with the agent's
      Zoiper account: the **Domain/registrar** IP is your Asterisk.
- [ ] Root/SSH access to the Asterisk box.
- [ ] A **DNS name** for Asterisk that agents' browsers can reach (e.g. `pbx.yourcompany.in`) — WebRTC
      needs WSS with a valid TLS certificate. A LAN‑only name works if you install a proper cert.
- [ ] **coturn** (TURN/STUN) installable on a box reachable by agents (can be the same server).
- [ ] RecoverIQ served over **HTTPS** (already the case if you use the Cloudflare tunnel / real cert).
- [ ] The Dinstar trunk + outbound route in Asterisk already working (Zoiper proves this).
- [ ] One test agent extension you can experiment with.

> Ports to open (firewall): **8089/tcp** (Asterisk WSS), **3478/udp+tcp** and **5349/tcp** (coturn),
> **49152–65535/udp** (RTP/TURN relay). Keep 5060 for the Dinstar trunk on the LAN only.

---

## Step 1 — Confirm the current setup

1. Open the Asterisk CLI: `sudo asterisk -rvvv`
2. See the registered agent: `pjsip show endpoints` (or `sip show peers` if it's chan_sip — if so,
   plan to add a **PJSIP** WebRTC endpoint; chan_sip can't do WebRTC).
3. Note one working **extension number + password** and the **outbound dialplan context** that reaches
   the Dinstar (the context Zoiper uses to dial out).

---

## Step 2 — Enable the Asterisk HTTP/WebSocket server

Edit `/etc/asterisk/http.conf`:

```ini
[general]
enabled=yes
bindaddr=0.0.0.0
tlsenable=yes
tlsbindaddr=0.0.0.0:8089
tlscertfile=/etc/asterisk/keys/fullchain.pem     ; your real TLS cert (Let's Encrypt etc.)
tlsprivatekey=/etc/asterisk/keys/privkey.pem
```

Reload: `asterisk -rx "module reload http"` then check `asterisk -rx "http show status"` (expect a
TLS server bound on 8089).

---

## Step 3 — Create DTLS certs for media (SRTP)

WebRTC media is encrypted with DTLS‑SRTP. Generate a cert Asterisk uses for the media handshake:

```bash
cd /etc/asterisk/keys
# Uses the bundled helper; or use your own openssl cert
/usr/src/asterisk*/contrib/scripts/ast_tls_cert -C pbx.yourcompany.in -O "YourCompany" -d /etc/asterisk/keys
```

You'll get `asterisk.pem` etc. (Any valid cert works; self‑signed is fine for DTLS media, but the
**WSS** cert in Step 2 should be a real/trusted one so browsers don't block it.)

---

## Step 4 — Add a WebRTC transport + agent endpoints (PJSIP)

Edit `/etc/asterisk/pjsip.conf`. Add the WebSocket transport once:

```ini
[transport-wss]
type=transport
protocol=wss
bind=0.0.0.0
```

For **each agent**, define a WebRTC‑capable endpoint (template makes it easy):

```ini
[webrtc-agent](!)
type=endpoint
context=from-internal              ; the context that can dial your Dinstar outbound route
disallow=all
allow=opus,ulaw,alaw
webrtc=yes                         ; sets DTLS, ICE, rtcp_mux, avpf automatically on Asterisk 18+
direct_media=no

[6001](webrtc-agent)               ; agent extension number
type=endpoint                       ; (the (!) template + these lines; simplest is per-agent blocks)
auth=6001-auth
aors=6001

[6001-auth]
type=auth
auth_type=userpass
username=6001
password=STRONG_PER_AGENT_SECRET

[6001]
type=aor
max_contacts=1
```

Repeat per agent (6002, 6003, …). Reuse the **same extension numbers your agents already have in
Zoiper** so their outbound routing/CDR stays identical — just make them `webrtc=yes`.

Reload: `asterisk -rx "pjsip reload"` → `pjsip show endpoints` should list them.

---

## Step 5 — Stand up coturn (TURN/STUN)

Install and configure `/etc/turnserver.conf`:

```ini
listening-port=3478
tls-listening-port=5349
fingerprint
lt-cred-mech
use-auth-secret
static-auth-secret=A_LONG_RANDOM_SHARED_SECRET
realm=pbx.yourcompany.in
min-port=49152
max-port=65535
cert=/etc/asterisk/keys/fullchain.pem
pkey=/etc/asterisk/keys/privkey.pem
```

Start it: `systemctl enable --now coturn`. RecoverIQ's softphone will use short‑lived TURN
credentials derived from `static-auth-secret` (time‑limited, generated by the backend).

---

## Step 6 — Store each agent's SIP credentials in RecoverIQ

Add fields to the user record (admin/HR‑set in Manpower): **SIP extension**, **SIP password**, and the
shared **Asterisk WSS URL** + **TURN secret** live in server config (not per user). At login,
RecoverIQ returns the agent their SIP extension/password + the WSS URL + a freshly‑minted TURN
credential — so secrets aren't hard‑coded in the app.

> This is the main RecoverIQ backend change: a small `/api/telephony/config` endpoint that returns
> `{ wss_url, sip_ext, sip_password, turn_urls, turn_user, turn_cred, expires }` for the signed‑in
> agent, plus the admin fields to set the extension/password.

---

## Step 7 — Embed the WebRTC softphone in RecoverIQ (web)

Add a SIP client (**SIP.js** or **JsSIP**) into the web app:

1. On login (for caller/FOS roles), fetch `/api/telephony/config`.
2. Create a `UserAgent` that connects to `wss://pbx.yourcompany.in:8089/ws`, registers the agent's
   extension, and passes the TURN servers into the RTCPeerConnection config.
3. Add a floating **call bar / dialpad**: dial, answer, mute, hold, DTMF keypad, hang‑up, call timer.
4. Rewire the case **📞 Call** button: instead of `tel:`/Zoiper, place the call in‑page
   (`userAgent.invite('sip:<customer_number>@pbx...')`) — Asterisk routes it out the Dinstar.
5. Ask for microphone permission once; show mic/network status in the bar.

(Native Android: use the **Linphone SDK** or **PJSIP** to register the same extension and place calls
in‑app — same config endpoint.)

---

## Step 8 — Turn on recording + wire it to case history

1. In the outbound dialplan (the context that dials the Dinstar), add **MixMonitor** so every call is
   recorded to a folder, filename keyed by the case/agent, e.g.
   `Set(MIXMON_DIR=/var/spool/asterisk/recordings)` + `MixMonitor(${UNIQUEID}.wav)`.
2. Serve that folder over HTTPS (behind auth) so recordings have a URL.
3. Deploy the **connector** (small FastAPI service) with Asterisk **AMI/ARI** access + a RecoverIQ
   `X‑Integration‑Key`. On each hangup it posts to `POST /api/integration/calls`:
   `{ contact_id, agent_emp_code, disposition, recording_url, ... }`.
4. Add `recording_url` to the CallLog + an audio player in the case **History** timeline (small
   RecoverIQ change) so the finished call is playable on the case.

---

## Step 9 — Register the connector in RecoverIQ

RecoverIQ → **Connections** → Add dialer → base URL of the connector + the integration key. The
click‑to‑call widgets and dialer panels light up automatically (the integration layer already exists).

---

## Step 10 — Test end‑to‑end (one agent)

1. Log in to RecoverIQ as the test agent over **HTTPS**; allow the mic.
2. Confirm the call bar shows **Registered** (Asterisk CLI: `pjsip show contacts` shows the browser).
3. Open a case → **📞 Call** → you hear ringback → customer's phone rings via the Dinstar SIM →
   talk → hang up.
4. Check the case **History**: a call log appears with the **recording** playable.
5. `pjsip set logger on` on Asterisk if anything fails, to see the SIP/WebRTC negotiation.

---

## Step 11 — Roll out

- Set every agent's SIP extension/password (reuse their Zoiper extensions).
- Cap concurrent calls to the number of **live SIMs** in the UC2000 (32 max on the VG‑32G).
- Set **recording retention** and storage.
- Remove Zoiper from agent machines once RecoverIQ calling is verified.
- Keep Asterisk + Dinstar on the LAN; agents reach Asterisk's **WSS** over HTTPS/VPN if remote.

---

## Troubleshooting quick hits

| Symptom | Likely cause | Fix |
|---|---|---|
| Softphone won't register | Wrong WSS URL or cert not trusted | Use a real TLS cert on 8089; URL `wss://host:8089/ws` |
| Registers but no audio | No/again TURN | Verify coturn running, ports 3478/49152‑65535 open, TURN creds valid |
| One‑way audio | NAT / ICE | Ensure `webrtc=yes`, `ice_support=yes`, TURN reachable both ways |
| Call connects, no recording | MixMonitor not in the dial path | Add MixMonitor to the outbound context; check folder perms |
| "Not secure / mic blocked" | RecoverIQ not on HTTPS | Serve the app over HTTPS (browsers block mic on http) |

---

## What RecoverIQ needs built (our side, when you're ready)

1. `/api/telephony/config` endpoint + admin fields for SIP extension/password (Step 6).
2. In‑app **WebRTC softphone** (web SIP.js call bar; native Linphone/PJSIP) (Step 7).
3. `recording_url` on CallLog + **audio player in case History**, and the **connector** service
   (Steps 8–9).

Everything else in this guide is Asterisk / coturn / Dinstar configuration on your infrastructure.
