# SSDASSIST — Self-Hosting on Your Own Ubuntu PC (always-on + auto-deploy + HTTPS)

You run **everything on one Ubuntu PC** you own (at home or the office). It stays on 24/7,
serves the web app and the mobile app's backend, and **updates itself every time you push
code from your Windows machine to GitHub**. Field officers reach it over the internet through
a free **Cloudflare Tunnel** (no static IP, no router port-forwarding), which also gives you
automatic HTTPS.

**Your setup:** one always-on Ubuntu PC · auto-deploy on every `git push` · reachable on the
internet with HTTPS via Cloudflare Tunnel.

**Already built into the repo (you don't create these):**
`app/docker-compose.yml` (Postgres + the API that also serves the web app), `app/backend/Dockerfile`,
`app/.env.example` (secrets template), `.github/workflows/deploy-selfhosted.yml` (the auto-deploy job).

Commands are labelled **[Windows]** (your dev PC) or **[Ubuntu PC]** (the server) every time.

---

## Part 0 — What you need

- The **Ubuntu PC** (Ubuntu 22.04 or 24.04), ideally 8 GB RAM, that can stay powered on. It
  can be a normal desktop — it doesn't need a monitor once set up.
- A **domain name** (e.g. `ssdenterprises.in`). A cheap one (~₹700–900/year from GoDaddy,
  Namecheap, Cloudflare, etc.) is fine. You'll manage it through a **free Cloudflare account**.
  This is what lets field phones reach your home/office PC securely.
- Your GitHub account with access to `SSDRetrace/SSDASSIST` (already the repo's remote).
- About an hour, mostly waiting on installs.

> Why a tunnel and not just your home internet? A home/office connection usually has no fixed
> public address and the router blocks incoming connections. Cloudflare Tunnel makes an
> **outbound** connection from your PC to Cloudflare, so your app becomes reachable at your
> domain with HTTPS — without exposing your PC or touching the router.

---

## Part A — Push your latest code from Windows to GitHub

**[Windows]** in the project folder:

```powershell
cd C:\Users\sahoo\Claude\Projects\SSDASSIST
git status
git add -A
git commit -m "New address/phone + FOS notifications, profile screen, self-host docs"
git push origin main
```

If Git asks you to sign in, use a **Personal Access Token** (GitHub → Settings → Developer
settings → Personal access tokens → Tokens (classic) → tick **repo** → paste as the password),
or use **GitHub Desktop** and click *Push origin*.

> Never commit secrets. `.gitignore` already excludes `SSDE Man power.xlsx`,
> `SSDE_login_credentials.xlsx`, `SSDE_ALL_LOGINS.xlsx`, `app/backend/.env`, and `*.db`.
> A quick `git status` should not list any of those.

---

## Part B — Prepare the Ubuntu PC

Do these directly on the PC (keyboard + screen), or from Windows over SSH once it's on the
same network (`ssh yourname@192.168.x.x`).

### B1. Update the system
**[Ubuntu PC]**

```bash
sudo apt update && sudo apt -y upgrade
```

### B2. Install Docker (runs the whole app)
**[Ubuntu PC]**

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```

Log out and back in (or reboot) so Docker works without `sudo`, then check:

```bash
docker --version
docker compose version
```

### B3. Make it truly "always on" (never sleep)
So the PC keeps serving even with the lid closed / screen off:
**[Ubuntu PC]**

```bash
# Stop the machine from suspending or hibernating
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

On a laptop, also: *Settings → Power →* set **"When the lid is closed"** and **"Automatic
suspend"** to **Off / Do nothing**. (Docker and the tunnel below start on boot automatically,
so after any power cut the app comes back on its own.)

### B4. Find the PC's local IP (for testing on your own network)
**[Ubuntu PC]**

```bash
hostname -I | awk '{print $1}'      # e.g. 192.168.1.50
```

---

## Part C — Put the code and your secrets on the PC

### C1. Clone the repo
Use a Personal Access Token as the password when Git prompts (private repo).
**[Ubuntu PC]**

```bash
cd ~
git clone https://github.com/SSDRetrace/SSDASSIST.git
cd SSDASSIST
```

### C2. Create your real secrets file
Kept in your home folder, **never** in the repo.
**[Ubuntu PC]**

```bash
cp app/.env.example ~/recoveriq.env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # copy this output
nano ~/recoveriq.env
```

Fill in (replace the placeholders):

```ini
SECRET_KEY=<paste the long random string you just generated>
POSTGRES_PASSWORD=<a strong database password>
ADMIN_EMAIL=admin@ssdenterprises.in
ADMIN_PASSWORD=Admin@2006
ENVIRONMENT=production

# Set after Part D once you know your domain (for passkey/biometric login):
# WEBAUTHN_RP_ID=app.ssdenterprises.in
# WEBAUTHN_ORIGIN=https://app.ssdenterprises.in

# Optional — leave blank if unused:
GOOGLE_MAPS_API_KEY=
GEMINI_API_KEY=
UPI_VPA=
LOCATION_PING_SECONDS=60
```

Save with **Ctrl+O, Enter, Ctrl+X**.

### C3. First build & start (do this once, by hand)
**[Ubuntu PC]**

```bash
cd ~/SSDASSIST/app
docker compose -p recoveriq --env-file ~/recoveriq.env up -d --build
```

First build takes a few minutes. Then verify:

```bash
docker compose -p recoveriq ps            # 'db' and 'api' should be Up
curl http://localhost:8000/api/health     # healthy JSON
```

On any other device on the **same network**, open `http://192.168.1.50:8000` (your PC's IP) —
you should see the login page. Admin (`admin@ssdenterprises.in / Admin@2006`) is created
automatically. Part D makes it reachable from anywhere with HTTPS.

### C4. Import the 189 real employees (one time)
The staff sheets aren't in GitHub, so copy them over and run the importer inside the container.

**[Windows]** (new terminal):

```powershell
cd C:\Users\sahoo\Claude\Projects\SSDASSIST
scp "SSDE Man power.xlsx" "SSDE_login_credentials.xlsx" yourname@192.168.1.50:/home/yourname/SSDASSIST/app/backend/
```

**[Ubuntu PC]**

```bash
cd ~/SSDASSIST/app
docker compose -p recoveriq exec api python productionize.py \
  "SSDE Man power.xlsx" "SSDE_login_credentials.xlsx"
rm ~/SSDASSIST/app/backend/"SSDE Man power.xlsx" ~/SSDASSIST/app/backend/"SSDE_login_credentials.xlsx"
```

This creates all 189 logins (starter password `Ssd@2026`, forced change on first login), maps
any existing cases to the right staff, and purges demo data.

---

## Part D — Make it reachable on the internet with HTTPS (Cloudflare Tunnel)

This is what lets field officers' phones reach your PC from anywhere, safely, with automatic
HTTPS — and no router/port changes.

### D1. Put your domain on Cloudflare (free) — GoDaddy steps
You keep the domain at GoDaddy (you still own and renew it there); you just move its **DNS** to
Cloudflare so the tunnel can attach your app to it.

1. **Add the domain to Cloudflare.** Create a free account at **cloudflare.com** → **Add a
   site** → type your GoDaddy domain (e.g. `ssdenterprises.in`) → choose the **Free** plan.
   Cloudflare scans your current DNS and then shows **two nameservers**, e.g.
   `dana.ns.cloudflare.com` and `rob.ns.cloudflare.com`. Copy both.

2. **Point GoDaddy at Cloudflare's nameservers.** Log in to GoDaddy → **My Products** → your
   domain → **Manage DNS** (or **Domain Settings**) → **Nameservers** → **Change** → choose
   **"I'll use my own nameservers"** → delete GoDaddy's and paste the **two Cloudflare
   nameservers** → **Save**. (Labels vary slightly, but it's always under the domain's
   *Nameservers* section.)

3. **Wait for it to go live.** Propagation takes ~15 min to a few hours. Cloudflare flips the
   site status from *Pending* to **Active** (and emails you).

> **Before you save at GoDaddy — protect your email/website.** Moving nameservers moves *all*
> DNS for the domain. Cloudflare usually auto-imports your existing records during the Step 1
> scan, but open the Cloudflare **DNS** tab and confirm your **MX records** (and any existing
> website A records) are present — otherwise email could stop working. If you use GoDaddy email
> or Google Workspace, double-check those MX entries carried over.
>
> Prefer not to move the whole domain? You can delegate just a subdomain to Cloudflare instead,
> but the full nameserver move is simplest and is what the rest of this guide assumes.

### D2. Install the tunnel agent on the PC
**[Ubuntu PC]**

```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb
cloudflared --version
```

### D3. Log in and create the tunnel
**[Ubuntu PC]**

```bash
cloudflared tunnel login          # opens a link; pick your domain to authorize
cloudflared tunnel create recoveriq
```

Note the **Tunnel ID** it prints. Now route your chosen hostname to the tunnel (use *your*
domain — `app.` sub-domain recommended):

```bash
cloudflared tunnel route dns recoveriq app.ssdenterprises.in
```

### D4. Point the tunnel at the app and run it as a service
**[Ubuntu PC]** create the config:

```bash
sudo mkdir -p /etc/cloudflared
sudo nano /etc/cloudflared/config.yml
```

Paste (replace the Tunnel ID and the hostname; the credentials file is under your home
`~/.cloudflared/<TUNNEL-ID>.json` — copy it to /etc/cloudflared or point to it):

```yaml
tunnel: <YOUR-TUNNEL-ID>
credentials-file: /home/yourname/.cloudflared/<YOUR-TUNNEL-ID>.json

ingress:
  - hostname: app.ssdenterprises.in
    service: http://localhost:8000
  - service: http_status:404
```

Install it as an always-on service:

```bash
sudo cloudflared service install
sudo systemctl enable --now cloudflared
sudo systemctl status cloudflared     # should be active (running)
```

Wait ~1 minute, then open **https://app.ssdenterprises.in** from any device/network — you get
the login page with a valid padlock. HTTPS is handled by Cloudflare and renews itself.

### D5. Tell the app its real address (passkeys/biometric login)
**[Ubuntu PC]** add to `~/recoveriq.env`:

```ini
WEBAUTHN_RP_ID=app.ssdenterprises.in
WEBAUTHN_ORIGIN=https://app.ssdenterprises.in
```

Apply:

```bash
cd ~/SSDASSIST/app
docker compose -p recoveriq --env-file ~/recoveriq.env up -d
```

> **Only want it on the office LAN (not the internet)?** Skip Part D entirely and just use
> `http://<PC-IP>:8000`. But then field officers can't reach it from outside the office, so
> the tunnel is strongly recommended for a collections team.

---

## Part E — Auto-deploy: push from Windows → PC updates itself

Installs a **self-hosted GitHub Actions runner** on your PC. The included workflow
(`.github/workflows/deploy-selfhosted.yml`) rebuilds and restarts the app on every push to
`main` that touches `app/`.

### E1. Get the runner commands from GitHub
Browser → your repo → **Settings → Actions → Runners → New self-hosted runner → Linux / x64**.
GitHub shows commands with a one-time token. Keep that page open.

### E2. Install & register the runner
**[Ubuntu PC]** — run the commands GitHub gave you (yours will have a real token/version):

```bash
mkdir ~/actions-runner && cd ~/actions-runner
curl -o actions-runner-linux-x64.tar.gz -L https://github.com/actions/runner/releases/download/vX.XXX.X/actions-runner-linux-x64-X.XXX.X.tar.gz
tar xzf ./actions-runner-linux-x64.tar.gz
./config.sh --url https://github.com/SSDRetrace/SSDASSIST --token <TOKEN_FROM_GITHUB>
```

Press Enter through the prompts (name, labels, work folder).

### E3. Run it as a service (survives reboots)
**[Ubuntu PC]**

```bash
cd ~/actions-runner
sudo ./svc.sh install
sudo ./svc.sh start
sudo ./svc.sh status        # active (running)
```

The Runners page in GitHub now shows a green **Idle** dot.

### E4. Test the full loop
**[Windows]**

```powershell
cd C:\Users\sahoo\Claude\Projects\SSDASSIST
# edit anything under app/ (e.g. a comment), then:
git add -A
git commit -m "Test auto-deploy"
git push origin main
```

Browser → repo → **Actions** tab: the *Deploy to self-hosted server* job runs **on your PC**
and goes green in 1–3 minutes. Refresh the app — your change is live. **That's push-here →
reflected-there working.**

> **Photos & data persistence:** both uploaded photos (field visits + profile pictures) and the
> database are kept on **persistent local Docker volumes on this PC** (`ssd_uploads` and
> `ssd_pgdata`) — stored on your own disk, never the cloud, and untouched by redeploys or
> reboots. Nothing is lost when you push new code. (Cloud storage via `GCS_BUCKET` remains an
> optional alternative, but is not required for local self-hosting.)

---

## Part F — Point the Android app at your server

The app uses certificate pinning, so update its build config and reinstall the APK.

**[Windows]** in `android-native/app/build.gradle.kts`:

- `BASE_URL` → `https://app.ssdenterprises.in/`
- `CERT_PIN` → **leave blank**. Cloudflare rotates its TLS certificates, so a hard-coded pin
  would eventually break the app. With it blank, the app uses normal HTTPS certificate
  validation (still fully encrypted and trusted).

Then *Build → Build APK* in Android Studio and install on the phones. The web app needs no
change — it just works at your domain.

---

## Everyday use

**Ship a change:** on Windows → `git add -A` → `git commit -m "..."` → `git push origin main`.
The PC rebuilds itself in a couple of minutes.

**Upload cases / see MIS:** log in to the web app and use Upload. Assignment, MIS, analytics
are automatic and live.

**After a power cut / reboot:** everything restarts on its own — Docker containers
(`restart: unless-stopped`), the Cloudflare tunnel, and the deploy runner all run as services.

---

## Maintenance cheat-sheet (run on the Ubuntu PC)

```bash
cd ~/SSDASSIST/app && docker compose -p recoveriq ps        # status
docker compose -p recoveriq logs -f api                     # live API logs
docker compose -p recoveriq restart api                     # restart the API
systemctl status cloudflared                                # tunnel health
cd ~/actions-runner && sudo ./svc.sh status                 # deploy runner health

# Manual deploy (if auto-deploy is ever off)
cd ~/SSDASSIST && git pull && cd app && docker compose -p recoveriq --env-file ~/recoveriq.env up -d --build

# BACK UP THE DATABASE weekly — keep the file off the PC (USB / cloud drive)
docker compose -p recoveriq exec -T db pg_dump -U ssd ssd_recovery > ~/ssd_backup_$(date +%F).sql

# Restore a backup
cat ~/ssd_backup_YYYY-MM-DD.sql | docker compose -p recoveriq exec -T db psql -U ssd -d ssd_recovery
```

---

## Quick troubleshooting

| Symptom | Fix |
|---|---|
| `https://app…` doesn't load | `systemctl status cloudflared`; if down, `sudo systemctl restart cloudflared`. Confirm DNS route: `cloudflared tunnel route dns recoveriq app.ssdenterprises.in`. |
| Cloudflare still "Pending" | Nameservers at your registrar aren't set to Cloudflare's yet, or still propagating. |
| Works on `http://PC-IP:8000` but not the domain | Tunnel/config issue — check `/etc/cloudflared/config.yml` hostname + the `service: http://localhost:8000` line. |
| Actions job fails on "docker compose" | Runner service not running or `~/recoveriq.env` missing. `cd ~/actions-runner && sudo ./svc.sh status`. |
| Old code after push | The push didn't touch `app/` (workflow only triggers on `app/**`), or browser cache — hard-refresh (Ctrl+Shift+R). |
| PC keeps sleeping | Re-run the `systemctl mask …sleep` command in B3 and set power settings to never suspend. |
| App can't reach server after moving domains | Update the Android `BASE_URL` and reinstall the APK (Part F). |

---

### One-line mental model
> Your **Windows PC** writes code → **GitHub** holds it → your **always-on Ubuntu PC** watches
> GitHub and rebuilds itself on every push → **Cloudflare Tunnel** publishes it at your domain
> with HTTPS → the **Postgres database** persists, so nothing is lost across updates or reboots.
