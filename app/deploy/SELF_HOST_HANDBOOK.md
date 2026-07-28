# RecoverIQ — Self-Hosting Handbook (beginner-proof)

Goal: run the **database + backend + web app on your own always-on PC**, reachable on the
internet at a stable HTTPS address, and set it up so that when you **push code to GitHub from
your laptop, the server updates itself automatically**.

You will do this **once**. After that, your daily workflow is just: edit code on your laptop →
`git push` → the server rebuilds itself in ~1–2 minutes.

Three pieces make this work:
1. **Docker** on the server runs Postgres + the backend together (one command).
2. **Cloudflare Tunnel** gives you a permanent free `https://` address without touching your
   router (works even on CGNAT / mobile broadband). This permanently replaces ngrok.
3. **A GitHub self-hosted runner** on the server listens for your pushes and redeploys.

> Follow the parts in order. Commands are meant to be copied exactly. Lines starting with `#`
> are comments — you don't type those.

---

## What you need before starting
- A spare PC that can stay **powered on and online 24/7** (4 GB RAM is plenty).
- **Ubuntu Server 24.04 LTS** installed on it (recommended). If you only have Windows, see the
  Windows note at the very bottom — but Linux is strongly recommended for an always-on server.
- Your project already on **GitHub** (this repo).
- A **domain name** you control (about ₹700–1000 / $8–12 a year — the only real cost). You can
  buy one from Cloudflare directly, which makes step C easiest.
- A free **Cloudflare** account.

Throughout, replace these placeholders with your real values:
- `yourdomain.com` → your domain
- `app.yourdomain.com` → the address people will use
- `OWNER/REPO` → your GitHub repo path (e.g. `mohithseerapu/SSDASSIST`)

---

## PART A — Prepare the server PC

Do these on the **server** (the spare PC), in its Terminal.

**A1. Update the system**
```
sudo apt update && sudo apt upgrade -y
```

**A2. Install Docker (includes Docker Compose)**
```
curl -fsSL https://get.docker.com | sudo sh
```

**A3. Let your user run Docker without `sudo`**
```
sudo usermod -aG docker $USER
```
Now **log out and log back in** (or reboot) so that takes effect. Verify:
```
docker run hello-world
```
You should see "Hello from Docker!". If you do, Docker works.

**A4. Install git**
```
sudo apt install -y git
```

---

## PART B — Get the code and configure secrets

**B1. Download the project onto the server**
```
cd ~
git clone https://github.com/OWNER/REPO.git recoveriq
```
(If the repo is private, git will ask for your GitHub username and a **Personal Access Token**
as the password — create one at GitHub → Settings → Developer settings → Personal access tokens.)

**B2. Create your secrets file** (kept in your home folder, never in the repo):
```
cp ~/recoveriq/app/.env.example ~/recoveriq.env
```

**B3. Generate a strong secret key:**
```
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```
Copy the long string it prints.

**B4. Edit the secrets file:**
```
nano ~/recoveriq.env
```
Fill in at least these four, then save with **Ctrl+O, Enter, Ctrl+X**:
```
SECRET_KEY=<paste the long string from B3>
POSTGRES_PASSWORD=<make up a strong database password>
ADMIN_EMAIL=<your real admin email>
ADMIN_PASSWORD=<a strong admin password>
```
Leave `ENVIRONMENT=production` as-is. Optional keys (maps/UPI/etc.) can stay blank.

**B5. First start — bring the stack up:**
```
cd ~/recoveriq/app
docker compose -p recoveriq --env-file ~/recoveriq.env up -d --build
```
The first build takes a few minutes. When it finishes, check it's running:
```
docker compose -p recoveriq ps
```
Then test it locally on the server:
```
curl http://localhost:8000/health
```
You should see `{"status":"ok"}`. **Your backend + database are now running.** Your admin
login was created from `ADMIN_EMAIL` / `ADMIN_PASSWORD`.

---

## PART C — Put it on the internet with Cloudflare Tunnel (free, stable HTTPS)

**C1. Add your domain to Cloudflare.** Sign in at cloudflare.com → **Add a site** → enter
`yourdomain.com` → pick the **Free** plan → follow the instructions to point your domain's
nameservers to Cloudflare (done at wherever you bought the domain). Wait until Cloudflare shows
the domain as **Active** (can take a few minutes to a few hours). *(If you buy the domain
through Cloudflare Registrar, it's already on Cloudflare — skip this.)*

**C2. Create the tunnel (mostly clicking).**
- Go to **Cloudflare Zero Trust** dashboard → **Networks → Tunnels → Create a tunnel**.
- Choose **Cloudflared**, name it `recoveriq`, **Save**.
- On the "Install connector" screen, choose **Debian / 64-bit**. It shows a command that looks
  like `sudo cloudflared service install eyJhIjoiJ...` (a long token). **Copy that whole
  command and run it on the server.** This installs the tunnel as an always-on service.
- Back in the dashboard the tunnel should flip to **HEALTHY / Connected**.

**C3. Route your address to the backend.**
- Still in the tunnel setup, open the **Public Hostname** tab → **Add a public hostname**:
  - **Subdomain:** `app`
  - **Domain:** `yourdomain.com`
  - **Type:** `HTTP`
  - **URL:** `localhost:8000`
- **Save.**

Now open **https://app.yourdomain.com** in any browser, anywhere — you should see the RecoverIQ
login. It has real HTTPS automatically, and the address never changes. (Cloudflare passes
WebSockets through by default, so the live sheet works.)

---

## PART D — Auto-deploy on every push (GitHub self-hosted runner)

This makes "push from my laptop → server updates itself" happen.

**D1. Register the runner.** In your browser: GitHub → your repo → **Settings → Actions →
Runners → New self-hosted runner → Linux**. GitHub shows a block of commands unique to your
repo. Run them **on the server**. They look like:
```
mkdir ~/actions-runner && cd ~/actions-runner
curl -o actions-runner-linux-x64.tar.gz -L https://github.com/actions/runner/releases/download/vX.X.X/actions-runner-linux-x64-X.X.X.tar.gz
tar xzf actions-runner-linux-x64.tar.gz
./config.sh --url https://github.com/OWNER/REPO --token <TOKEN GITHUB SHOWS YOU>
```
When `config.sh` asks questions, just press **Enter** to accept the defaults.

**D2. Run the runner as an always-on service:**
```
sudo ./svc.sh install $USER
sudo ./svc.sh start
```
Back on the GitHub Runners page it should show the runner as **Idle** (green).

**D3. The deploy workflow is already in the repo** at
`.github/workflows/deploy-selfhosted.yml`. It triggers on every push to `main` that changes
anything under `app/`, and it runs — on your server — the same compose command from B5. Nothing
more to configure.

**D4. Test the whole loop.** On your **laptop**, make any small change, then:
```
git add -A && git commit -m "test auto-deploy" && git push
```
Watch GitHub → your repo → **Actions**. A "Deploy to self-hosted server" run should start, run
on your server, and finish green. Refresh `https://app.yourdomain.com` — your change is live.
**That's the workflow you'll use forever: edit → push → it appears on the server.**

---

## PART E — Point the Android app at your new address

1. GitHub repo → **Settings → Secrets and variables → Actions** → set the secret
   **`APP_URL`** = `https://app.yourdomain.com/`. Leave `CERT_PIN` empty.
2. GitHub → **Actions → "Build Native Android App" → Run workflow**.
3. Download **`RecoverIQ-native.apk`** from the `android-native-latest` release and share it.
   On each phone: uninstall any old copy once, install this, log in.

---

## PART F — Backups (do NOT skip)

Your data lives in the Postgres Docker volume on the server. Make a nightly backup:

**F1. Create a backup script:**
```
nano ~/backup-db.sh
```
Paste this, then save (Ctrl+O, Enter, Ctrl+X):
```
#!/usr/bin/env bash
mkdir -p ~/backups
FILE=~/backups/recoveriq-$(date +%F).sql
docker exec recoveriq-db-1 pg_dump -U ssd ssd_recovery > "$FILE"
# keep only the last 14 days
find ~/backups -name "recoveriq-*.sql" -mtime +14 -delete
```
(If `recoveriq-db-1` isn't the container name, run `docker ps` and use the DB container's name.)

**F2. Make it runnable and schedule it for 2 AM daily:**
```
chmod +x ~/backup-db.sh
( crontab -l 2>/dev/null; echo "0 2 * * * ~/backup-db.sh" ) | crontab -
```
Copy the `~/backups` folder to another disk / cloud drive periodically so a dead PC doesn't
take your data with it.

---

## Everyday operations & troubleshooting

- **See logs:** `cd ~/recoveriq/app && docker compose -p recoveriq logs -f api`
- **Restart everything:** `docker compose -p recoveriq --env-file ~/recoveriq.env restart`
- **Is it up?** `curl http://localhost:8000/health` on the server, or open the public URL.
- **Server rebooted?** Everything comes back on its own — Docker (`restart: unless-stopped`),
  the Cloudflare tunnel (service), and the runner (service) all auto-start.
- **Restore a backup:** `cat ~/backups/recoveriq-YYYY-MM-DD.sql | docker exec -i recoveriq-db-1 psql -U ssd ssd_recovery`

## Honest reality check
Because it's your own PC: if the **power or internet at that location goes down, everyone is
offline** — including field officers mid-visit. You also own backups, security updates, and
uptime yourself. This is perfect for an internal tool or a pilot. If field staff depend on it
all day, consider whether a ~$10–25/month managed host is worth buying away that risk. You can
always start self-hosted and move to the cloud later — the code and this process don't change.

## Windows-only note
If the server must run Windows: install **Docker Desktop** (enable WSL2), install **git**, and
use the *same* `docker compose -p recoveriq --env-file ...` commands in PowerShell. Cloudflared
and the GitHub runner both have Windows installers. Linux is still recommended because it runs
unattended far more reliably.
