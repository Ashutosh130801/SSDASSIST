# SSD Recovery — Collections & Recovery Command Centre

A centralized, mobile-first app for SSD Enterprises to run loan recovery across **ICICI,
RBL and Axis** with three roles — **Admin**, **Field Officer (FOS)** and **Telecaller** —
replacing the WhatsApp-to-Excel manual workflow with a single database, automatic
allocation, live field-officer tracking, interactive analytics, an AI assistant, and
one-click Excel in/out.

It ships as a **mobile PWA** (installs to a phone home screen) backed by a **FastAPI +
PostgreSQL** API. Glassmorphism UI, gold-on-dark SSD brand.

---

## What it does

| Area | Capability |
|------|-----------|
| **Auth & roles** | JWT login (email/password) + optional Google Sign-In. Role-based access: admin = full; FOS = only their allocated field cases; telecaller = only their call queue. |
| **Data load** | Admin uploads your Excel (loading-file *or* Axis live-sheet layouts auto-detected). Cases are created/updated; money parsed with `Decimal` (exact to the paisa). |
| **Auto allocation** | On upload (or on demand). Matches a case pincode to an FO's assigned pincodes; falls back to the **nearest FO by GPS**; load-balances ties. Telecallers assigned by bank + least load. |
| **Field visits** | FO logs a visit: GPS-camera photo, live GPS + accuracy, "location correct?", "person moved?", paid/amount, disposition, note — all the things done manually over WhatsApp today. The case's received/pending totals update automatically. |
| **Live tracking** | FO app pings location every 60s (configurable). Admin sees every officer live on a Google Map with auto-refresh, plus movement trails. |
| **Telecaller** | Call queue with dispositions (RTP/PTP/RNR…), PTP amount & date. |
| **Analytics** | Interactive dashboard: KPIs, 14-day collections trend, paid/unpaid split, by-bank received vs pending, dispositions, FO leaderboard. |
| **AI assist** | Gemini-powered helper grounded in your live numbers — prioritise cases, draft reminders/call scripts, explain the dashboard. |
| **Export** | One click downloads the full, up-to-date tracker as `.xlsx` — who visited, paid or not, GPS, notes, per case. |

---

## Quick start (Docker — recommended)

```bash
cd app
cp backend/.env.example backend/.env      # then edit backend/.env (keys below)
docker compose up --build
```

Open **http://localhost:8000** on your computer, or `http://<your-LAN-ip>:8000` on your
phone (same Wi-Fi) and "Add to Home Screen".

The stack seeds demo staff and starts Postgres automatically.

### Demo logins
| Role | Email | Password |
|------|-------|----------|
| Admin | `admin@ssdrecovery.in` | `admin123` |
| Field Officer | `ravi@ssdrecovery.in` | `fos123` |
| Telecaller | `krishna@ssdrecovery.in` | `tc123` |

> Change these before real use (Admin → Staff, or edit `.env` + `seed.py`).

---

## Run without Docker

```bash
cd app/backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export DATABASE_URL="postgresql+psycopg2://ssd:ssd_password@localhost:5432/ssd_recovery"
# (or for a quick local trial with no Postgres: export DATABASE_URL="sqlite:///./ssd.db")
python -m app.seed                 # create staff (optionally: python -m app.seed path/to/loading.xlsx ICICI)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend is served by the backend at `/` — nothing else to build (React + Babel load from CDN).

---

## Configuration — `backend/.env`

```
DATABASE_URL=postgresql+psycopg2://ssd:ssd_password@localhost:5432/ssd_recovery
SECRET_KEY=<long-random-string>          # sign JWTs — required for production
GOOGLE_MAPS_API_KEY=<your key>           # enables the live map + FO map views
GOOGLE_CLIENT_ID=<oauth web client id>   # optional: enables Google Sign-In button
GEMINI_API_KEY=<AI Studio key>           # enables AI assist (graceful fallback if empty)
GEMINI_MODEL=gemini-2.0-flash            # your account's Flash model id
LOCATION_PING_SECONDS=60                  # FO live-location cadence
```

- **Google Maps key:** enable *Maps JavaScript API*, restrict to your domain, paste the key.
- **Gemini:** the frontend answer degrades gracefully (still shows your live numbers) until a key is set. `GEMINI_MODEL` is whatever Flash id your key exposes.

---

## Uploading cases & downloading the tracker

Admin → **Cases**:
- **⬆ Upload** — pick an `.xlsx`, optionally set a default bank, **Preview**, then **Import & Allocate**. Existing accounts are updated (amounts/status), new ones created, then auto-allocated.
- **⚡ Auto-allocate** — re-runs allocation over any unassigned open cases.
- **⬇ Export Excel** — the live tracker with visit history, GPS, paid/unpaid and notes.

Recognised columns include: `CUS NAME/NAMES`, `ACCOUNT NO/ACC.NO`, `CC NO`, `PHONE`,
`ADDRESS`, `BANK`, `BKT`, `CYC`, `FUNDING AMOUNT/AMOUNT`, `RECEIVED AMOUNT`, `PENDING AMOUNT`,
`TOS/POS/TAD/MAD`, `FOS`, `CALLER/TC NAME`, `PAID/UNPAID`, `DISPO`, `REMARKS`. Pincodes are
auto-extracted from the address when not present.

---

## Architecture

```
app/
├─ backend/                 FastAPI + SQLAlchemy (Postgres; SQLite fallback)
│  ├─ app/
│  │  ├─ models.py          User, Case, Visit, CallLog, LocationPing, ImportBatch
│  │  ├─ allocation.py      pincode-match → nearest-FO(GPS) → load-balance
│  │  ├─ excel_io.py        Decimal-safe import (auto layout detect) + export
│  │  ├─ routers/           auth, users, cases, imports, visits, calls, tracking, analytics, ai
│  │  ├─ security.py        bcrypt + JWT
│  │  └─ main.py            serves the API and the PWA
│  └─ Dockerfile
├─ frontend/                Installable PWA (React via CDN, Chart.js, Google Maps)
│  ├─ index.html · app.jsx · styles.css · manifest.webmanifest · sw.js
└─ docker-compose.yml       Postgres + API
```

**Money integrity:** every amount is stored as SQL `NUMERIC(14,2)` and computed with Python
`Decimal` (half-up rounding). Received/pending are derived server-side on every visit and
edit, so totals stay exact and consistent.

**Security:** passwords hashed with bcrypt; all `/api/*` routes require a Bearer JWT; each
role's data is scoped in the query layer (an FO literally cannot read another FO's cases);
only admins can import, allocate, manage staff and export.

---

## Notes & next steps

- This is a runnable MVP of the full workflow. Natural follow-ups: push notifications for new
  allocations, offline visit queue with background sync, WhatsApp API for auto-reminders,
  Alembic migrations, per-branch admin scoping, and a Play Store/App Store wrapper (Capacitor)
  around the same PWA.
- For production: set a strong `SECRET_KEY`, restrict CORS, put HTTPS in front (maps/GPS/camera
  require HTTPS on real phones), and change the demo passwords.
```
