# In-App Voice Calling — Windows Setup Guide (WebRTC + TURN)

RecoverIQ has **staff↔staff voice calling in the chat** (web). Open a 1:1 chat → tap **📞** in the header → the other person gets a ringing screen (accept/reject), then an in-call screen (mute / hang up / timer). This guide runs the **TURN relay natively on Windows**, reusing your existing **static public IP** (the same one the Dinstar sits behind), so calls connect even across different networks/mobile data.

---

## 1. How it works

- **Signaling** (offer/answer/ICE) rides your app's `/ws` socket — nothing extra to host.
- **Audio** is peer-to-peer WebRTC. It uses:
  - **STUN** — discovers public addresses; connects on same/lenient networks. No server needed (public STUN by default).
  - **TURN** — a relay for when NAT blocks a direct path (mobile data, strict NAT). **This is what you host on Windows.**
- The app fetches STUN/TURN from `GET /api/rtc/ice`. The server mints a **short-lived TURN credential** from a shared secret (nothing static is exposed).

---

## 2. Prerequisites

- A **Windows PC at the site that owns the static public IP** (the Dinstar's site), always-on, ideally on a UPS.
- Admin access to that site's **router** to add port-forwards.
- The **static public IP** (confirm it's truly public, not CGNAT — the Trickle-ICE test in §7 proves it).
- Your app backend already reachable over HTTPS (needed for mic access + signaling).

> The TURN server must run **on a PC behind that static IP's router** (you can't run it "on" the Dinstar box itself). It coexists with the Dinstar because it uses **different ports**.

---

## 3. Choose a small relay port range (makes Windows + router easy)

TURN normally uses a huge UDP relay range (49152–65535), which is painful to port-forward. We deliberately use a **small band** — plenty for dozens of simultaneous calls:

```
Relay UDP range: 49160–49200   (≈ 40 ports)
Signaling:       3478 UDP + 3478 TCP
```

Make sure this relay band does **not** overlap the Dinstar's RTP media range — if it does, pick another free band (e.g. 50000–50040) and use it consistently below.

---

## 4. Install eturnal (native Windows TURN server)

eturnal is a well-maintained STUN/TURN server with an **official Windows installer** and runs as a **Windows service**.

1. Download the Windows installer from **eturnal.net** (Downloads → Windows) and run it. It installs to `C:\Program Files\eturnal\` and registers a service named **eturnal**.
2. Edit the config file `C:\Program Files\eturnal\etc\eturnal.yml` (open Notepad **as Administrator**). Replace the whole `eturnal:` section with:

```yaml
eturnal:
  ## Shared secret — the app uses THIS to generate time-limited call credentials.
  ## Use a long random string; keep it identical to TURN_SECRET in the app (step 6).
  secret: "PUT_A_LONG_RANDOM_SECRET_HERE"

  ## Advertise your PUBLIC IP for relay candidates (this is the NAT fix — like coturn external-ip).
  relay_ipv4_addr: "YOUR_STATIC_PUBLIC_IP"

  ## Small relay range (must match the firewall + router forward below).
  relay_min_port: 49160
  relay_max_port: 49200

  listen:
    - ip: "::"
      port: 3478
      transport: udp
    - ip: "::"
      port: 3478
      transport: tcp

  ## Don't let the relay reach your internal network (safety).
  blacklist:
    - "127.0.0.0/8"
    - "10.0.0.0/8"
    - "172.16.0.0/12"
    - "192.168.0.0/16"
    - "169.254.0.0/16"

  log_level: info
```

3. Restart the service so the config loads:
   - Open **Services** (`services.msc`) → find **eturnal** → Restart. (Or in an admin PowerShell: `Restart-Service eturnal`.)

---

## 5. Open Windows Firewall + forward the router ports

**Windows Firewall** (admin PowerShell — one-time):

```powershell
New-NetFirewallRule -DisplayName "TURN 3478 UDP" -Direction Inbound -Protocol UDP -LocalPort 3478 -Action Allow
New-NetFirewallRule -DisplayName "TURN 3478 TCP" -Direction Inbound -Protocol TCP -LocalPort 3478 -Action Allow
New-NetFirewallRule -DisplayName "TURN relay UDP" -Direction Inbound -Protocol UDP -LocalPort 49160-49200 -Action Allow
```

**Router port-forwarding** — forward these from the static public IP to the Windows PC's **LAN IP** (e.g. 192.168.1.50):

| Port(s) | Protocol | Forward to (PC LAN IP) |
|---|---|---|
| 3478 | UDP | 192.168.1.50:3478 |
| 3478 | TCP | 192.168.1.50:3478 |
| 49160–49200 | UDP | 192.168.1.50:49160–49200 |

(Give that PC a **fixed LAN IP** via DHCP reservation so the forwards don't break on reboot.) These are all separate from the Dinstar's SIP/RTP forwards, so both work on the same IP.

---

## 6. Point RecoverIQ at the TURN server

In your backend environment (`app/backend/.env`, next to `run_local.bat`), add — using the **same secret** and **same public IP** as eturnal:

```
STUN_URL=stun:YOUR_STATIC_PUBLIC_IP:3478
TURN_URL=turn:YOUR_STATIC_PUBLIC_IP:3478
TURN_SECRET=PUT_A_LONG_RANDOM_SECRET_HERE
TURN_TTL_SECONDS=3600
```

Restart the backend. Now `GET /api/rtc/ice` returns STUN + a fresh, time-limited TURN credential, and the app uses them automatically. (Leaving `TURN_SECRET` blank = STUN-only: works same-network, not across strict NAT.)

---

## 7. Test

1. **Same office Wi-Fi:** two users → 1:1 chat → 📞 → accept → you should hear each other (STUN alone).
2. **Cross-network:** one on Wi-Fi, one on **mobile data** → call. Connects only if TURN is working.
3. **Prove TURN + the public IP:** open a "WebRTC Trickle ICE" test page, add server `turn:YOUR_STATIC_PUBLIC_IP:3478` with any username/password (for a raw reachability check use eturnal's own test, or temporarily set a static user). You want to see **`relay` candidates** appear. If you see `relay`, TURN is reachable on that IP → cross-network calls will work. No `relay` = recheck firewall, router forward, `relay_ipv4_addr`, and that the IP is truly public.

Watch the service log while testing: `C:\Program Files\eturnal\log\` (or the Event Log) shows allocations when a relayed call runs.

---

## 8. Notes & limits

- **HTTPS required** for the mic — your app is already HTTPS, so the browser will just prompt for mic permission on the first call.
- **1:1 only** for now (no group calls — that needs an SFU, a later phase).
- **Coexists with the Dinstar** on the same IP because ports differ; just keep the relay band clear of the Dinstar's RTP range.
- **Bandwidth:** ~40–100 kbps per call leg; a relayed call uses both legs on the TURN box — fine for many concurrent calls on a normal connection.
- **Native Android app:** this ships voice calling on **web (PWA)** only. The Android app needs the WebRTC library added — a separate, larger change (next phase).

---

## 9. Alternative (if you ever move off Windows)

The same thing runs on a small Linux VPS with **coturn**: `static-auth-secret=<same secret>`, `use-auth-secret`, `external-ip=<public ip>`, `min-port/max-port=49160-49200`. The app config is identical (`TURN_SECRET`, `TURN_URL`). Ask if you want that variant.

---

_Backend: `GET /api/rtc/ice` (STUN + time-limited TURN) and `type:"call"` relay over `/ws`. Frontend: the app-wide `VoiceCall` component + the 📞 button in each 1:1 chat._
