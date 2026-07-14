# =====================================================================
#  SSD Recovery — one-shot deploy to Google Cloud Run + Cloud SQL (Postgres)
#  Windows PowerShell. Run from the "app" folder:  .\deploy\deploy.ps1
#  Prereqs: gcloud CLI installed & logged in (gcloud auth login)
# =====================================================================
$ErrorActionPreference = "Stop"

# ---------- EDIT THESE ----------
$PROJECT   = "ssd-recovery"          # your GCP project id
$REGION    = "asia-south1"           # Mumbai (closest to AP/Telangana)
$SERVICE   = "ssd-recovery"          # Cloud Run service name
$SQL_INST  = "ssd-db"                # Cloud SQL instance name
$DB_NAME   = "ssd_recovery"
$DB_USER   = "ssd"
$DB_PASS   = "CHANGE_ME_strong_password"   # or set via Secret Manager (see DEPLOY.md)
$MAPS_KEY  = ""                       # Google Maps JS + Geocoding API key
$GEMINI_KEY= ""                       # Gemini API key (optional)
$SECRET_KEY= [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
# --------------------------------

$CONN = "$PROJECT`:$REGION`:$SQL_INST"      # PROJECT:REGION:INSTANCE

Write-Host "== Setting project & enabling APIs ==" -ForegroundColor Cyan
gcloud config set project $PROJECT
gcloud services enable run.googleapis.com sqladmin.googleapis.com `
    artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com

Write-Host "== Creating Cloud SQL Postgres instance (skips if it exists) ==" -ForegroundColor Cyan
gcloud sql instances describe $SQL_INST 2>$null
if ($LASTEXITCODE -ne 0) {
  gcloud sql instances create $SQL_INST --database-version=POSTGRES_16 `
    --tier=db-f1-micro --region=$REGION --storage-size=10
}
gcloud sql databases describe $DB_NAME --instance=$SQL_INST 2>$null
if ($LASTEXITCODE -ne 0) { gcloud sql databases create $DB_NAME --instance=$SQL_INST }
gcloud sql users describe $DB_USER --instance=$SQL_INST 2>$null
if ($LASTEXITCODE -ne 0) { gcloud sql users create $DB_USER --instance=$SQL_INST --password=$DB_PASS }

# SQLAlchemy/psycopg2 connects to Cloud SQL over a unix socket on Cloud Run:
$DATABASE_URL = "postgresql+psycopg2://$DB_USER`:$DB_PASS@/$DB_NAME`?host=/cloudsql/$CONN"

Write-Host "== Building & deploying to Cloud Run (source build) ==" -ForegroundColor Cyan
gcloud run deploy $SERVICE `
  --source . `
  --region $REGION `
  --allow-unauthenticated `
  --add-cloudsql-instances $CONN `
  --memory 512Mi --cpu 1 --min-instances 0 --max-instances 4 --timeout 60 `
  --set-env-vars "DATABASE_URL=$DATABASE_URL" `
  --set-env-vars "SECRET_KEY=$SECRET_KEY" `
  --set-env-vars "GOOGLE_MAPS_API_KEY=$MAPS_KEY" `
  --set-env-vars "GEMINI_API_KEY=$GEMINI_KEY" `
  --set-env-vars "LOCATION_PING_SECONDS=60"

$URL = gcloud run services describe $SERVICE --region $REGION --format "value(status.url)"
Write-Host ""
Write-Host "==============================================================" -ForegroundColor Green
Write-Host "  Deployed:  $URL" -ForegroundColor Green
Write-Host "  Login:     admin@ssdrecovery.in / admin123 (change immediately)" -ForegroundColor Green
Write-Host "  Add this URL to your Google Maps API key HTTP-referrer allowlist." -ForegroundColor Green
Write-Host "==============================================================" -ForegroundColor Green
