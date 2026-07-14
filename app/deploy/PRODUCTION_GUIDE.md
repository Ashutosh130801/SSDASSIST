# RecoverIQ — Production Guide

Everything needed to run the platform on a real server with a real database, create the
admin and every role's login with proper authentication, and manage the database efficiently.

One container serves **both** the API and the web app (the backend serves the PWA at `/`),
so there is a single service and a single database to operate.

---

## 0. Prerequisites

- A domain (optional but recommended) and a Google Cloud **or** any Linux server.
- **gcloud CLI** (for the Cloud Run path) or **Docker** (for the plain-server path).
- Your **Google Maps API key** (Maps JavaScript API + Geocoding API enabled).
- Optional: **Gemini API key** (AI assist), **Google OAuth Client ID** (Google sign-in).

---

## 1. Deploy — Option A: Google Cloud Run + Cloud SQL (recommended)

Managed, auto-scaling, HTTPS out of the box, managed Postgres with automated backups.

1. `gcloud auth login`, then create a project with **billing enabled**.
2. Edit **`app/deploy/deploy.ps1`** (Windows) or **`deploy.sh`** (Mac/Linux) and set:
   `PROJECT`, `REGION` (e.g. `asia-south1` = Mumbai), a strong `DB_PASS`, and your
   `MAPS_KEY` / `GEMINI_KEY`. `SECRET_KEY` is auto-generated.
3. From the **`app`** folder run the script:
   ```powershell
   .\deploy\deploy.ps1        # Windows
   ./deploy/deploy.sh         # Mac/Linux
   ```
   It enables the APIs → creates Cloud SQL Postgres + database + user → builds the
   container → deploys to Cloud Run → prints your `https://…run.app` URL.
4. Turn on production mode (enforces a real secret, locks CORS to same-origin, hides API docs):
   ```
   gcloud run services update recoveriq --region <REGION> --set-env-vars ENVIRONMENT=production
   ```

> Store `DATABASE_URL`, `SECRET_KEY`, `GEMINI_API_KEY` in **Secret Manager** and pass them
> with `--set-secrets` instead of `--set-env-vars` for a hardened setup.

## 1. Deploy — Option B: your own Linux server (VPS)

For a single always-on box (Ubuntu 22.04+ with Docker):

```bash
# on the server, in the app/ folder
cp backend/.env.example backend/.env      # then edit backend/.env (see §3)
docker compose up -d --build              # starts Postgres + the app
```

`docker-compose.yml` brings up Postgres and the app together. Put **Nginx + Let's Encrypt**
(or Caddy) in front for HTTPS on your domain, proxying to the app's port. Point
`DATABASE_URL` at the compose Postgres service.

---

## 2. Environment variables (the whole list)

| Variable | Required | Purpose |
|----------|----------|---------|
| `DATABASE_URL` | ✅ | Postgres in prod (`postgresql+psycopg2://user:pass@host/db`); SQLite locally |
| `SECRET_KEY` | ✅ | signs JWTs — long random string; app refuses to start in prod with the default |
| `ENVIRONMENT` | ✅ (prod) | set to `production` to lock CORS + hide docs |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | – | session length (default 720 = 12h) |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | – | first admin created by the seed / first boot |
| `GOOGLE_MAPS_API_KEY` | – | live map, field tracking, geocoding |
| `GEMINI_API_KEY` | – | AI assist |
| `GOOGLE_CLIENT_ID` | – | optional Google sign-in |
| `BRAND_NAME` / `BRAND_TAGLINE` | – | white-label the login + sidebar (default "RecoverIQ") |
| `UPI_VPA` / `UPI_PAYEE_NAME` | – | UPI payment links + QR |
| `SEED_ON_START` | – | `1` on first deploy to auto-create the admin, then remove |

---

## 3. Create the admin + role logins (with authentication)

Roles (internal key → label shown in the app):
`admin` → **Administrator**, `manager` → **Collections Manager**,
`fos` → **Field Agent**, `telecaller` → **Tele-calling Agent**.

Every login is a row in `users` with a **bcrypt-hashed** password (never plaintext). Sign-in
issues a **JWT** (12h) sent as `Authorization: Bearer …` on every request; the server checks
the token, the role, a per-user data scope, **and** a device gate (a user's first device is
auto-approved, any new device must be approved by an admin/manager). There is **no public
signup** — accounts are created only by the three methods below.

### 3a. Create the first admin (choose one)

**On first Cloud Run deploy** — seed just the admin, then turn seeding off:
```
gcloud run services update recoveriq --region <REGION> --set-env-vars SEED_ON_START=1
# open the URL, sign in once, then:
gcloud run services update recoveriq --region <REGION> --remove-env-vars SEED_ON_START
```
Admin login = `ADMIN_EMAIL` / `ADMIN_PASSWORD`. **Change the password immediately.**
(Deploy with `--set-env-vars ADMIN_EMAIL=you@co.com,ADMIN_PASSWORD=aStrongPass` to set your own.)

**Or with the CLI** (works against local SQLite or prod Postgres — just set `DATABASE_URL`):
```bash
cd app/backend
python manage.py create-user --name "Asha Rao" --email asha@yourco.com \
    --role admin --password "StrongPass!23"
```

### 3b. Create every other role — two ways

**In the app (recommended for daily use):** sign in as admin →
**Team → + Add staff** → set name, email, password, **Role**, branch, and for Field Agents
their banks / assigned pincodes / base lat-lng (these drive auto-allocation). Use **Edit** on
a row to change role, reset password, or deactivate.

**From the server with `manage.py`** (great for bulk/scripted onboarding):
```bash
# Collections Manager
python manage.py create-user --name "Vizag Manager" --email mgr@yourco.com \
    --role manager --password "Mgr!2345" --branch Visakhapatnam

# Field Agent (with allocation data)
python manage.py create-user --name "Ravi K" --email ravi@yourco.com \
    --role fos --password "Field!234" --branch Visakhapatnam \
    --banks ICICI,RBL --pincodes 530001,530016 --lat 17.7231 --lng 83.3013

# Tele-calling Agent
python manage.py create-user --name "Krishna" --email krishna@yourco.com \
    --role telecaller --password "Call!2345"
```

Other `manage.py` commands:
```bash
python manage.py list-users
python manage.py reset-password --email ravi@yourco.com --password "New!2345"
python manage.py set-role --email ravi@yourco.com --role manager
python manage.py deactivate --email old@yourco.com      # blocks sign-in
python manage.py activate   --email old@yourco.com
python manage.py stats                                   # row counts
```

> On Cloud Run, run `manage.py` from your PC with `DATABASE_URL` pointed at Cloud SQL
> through the Auth Proxy (see §5), or as a one-off `gcloud run jobs` execution.

---

## 4. First real setup (as admin, in the app)

1. **Team → + Add staff** — create your managers, field agents and tele-callers.
2. **Accounts → ⬆ Upload** — upload your bank Excel(s); Preview → **Import & Allocate**
   (auto-allocates by pincode / nearest field agent).
3. **Accounts → 📍 Geocode** — turn addresses into map pins.
4. (Optional) set `UPI_VPA` for payment links, add message templates in **Communication**.
5. Share the URL; staff install it via **⬇ Install app** / Add-to-Home-Screen.

---

## 5. Manage the database efficiently

### Connect to the production database

- **Cloud SQL Studio (browser):** Cloud Console → **SQL → your instance → Studio** → run SQL
  against `recoveriq` (or whatever `DB_NAME` you set). No install needed.
- **psql from your PC:** `gcloud sql connect <instance> --user=<db_user> --database=<db_name>`
- **GUI (DBeaver / TablePlus / pgAdmin):** run the **Cloud SQL Auth Proxy**
  (`cloud-sql-proxy PROJECT:REGION:INSTANCE`) and connect the GUI to `127.0.0.1:5432`.
- **Local dev:** the DB is the file `app/backend/ssd_local.db`; open with
  [DB Browser for SQLite](https://sqlitebrowser.org).

### Backups & safety

- Cloud SQL has **automated daily backups** on by default — verify the schedule and set a
  retention window; enable **point-in-time recovery** for a production lender.
- Take a manual backup before big changes: `gcloud sql backups create --instance=<instance>`.
- Never edit passwords by hand in SQL — they're bcrypt-hashed. Use the app or `manage.py`.

### The schema (what lives where)

| Table | Holds |
|-------|-------|
| `users` | logins: name, email, **bcrypt password**, role, branch, banks, pincodes, base lat/lng, active flag |
| `cases` | loan accounts: customer, bank, account/card, address, pincode, lat/lng, bucket, funded/received/pending, status, disposition, assignments, follow-up |
| `visits` | field visits: GPS, accuracy, photo, geo-fence distance, paid, amount, disposition, note |
| `call_logs` | calls **and** payments: disposition, ptp amount/date, note, caller |
| `location_pings` | field-agent GPS pings for live tracking + route history |
| `import_batches` | every Excel upload |
| `legal_cases` | litigation matters (Sec 138 / SARFAESI / Arbitration…), stage, next hearing |
| `message_templates` | reusable WhatsApp/SMS templates |
| `leaves` / `devices` | leave requests; approved login devices |

Money columns are `NUMERIC(14,2)` and computed with Python `Decimal`, so totals are exact.
Hot columns (`email`, `account_no`, `pincode`, `status`, `follow_up_date`, `next_hearing_date`)
are already indexed. New columns auto-migrate on boot, so redeploys never need a manual migration.

### Handy read-only SQL (audits)

```sql
-- collections by bank
SELECT bank, COUNT(*) accounts, SUM(received_amount) received, SUM(pending_amount) pending
FROM cases GROUP BY bank;

-- recent field activity
SELECT created_at, disposition, amount_collected FROM visits ORDER BY created_at DESC LIMIT 50;

-- promises to pay due today or overdue
SELECT case_id, ptp_amount, ptp_date FROM call_logs
WHERE disposition='PTP' AND ptp_date <= now() ORDER BY ptp_date;
```

For day-to-day, prefer the in-app **Activity** feed, **Accounts** drawer, **PTP Tracker**, and
**Accounts → ⬇ Export Excel** — they keep roles, scoping and money math consistent. Use raw SQL
mainly for read-only audits.

---

## 6. Go-live hardening checklist

- [ ] `ENVIRONMENT=production` set; app boots (rejects the default `SECRET_KEY`).
- [ ] `SECRET_KEY`, `DATABASE_URL`, API keys in **Secret Manager** (not plain env).
- [ ] Google Maps key **restricted** to your Cloud Run URL / domain; only Maps JS + Geocoding enabled.
- [ ] Admin default password changed; test each role login (see the acceptance matrix in `GO_LIVE.md`).
- [ ] Cloud SQL backups + point-in-time recovery verified.
- [ ] Custom domain mapped (optional) with HTTPS.

## 7. Known follow-ups

- **Visit photos** currently save to the container disk (ephemeral on Cloud Run) — move to
  **Google Cloud Storage** before heavy field use.
- **2FA / biometric (WebAuthn)** and **login rate-limiting + password-reset** are planned;
  build after go-live (needs the HTTPS URL).
- For serving multiple NBFCs as SaaS, see the multi-tenancy options discussed with the team
  (isolated instance per client, or shared multi-tenant with `organization_id`).
