# Deploying SSD Recovery to Google Cloud (Cloud Run + Cloud SQL)

Firebase Hosting can only serve static files, so it can't run this FastAPI backend
by itself. The correct Google-Cloud setup is:

- **Cloud Run** runs the app container (API **and** the frontend) → gives you an HTTPS URL.
- **Cloud SQL for PostgreSQL** is the database.
- **Firebase Hosting** is optional, only to put a custom domain/CDN in front of Cloud Run.

Everything below uses the `Dockerfile` and scripts already in this folder.

---

## 0. One-time prerequisites

1. A Google Cloud account with **billing enabled** (Cloud Run + Cloud SQL need it; cost is small — see the end).
2. Install the **gcloud CLI**: https://cloud.google.com/sdk/docs/install
3. Log in and create a project:
   ```
   gcloud auth login
   gcloud projects create ssd-recovery --name="SSD Recovery"
   gcloud config set project ssd-recovery
   ```
   Then enable billing for the project in the Cloud Console.

---

## 1. Fastest path — run the script

From the **`app`** folder:

- Windows PowerShell: `.\deploy\deploy.ps1`
- macOS/Linux: `bash deploy/deploy.sh`

Open the script first and edit the variables at the top (**project id, region,
DB password, Maps key, Gemini key**). It will:
enable the APIs → create the Cloud SQL Postgres instance, database and user →
build the container from source → deploy to Cloud Run wired to Cloud SQL → print your URL.

### Create the admin on the first deploy
The cloud database starts empty. Run the deploy **once more** with seeding on:
```
gcloud run services update ssd-recovery --region asia-south1 --set-env-vars SEED_ON_START=1
# log in once at the URL, then turn it back off:
gcloud run services update ssd-recovery --region asia-south1 --remove-env-vars SEED_ON_START
```
Login: `admin@ssdrecovery.in` / `admin123` — **change this password immediately** (Admin → Staff).

---

## 2. Manual steps (what the script does)

```bash
PROJECT=ssd-recovery ; REGION=asia-south1 ; SQL=ssd-db
gcloud services enable run.googleapis.com sqladmin.googleapis.com cloudbuild.googleapis.com

# Postgres instance + db + user
gcloud sql instances create $SQL --database-version=POSTGRES_16 --tier=db-f1-micro --region=$REGION --storage-size=10
gcloud sql databases create ssd_recovery --instance=$SQL
gcloud sql users create ssd --instance=$SQL --password='STRONG_PASSWORD'

# Deploy (Cloud Run builds the Dockerfile from source)
CONN=$PROJECT:$REGION:$SQL
gcloud run deploy ssd-recovery --source . --region $REGION --allow-unauthenticated \
  --add-cloudsql-instances $CONN \
  --set-env-vars "DATABASE_URL=postgresql+psycopg2://ssd:STRONG_PASSWORD@/ssd_recovery?host=/cloudsql/$CONN" \
  --set-env-vars "SECRET_KEY=$(openssl rand -hex 32)" \
  --set-env-vars "GOOGLE_MAPS_API_KEY=YOUR_KEY,GEMINI_API_KEY=YOUR_KEY,LOCATION_PING_SECONDS=60"
```

The Cloud SQL connection uses a unix socket at `/cloudsql/PROJECT:REGION:INSTANCE`,
which is why `DATABASE_URL` has `?host=/cloudsql/...`. No code changes needed —
SQLAlchemy + psycopg2 handle it, and the app auto-creates its tables on boot.

---

## 3. Keys & settings to set on Cloud Run

| Env var | What | Needed for |
|--------|------|-----------|
| `DATABASE_URL` | Cloud SQL socket URL (above) | required |
| `SECRET_KEY` | long random string | required (JWT signing) |
| `GOOGLE_MAPS_API_KEY` | Maps JS **+** Geocoding API enabled | maps, live tracking, geocoding |
| `GEMINI_API_KEY` | Google AI Studio key | AI assist (optional) |
| `GOOGLE_CLIENT_ID` | OAuth web client id | Google sign-in (optional) |
| `LOCATION_PING_SECONDS` | e.g. `60` | FO location cadence |

**Restrict your Maps key** to your Cloud Run URL (and later your custom domain) under
*APIs & Services → Credentials → HTTP referrers*. HTTPS from Cloud Run is what unlocks
GPS + camera on field officers' phones.

For production, store secrets in **Secret Manager** and pass `--set-secrets`
(e.g. `--set-secrets DATABASE_URL=ssd-db-url:latest`) instead of `--set-env-vars`.

---

## 4. Optional — Firebase Hosting in front (custom domain)

```
firebase init hosting          # pick your project; use the provided deploy/firebase.json as a guide
firebase deploy --only hosting
```
The rewrite in `deploy/firebase.json` forwards all traffic to the Cloud Run service, so
`https://yourdomain.web.app` serves the app. Update `serviceId`/`region` to match your deploy.

---

## 5. Important limitations to plan for

- **Visit photos** (GPS-camera images) are currently written to the container's local
  disk, which on Cloud Run is **ephemeral** and not shared between instances — photos
  would be lost on restart/scale. Before real field use, switch photo storage to
  **Google Cloud Storage**. (Ask me to wire this — it's a small change to the visits route.)
- **Cold starts / cost:** `min-instances 0` scales to zero (cheapest) but the first
  request after idle is slow. The 1-minute live-location pings keep it warm during work
  hours. Set `--min-instances 1` for zero cold starts (small always-on cost).
- **Rough cost:** Cloud SQL `db-f1-micro` + light Cloud Run traffic is typically a few
  US dollars/month at your volume; scales with usage.
- Change the demo passwords, and set a strong `SECRET_KEY`, before going live.
