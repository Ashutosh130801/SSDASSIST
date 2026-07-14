# Run locally + test with real users on a free public URL

Use this to run the app on your own PC, create the first admin, add a few test users, and give
them a link they can open from anywhere — no cloud account, no cost.

---

## 1. Run it on your computer

**One-time:** install **Python 3.11+** from https://www.python.org/downloads/ — during install,
tick **"Add python.exe to PATH"**.

**Start the app:**
- **Windows:** open the `app\backend` folder and **double-click `run_local.bat`**.
- **Mac/Linux:** in Terminal, run `bash app/backend/run_local.sh`.

The first run installs everything (1–2 min), creates the database, seeds the admin, and starts the
server. When you see it running, open **http://localhost:8000** in your browser.

> It uses a local file database (`ssd_local.db`) — no Postgres needed for testing. Press
> **Ctrl+C** in that window to stop the app.

---

## 2. The first admin login

`run_local` automatically creates the administrator for you:

- **Email:** `admin@ssdrecovery.in`
- **Password:** `admin123`

**To use your own admin email/password instead**, create one with the management tool (run from
`app\backend`, in a terminal where the app's `.venv` is active):
```
python manage.py create-user --name "Your Name" --email you@yourco.com --role admin --password "StrongPass!23"
```
Then log in with that. (You can also just log in with the default admin and change details under
**Team**.)

---

## 3. Add your test users

Sign in as admin → **Team → + Add staff**. Create one login per tester and pick their role
(**Collections Manager**, **Field Agent**, **Tele-calling Agent**). Give each a password and share
it with that tester. That's all they need to log in.

> Prefer the command line? `python manage.py create-user --name "Ravi" --email ravi@yourco.com
> --role fos --password "Field!234" --branch Visakhapatnam`

---

## 4. Let testers reach it — pick one

### Option A — same office/Wi-Fi (simplest, no tools)
Find your PC's local IP: on Windows run `ipconfig` (look for **IPv4 Address**, e.g.
`192.168.1.24`). Anyone on the **same Wi-Fi** opens `http://192.168.1.24:8000`. No domain needed.
(Windows may ask to **Allow** the app through the firewall the first time — click Allow.)

### Option B — a free public HTTPS link (works from anywhere) — recommended
Use **Cloudflare Tunnel** — free, no signup, gives an `https://…trycloudflare.com` address.

1. Install it once:
   - Windows: `winget install --id Cloudflare.cloudflared`
   - Mac: `brew install cloudflared`
2. Keep the app running (step 1). In a **new** terminal window run:
   ```
   cloudflared tunnel --url http://localhost:8000
   ```
3. It prints a line like `https://brave-lion-xyz.trycloudflare.com` — **share that link** with your
   testers. It works on their phones/laptops from any network.

> The link lives only while that window stays open, and changes each time you run it. That's fine
> for a test session.

### Option B2 — a stable free subdomain (ngrok)
If you want the **same** URL every time, use **ngrok**:
1. Sign up free at https://ngrok.com, install it, then `ngrok config add-authtoken <your token>`.
2. Claim your free static domain in the ngrok dashboard, then run:
   ```
   ngrok http --url=your-name.ngrok-free.app 8000
   ```
3. Share `https://your-name.ngrok-free.app`.

---

## 5. Important notes for a good test

- **Keep your PC on** with the app window (and the tunnel window) running — if you close them or the
  PC sleeps, the link stops working.
- **HTTPS is automatic** with the tunnel, so **live GPS tracking** and **passkeys/biometric** will
  work on testers' phones (browsers only allow those on secure `https://` pages). For passkeys,
  start the app with `WEBAUTHN_ORIGIN=https://your-tunnel-url` and `WEBAUTHN_RP_ID=your-tunnel-host`.
- **Maps look blank without a key.** To test the map/route features, add a Google Maps key
  (`GOOGLE_MAPS_API_KEY`) and allow your tunnel URL on the key. Everything else works without it.
- **New-device prompt:** each tester's first device is auto-approved. If someone logs in from a
  second device they'll see "awaiting approval" — you approve it under **Devices** as admin.
- This is for **testing** — the local file database is easy to reset (delete `ssd_local.db`). When
  you're ready for always-on real use, move to a host (see `PRODUCTION_GUIDE.md` /
  `DEPLOYMENT_HANDBOOK.md`, or the free Neon + Koyeb option).

---

## How to set custom env values on Windows before starting

If you want to set your own admin, secret, or WebAuthn values, open **PowerShell** in `app\backend`
and run (then start uvicorn yourself instead of the .bat):
```
.\.venv\Scripts\activate
$env:DATABASE_URL="sqlite:///./ssd_local.db"
$env:SECRET_KEY="a-long-random-string"
$env:ADMIN_EMAIL="you@yourco.com"; $env:ADMIN_PASSWORD="StrongPass!23"
python -m app.seed
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```
