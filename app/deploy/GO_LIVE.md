# SSD Recovery — Go-Live: deploy, run & test with real users

This is the end-to-end checklist to put the app into production on Google Cloud,
with real staff and real integrations, and verify security across every role.

---

## 0. What's "real" vs configured

Nothing in the app is mocked. These integrations turn on when you supply keys:

| Integration | How to enable | Used for |
|-------------|---------------|----------|
| **PostgreSQL (Cloud SQL)** | `DATABASE_URL` | all data storage |
| **Google Maps JS API** | `GOOGLE_MAPS_API_KEY` | live map, FO map, route replay |
| **Google Geocoding API** | same key (enable Geocoding) | address → map pin |
| **Gemini** | `GEMINI_API_KEY` | AI assist |
| **Google Sign-In** | `GOOGLE_CLIENT_ID` | optional passwordless login |

Demo data has been removed: the seed now creates **only your admin**; login screen has
no demo credentials. Real staff are created by the admin inside the app.

---

## 1. Pre-flight on your PC (before deploying)

```
cd %USERPROFILE%\Claude\Projects\SSDASSIST\app\backend
.venv\Scripts\activate

REM boots the whole app (all roles/features) — should print "boots OK"
python -c "import app.main; print('boots OK,', len(app.main.app.routes), 'routes')"

REM security & auth self-test (seeds demo staff into a throwaway db, then asserts every rule)
set DATABASE_URL=sqlite:///./sec_test.db
set SECRET_KEY=sec-test
set SEED_DEMO=1
python security_test.py
```
Expect **"ALL SECURITY CHECKS PASSED ✅"**. Then delete the throwaway db: `del sec_test.db`.

The security test verifies: valid login, wrong-password/unknown-user rejected, no-token and
tampered-token blocked (401), role gates (staff can't import/allocate/geocode/manage
users/see devices or admin records → 403), per-user data scoping, FO can't touch a foreign
case, branch-manager sees only their branch, new-device blocked until approved, and disabled
accounts can't log in.

---

## 2. Deploy to Cloud Run + Cloud SQL

1. Install the **gcloud CLI**, then `gcloud auth login`. Create a project with **billing enabled**.
2. Edit **`app\deploy\deploy.ps1`** — set `PROJECT`, `REGION` (e.g. `asia-south1`), a strong
   `DB_PASS`, and your `MAPS_KEY` / `GEMINI_KEY`. `SECRET_KEY` is auto-generated.
3. From the **`app`** folder:
   ```
   .\deploy\deploy.ps1
   ```
   It enables APIs → creates Cloud SQL Postgres + db + user → builds the container →
   deploys to Cloud Run → prints your **https://…run.app** URL.
4. Set production mode (locks CORS, hides API docs, enforces a real secret):
   ```
   gcloud run services update ssd-recovery --region <REGION> --set-env-vars ENVIRONMENT=production
   ```

## 3. Create the real admin (first deploy only)

The cloud database starts empty. Seed just the admin, then turn seeding off:
```
gcloud run services update ssd-recovery --region <REGION> --set-env-vars SEED_ON_START=1
REM open the URL, sign in once, then:
gcloud run services update ssd-recovery --region <REGION> --remove-env-vars SEED_ON_START
```
Admin login = the `ADMIN_EMAIL` / `ADMIN_PASSWORD` from your env (defaults
`admin@ssdrecovery.in` / `admin123`). **Change this password immediately** after first login.

> Tip: set your own admin from the start by deploying with
> `--set-env-vars ADMIN_EMAIL=you@yourco.com,ADMIN_PASSWORD=aStrongPass`.

## 4. Lock down the integrations

- **Google Maps key** → *APIs & Services → Credentials* → restrict to HTTP referrers =
  your Cloud Run URL (and later your custom domain). Enable **Maps JavaScript API** +
  **Geocoding API**.
- Keep `DATABASE_URL`, `SECRET_KEY`, `GEMINI_API_KEY` in **Secret Manager** for production
  (`--set-secrets` instead of `--set-env-vars`).
- Confirm `ENVIRONMENT=production` is set (step 2.4).

---

## 5. Set up your real organisation (in the app, as admin)

1. **Staff → + Add staff** — create each real person with role **Field Officer**,
   **Telecaller**, or **Branch Manager**, their **branch**, employment type, joining date,
   and (for FOs) assigned pincodes + base lat/lng. Set a strong password for each.
2. **Cases → ⬆ Upload** — upload your real bank Excel(s) (ICICI / RBL / Axis). Preview →
   **Import & Allocate**. Cases auto-allocate by pincode / nearest FO.
3. **Cases → 📍 Geocode** — convert addresses to map pins.
4. Share the URL with staff; each installs it (**⬇ Install app** or Add-to-Home-Screen).

---

## 6. Multi-user acceptance test (do this after go-live)

Use **separate browsers/phones per person** so device-approval behaves realistically.

| Role | Log in as | Should be able to | Should NOT be able to |
|------|-----------|-------------------|-----------------------|
| **Admin** | your admin | everything: upload, allocate, all cases, live map of all FOs, records, staff, devices, leave approvals | — |
| **Branch Manager** | a manager | their branch's cases, team, live map (branch FOs only), approve branch leave, approve branch devices | see other branches; create admins |
| **Field Officer** | an FO | see only their cases (grouped by bank/bucket), FO Live Map (own position + today's route), log GPS visits + payments, apply leave | see other FOs' cases; import; approve anything |
| **Telecaller** | a telecaller | only their call queue (Due/Today/Upcoming), log calls/PTP/payments, PTP tracker, apply leave | field visits; import; other callers' cases |

Device-approval walkthrough:
1. FO logs in on **phone A** → allowed (first device auto-approved).
2. FO tries **phone B** → "awaiting approval" (blocked).
3. Admin (or branch manager) → **Devices** → **Approve** phone B → FO can now log in on B.

Live tracking walkthrough:
1. FO opens **Live Map** on their phone (grant location) → blue dot + today's route builds.
2. Admin → **Live Map** → sees the FO's marker moving (refreshes each minute).
3. Admin → **Staff → 🕘 Route** → pick a day → **Play** to replay the trail, **⬇ CSV** to export.

Money integrity spot-check: log a payment on a case → pending recalculates exactly; the
same figure appears in the case timeline, Records feed, and the Excel export.

---

## 7. Known production follow-ups

- **Visit photos** currently save to the container's local disk (ephemeral on Cloud Run).
  Move photo storage to **Google Cloud Storage** before heavy field use (ask me to wire it).
- **Phase 4 (WebAuthn passkey/biometric login + 2FA)** needs the HTTPS URL from this deploy —
  build it after go-live.
- Set `--min-instances 1` if you want zero cold-starts (small always-on cost).
- Back up Cloud SQL (automated backups are on by default; verify the schedule).
