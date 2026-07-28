# RecoverIQ — Production Go-Live (Railway) — precise steps

This is the exact, ordered checklist to take the app from demo to real production on
**Railway** (managed host + managed Postgres), then create real staff, import real data,
and ship the Android app. Follow top to bottom.

Facts this relies on (already true in the repo):
- `app/Dockerfile` builds ONE service that runs the API **and** serves the web app, and
  binds to Railway's injected `$PORT`.
- On boot with `SEED_ON_START=1`, the app creates **only** the admin account
  (demo staff are created only if you also set `SEED_DEMO=1` — you will NOT set that).
- The app **refuses to start in production** unless `SECRET_KEY` is a strong non-default value.
- The live sheet / presence / live updates use a single in-process WebSocket hub, so the
  service must run as **exactly one instance** (no horizontal autoscaling).

---

## PART A — Deploy the backend + web app on Railway

1. **Push the repo to GitHub** (private is fine). Make sure the `app/` folder (backend +
   frontend + Dockerfile) is included.

2. **Create the Railway project.** railway.app → New Project → **Deploy from GitHub repo**
   → pick this repo.

3. **Point the service at the app folder + Dockerfile.** Open the service → **Settings**:
   - **Root Directory:** `app`
   - **Builder:** Dockerfile (Railway auto-detects `app/Dockerfile`).

4. **Add Postgres.** In the project: **New → Database → PostgreSQL**. Railway provisions it
   and exposes a `DATABASE_URL`.

5. **Set environment variables** on the API service (Variables tab). Required:

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (reference the Postgres plugin) |
   | `SECRET_KEY` | a long random string — generate with the command below |
   | `ENVIRONMENT` | `production` |
   | `ADMIN_EMAIL` | your real admin login email |
   | `ADMIN_PASSWORD` | a strong password (you'll change it after first login) |
   | `SEED_ON_START` | `1`  *(first deploy only — see step 8)* |

   Generate a secret key (run locally):
   ```
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

   Optional (set later if/when you use them):
   - `GOOGLE_MAPS_API_KEY` — nicer maps/geocoding
   - `GCS_BUCKET` (+ Google service-account creds) — **recommended**: stores visit photos in
     cloud storage. Without it, photos sit on the container disk and are wiped on every
     redeploy.
   - `UPI_VPA` — your collection UPI id for pay links/QR
   - `GEMINI_API_KEY` — AI Assist
   - Do **NOT** set `SEED_DEMO`. Leave `CORS_ORIGINS` empty (backend serves the site same-origin).

6. **Deploy.** Railway builds the Dockerfile and starts the service. Watch the deploy logs
   until it's live. (If you ever see a Postgres driver error, change `DATABASE_URL` to start
   with `postgresql+psycopg2://` instead of `postgresql://`.)

7. **Get your permanent URL + lock to one instance.** Settings → **Networking → Generate
   Domain** (e.g. `recoveriq-production.up.railway.app`), or add a custom domain. Then in
   Settings make sure the service runs **1 replica / no autoscaling** (WebSocket requirement).

8. **Turn off first-run seeding.** After the first successful deploy, open the site, confirm
   you can log in as the admin, then **remove `SEED_ON_START`** (or set it to `0`) and
   redeploy. This prevents re-seed attempts on every restart.

9. **Health check:** visiting `https://<your-domain>/health` should return `{"status":"ok"}`.

---

## PART B — Create the real accounts (in the app)

Log in at `https://<your-domain>` as the admin.

10. **Secure the admin.** Change the admin password immediately, and turn on 2FA/passkey
    (Security screen).

11. **Understand the two IDs:**
    - **Login account** = email + password (what people sign in with).
    - **emp_code** (e.g. `TC001`, `FO001`) = auto-generated when you add a staff member; it's
      the code that must appear in the **CALLER / FOS columns of your upload sheets** so cases
      match to the right person.

12. **Create the org top-down (Team screen):**
    1. **Add branch** → this creates the branch's **manager** login.
    2. **Add staff** for each **team lead**, **field officer (FOS)**, and **telecaller**.
       Use real emails + strong passwords. Note each person's generated **emp_code**.
    3. Make sure those emp_codes (and the **team-lead names**) match what your real
       allocation files use in their CALLER / FOS / TEAM(-LEAD) columns — or standardize the
       files to the generated codes. (Team-lead visibility is driven by the team-lead **name**
       in the sheet.)

---

## PART C — Load real data

13. **Import allocation files.** Accounts → **Upload**, one product file at a time.
14. **Verify** against a sheet you trust: MIS/feedback totals, team-lead scoping (each lead
    sees only their named cases), paid/unpaid, and that callers/FOS see their own queues.

---

## PART D — Ship the Android app (single native APK)

15. In the **GitHub repo → Settings → Secrets and variables → Actions**, set:
    - `APP_URL` = `https://<your-domain>/`
    - Leave **`CERT_PIN` unset/empty for launch.** (Pinning to an auto-renewing certificate
      would make the app stop connecting every ~90 days. Ship without pinning first — it's
      still full HTTPS — and add a proper pin-with-backup later if you want it.)

16. Run the **"Build Native Android App"** workflow (Actions tab → Run workflow), or push a
    change. Download **`RecoverIQ-native.apk`** from the `android-native-latest` release.

17. **Distribute that one APK.** On each phone: uninstall any older RecoverIQ once, install
    the new APK, log in. The first device per user auto-approves; a later/changed device
    needs admin approval (Devices screen).

---

## PART E — Operations / safety rails

- **Backups:** enable Railway's Postgres backups (or schedule a daily `pg_dump`).
- **Rollback:** Railway keeps deploy history — one click to roll back a bad deploy.
- **Secrets:** never commit real `SECRET_KEY` / passwords; they live only in Railway Variables.
- **Retention:** FO location/route retention is already 90 days.
- **Monitoring:** watch `/health` and the Railway deploy logs.

## Rough cost
One always-on service + small Postgres on Railway ≈ **$10–25/month** at your scale.
