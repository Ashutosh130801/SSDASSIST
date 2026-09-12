# RecoverIQ / SSD — Full Setup From Scratch (PostgreSQL, Windows Server)

This is the complete clean-install guide: PostgreSQL, the backend, configuration, first run,
seeding staff, importing cases, and backups. Do the steps **in order**. Where a step is
optional, it says so.

Folder assumptions (your current layout):
- Repo root: `C:\Users\sahoo\Claude\Projects\SSDASSIST`
- Backend:   `C:\Users\sahoo\Claude\Projects\SSDASSIST\app\backend`
- You run all commands from the **backend** folder unless told otherwise.

---

## 0. Prerequisites (install once)

1. **Python 3.11 or 3.12** — https://www.python.org/downloads/
   During install, tick **“Add python.exe to PATH.”** Verify:
   ```
   python --version
   ```
2. **Git** (you already have it / GitHub Desktop). Verify:
   ```
   git --version
   ```
3. **PostgreSQL 16** — installed in Step 1 below.

No Node.js is needed — the web frontend is transpiled in the browser.

---

## 1. Install PostgreSQL

1. Download the Windows installer (EDB) from https://www.postgresql.org/download/windows/
2. Run it. When it asks for a password for the **`postgres`** superuser, set one and **write it down**.
3. Keep the default **port 5432**. You can skip Stack Builder at the end.
4. Verify: open **SQL Shell (psql)** from the Start menu, press Enter through the prompts,
   enter the `postgres` password → you should get a `postgres=#` prompt.

---

## 2. Create the app database and user

In the `psql` shell (`postgres=#`), paste these lines. Use a **strong password** and remember it
(you’ll put the same one in `.env`):

```sql
CREATE USER ssd WITH PASSWORD 'ChangeThisStrongPassword';
CREATE DATABASE ssd_recovery OWNER ssd;
GRANT ALL PRIVILEGES ON DATABASE ssd_recovery TO ssd;
```

Test the connection (new Command Prompt):
```
psql "postgresql://ssd:ChangeThisStrongPassword@localhost:5432/ssd_recovery" -c "select 1;"
```
A `?column? = 1` result means it works.

> If `psql` isn’t recognized, add PostgreSQL’s `bin` to PATH, e.g.
> `C:\Program Files\PostgreSQL\16\bin`.

---

## 3. Get the code

If the repo isn’t already on this machine:
```
cd C:\Users\sahoo\Claude\Projects
git clone https://github.com/Ashutosh130801/SSDASSIST.git
```
If it’s already there, make sure it’s at the commit you want:
```
cd C:\Users\sahoo\Claude\Projects\SSDASSIST
git fetch origin
git status
```

---

## 4. Configure `.env` (the single most important step)

The `.env` lives at `app\backend\.env`. Open it in Notepad and set the values below.
**Required** keys must be correct or the app won’t start clean. Everything else is optional
(features degrade gracefully when blank).

### Required
```
# Point the app at PostgreSQL (must match Step 2 exactly)
DATABASE_URL=postgresql+psycopg2://ssd:ChangeThisStrongPassword@localhost:5432/ssd_recovery

# A long random string. Generate one with:  python -c "import secrets;print(secrets.token_urlsafe(48))"
SECRET_KEY=paste-a-long-random-string-here

# First admin, created automatically on first boot
ADMIN_EMAIL=admin@ssdenterprises.in
ADMIN_PASSWORD=Admin@2006

# How long a login stays valid (minutes). 720 = 12h.
ACCESS_TOKEN_EXPIRE_MINUTES=720

# Environment
ENVIRONMENT=production
```

### Optional (enable the features you use)
```
# --- Maps & geocoding (address -> lat/long on the FO map) ---
LOCATIONIQ_KEY=            # free key from locationiq.com
GOOGLE_MAPS_API_KEY=       # for the web map tiles / Google geocoding later

# --- AI assist / address cleaning (pick ONE) ---
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-4o-mini
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.0-flash

# --- HR emails (offer/agreement letters) ---
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=ssdenterpriseshr@gmail.com
SMTP_PASSWORD=your16charGmailAppPassword   # Gmail App Password, not the normal one
SMTP_FROM=ssdenterpriseshr@gmail.com
COMPANY_NAME=SRI SAI DHANADA ENTERPRISES

# --- In-app voice calling (staff↔staff) ---
STUN_URL=stun:stun.l.google.com:19302
TURN_URL=                 # e.g. turn:your.server:3478  (self-hosted coturn/eturnal)
TURN_SECRET=              # shared secret; server mints short-lived TURN creds

# --- Visit photo storage (leave blank = save to local ./uploads) ---
GCS_BUCKET=

# --- UPI collection links/QR ---
UPI_VPA=yourcollection@upi
UPI_PAYEE_NAME=SSD Enterprises

# --- Login security ---
LOGIN_MAX_ATTEMPTS=5
LOGIN_LOCKOUT_MINUTES=15

# --- Branding ---
BRAND_NAME=RecoverIQ
BRAND_TAGLINE=Collections & Recovery Intelligence
```

> Never commit the real `.env`. It’s already git-ignored.

---

## 5. First run on PostgreSQL

From `app\backend`, just run the Postgres launcher:
```
run_postgres.bat
```
On first run it will:
1. Create the Python virtual environment (`.venv`) and install all dependencies.
2. Create every table in PostgreSQL (auto-migration adds all columns).
3. Create the admin from `ADMIN_EMAIL` / `ADMIN_PASSWORD`.
4. Start the server.

Watch the startup log — it must say:
```
[SSD] Database: PostgreSQL  ->  localhost:5432/ssd_recovery
```
If it ever says **SQLite**, you launched the wrong script (`run_local.bat`). Use `run_postgres.bat`.

Open the app: **http://localhost:8000** — log in as `admin@ssdenterprises.in` / `Admin@2006`.

> Leave this window open — it *is* the server. Ctrl+C stops it.

---

## 6. Seed the staff (employees) from the manpower list

Use `seed_manpower.bat` (in `app\backend`) — it reads the curated manpower sheet and creates
every employee directly, no credentials sheet needed. Run it **after** Step 5 (so `.venv` and
the tables exist) and with the server stopped or running (it writes to the same Postgres):

```
seed_manpower.bat "C:\path\to\SSDE_manpower (7).xlsx"
```
(or drop the sheet as `SSDE_manpower.xlsx` in the project root and just run `seed_manpower.bat`.)

What it does (verified against your sheet):
- Creates **224 users** — `fos 99, telecaller 88, teamlead 17, headoffice 10, hr 2, it 2,
  techsupport 2, admin 1, manager 1, it_support_view 1, staff 1`.
- Keeps **every Emp Code exactly as given**, so the app’s auto-generated next id continues
  from the next free number per prefix (next FOS = **FO102**, telecaller = **TC097**,
  team lead = **TL043**).
- **Dual-role people get both hats** — the 13 “Field Agent + Team Lead” / “Tele-calling Agent +
  Team Lead” become one account with their primary code (FO../TC..) **plus** the team-lead hat
  (`also_team_lead` + their `Team Lead ID`, e.g. FO059 also carries TL035). They pick the view
  at login and can switch.
- Fills all HR fields (phone, DOB, DOJ, PAN, Aadhaar, bank, addresses, emergency contact…).
- Idempotent: re-running updates existing people (matched by email), never duplicates, and
  never overwrites a password someone already changed.

**Passwords:** staff first-login password is **`Ssd@2026`** (they’re forced to change it on
first login). The admin (`admin@ssdenterprises.in`) uses `ADMIN_PASSWORD` from `.env`.

> The two `techsupport` accounts are intentionally hidden from the Manpower directory
> (diagnostic role), so the on-screen staff count shows 222.

---

## 7. Import cases and products (through the app UI)

With staff seeded, load your portfolios from inside the app (Admin/Head-Office login):

1. **Products** → upload `SSD PRODUCTS.xlsx` (bank/product catalog), if used.
2. **Upload / Import** → upload each case file (ICICI FR X-BKT, AXIS PL&BL, PIRAMAL, etc.),
   choosing the bank/product and the month on the upload form.
3. Allocation (FOS/caller) is matched from the file by employee ID/name.
4. **DPR** uploads update paid/unpaid per case as you go.

Doing imports through the app (not scripts) keeps audit history, allocation, and MIS correct.

---

## 8. Backups (set up once — nothing backs itself up)

Run one now to test:
```
backup_postgres.bat
```
It writes a compressed dump to `app\backend\backups\ssd_YYYYMMDD_HHmmss.dump` and prunes
dumps older than 14 days.

> If it says `pg_dump is not recognized`, add `C:\Program Files\PostgreSQL\16\bin` to PATH.

Automate it (Windows Task Scheduler):
1. **Create Basic Task** → name `SSD DB backup`.
2. Trigger **Daily**, e.g. 1:00 AM.
3. Action **Start a program** → browse to `app\backend\backup_postgres.bat`.
4. Tick “Run whether user is logged on or not” for a server.

**Extra safety:** copy the `backups\` folder to a second drive or a cloud-synced folder.
Restore, if ever needed:
```
pg_restore -d "postgresql://ssd:ChangeThisStrongPassword@localhost:5432/ssd_recovery" --clean --if-exists ssd_YYYYMMDD_HHmmss.dump
```

---

## 9. Serving it beyond localhost (optional, production)

You already serve at `recoveriq.ssdenterprises.org.in`. For a public/HTTPS deploy you need,
in front of the app on port 8000:
- A reverse proxy (Nginx / Caddy / IIS) terminating HTTPS and forwarding to `127.0.0.1:8000`.
- **WebSocket pass-through** enabled (the live sheet, presence, chat and voice-call signaling
  all use WebSockets — the proxy must forward the `Upgrade`/`Connection` headers).
- Optionally set `WEBAUTHN_RP_ID` / `WEBAUTHN_ORIGIN` to your domain for passkeys, and
  `CORS_ORIGINS` only if the frontend is served from a different origin.
- For in-app voice across mobile networks, run a TURN server (coturn/eturnal) and set
  `TURN_URL` + `TURN_SECRET`.

The desktop app (`desktop\`) already points at `https://recoveriq.ssdenterprises.org.in`, so once
the domain serves this backend, the desktop and Android apps connect automatically.

---

## 9b. Migrate the Cloudflare Tunnel to another PC

The tunnel itself lives in Cloudflare; each PC just runs a **connector** (`cloudflared`) that
points at it. Moving it = putting the connector on the new PC and stopping it on the old one.
The DNS record (`recoveriq.ssdenterprises.org.in` → tunnel) does **not** change, so there's no
DNS edit and no downtime beyond the switchover.

### First, know which type you have (check on the OLD PC)
```
cloudflared tunnel list
dir %USERPROFILE%\.cloudflared
```
- If that folder has a **`config.yml`** and a **`<TUNNEL-ID>.json`** → it's **locally-managed** (config file).
- If it's nearly empty and the service runs from a long token → it's **dashboard-managed** (token).

### A) Dashboard-managed (token) — easiest
1. Install cloudflared on the **new PC**: `winget install --id Cloudflare.cloudflared`
   (or download the Windows `.msi` from Cloudflare).
2. Cloudflare dashboard → **Zero Trust → Networks → Tunnels →** your tunnel →
   **Configure → Install connector** → copy the Windows command (contains the token).
3. Run it on the new PC (elevated PowerShell):
   ```
   cloudflared service install eyJhIjoi...your-token...
   ```
4. Confirm the tunnel's **Public Hostname** still routes to `http://localhost:8000`.
5. On the **OLD PC**, remove its connector so it isn't running in two places:
   ```
   cloudflared service uninstall
   ```

### B) Locally-managed (config file)
1. Install cloudflared on the new PC (as above).
2. **Stop it on the OLD PC first:** `cloudflared service uninstall`
3. Copy the whole `%USERPROFILE%\.cloudflared\` folder from old → new PC. It must contain:
   - `cert.pem`
   - `<TUNNEL-ID>.json`  ← the credentials (the key file)
   - `config.yml`
4. Edit `config.yml` on the new PC so the paths and local URL are correct:
   ```yaml
   tunnel: <TUNNEL-ID>
   credentials-file: C:\Users\<newuser>\.cloudflared\<TUNNEL-ID>.json
   ingress:
     - hostname: recoveriq.ssdenterprises.org.in
       service: http://localhost:8000
     - service: http_status:404
   ```
5. Test in the foreground, then install as a service:
   ```
   cloudflared tunnel run <TUNNEL-NAME>
   cloudflared service install
   ```

### Rules that matter either way
- **Never run the connector on both PCs at once** — Cloudflare load-balances between them and
  requests will randomly hit the old (empty) machine. Uninstall the old connector.
- The **backend must already be running** on the new PC (`run_postgres.bat`, port 8000) before
  the tunnel is useful — the tunnel only forwards traffic.
- Migrate the **whole app** to the new PC too (PostgreSQL + `.env` + the repo). The tunnel does
  not carry your database.
- After switching, verify `https://recoveriq.ssdenterprises.org.in` loads and the desktop/Android
  apps still connect (they point at the domain, so nothing to change there).

---

## 10. Quick verification checklist

- [ ] `psql ... -c "select 1;"` works (Postgres reachable)
- [ ] Startup log says `Database: PostgreSQL`
- [ ] http://localhost:8000 loads; admin can log in
- [ ] Staff seeded (Step 6) — Manpower directory shows everyone
- [ ] A test case file imports and shows in the live sheet
- [ ] `backup_postgres.bat` produced a `.dump` file
- [ ] Task Scheduler nightly backup created

---

## Script reference

| Script | Database | Use |
|---|---|---|
| `run_postgres.bat` | PostgreSQL (.env) | **Production — start the server** |
| `backup_postgres.bat` | PostgreSQL | Nightly dump (schedule it) |
| `seed_manpower.bat` | PostgreSQL (.env) | (coming) create employees from the new manpower sheet |
| `run_local.bat` | SQLite | Offline dev only — do **not** use for production |
| `go_live.bat` / `seed_postgres.bat` | — | Old flows that expect a credentials sheet; **skip** (they purge FR cases) |

---

### Default login
`admin@ssdenterprises.in` / `Admin@2006` — change this password after first login.
