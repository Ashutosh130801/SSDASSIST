#!/usr/bin/env bash
# =====================================================================
#  SSD Recovery — deploy to Google Cloud Run + Cloud SQL (Postgres)
#  Run from the "app" folder:  bash deploy/deploy.sh
#  Prereqs: gcloud CLI installed & logged in (gcloud auth login)
# =====================================================================
set -euo pipefail

# ---------- EDIT THESE ----------
PROJECT="ssd-recovery"
REGION="asia-south1"          # Mumbai
SERVICE="ssd-recovery"
SQL_INST="ssd-db"
DB_NAME="ssd_recovery"
DB_USER="ssd"
DB_PASS="CHANGE_ME_strong_password"
MAPS_KEY=""
GEMINI_KEY=""
SECRET_KEY="$(python -c 'import secrets;print(secrets.token_hex(32))' 2>/dev/null || openssl rand -hex 32)"
# --------------------------------

CONN="${PROJECT}:${REGION}:${SQL_INST}"

echo "== project & APIs =="
gcloud config set project "$PROJECT"
gcloud services enable run.googleapis.com sqladmin.googleapis.com \
  artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com

echo "== Cloud SQL (create if missing) =="
gcloud sql instances describe "$SQL_INST" >/dev/null 2>&1 || \
  gcloud sql instances create "$SQL_INST" --database-version=POSTGRES_16 \
    --tier=db-f1-micro --region="$REGION" --storage-size=10
gcloud sql databases describe "$DB_NAME" --instance="$SQL_INST" >/dev/null 2>&1 || \
  gcloud sql databases create "$DB_NAME" --instance="$SQL_INST"
gcloud sql users describe "$DB_USER" --instance="$SQL_INST" >/dev/null 2>&1 || \
  gcloud sql users create "$DB_USER" --instance="$SQL_INST" --password="$DB_PASS"

DATABASE_URL="postgresql+psycopg2://${DB_USER}:${DB_PASS}@/${DB_NAME}?host=/cloudsql/${CONN}"

echo "== deploy to Cloud Run =="
gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --add-cloudsql-instances "$CONN" \
  --memory 512Mi --cpu 1 --min-instances 0 --max-instances 4 --timeout 60 \
  --set-env-vars "DATABASE_URL=${DATABASE_URL}" \
  --set-env-vars "SECRET_KEY=${SECRET_KEY}" \
  --set-env-vars "GOOGLE_MAPS_API_KEY=${MAPS_KEY}" \
  --set-env-vars "GEMINI_API_KEY=${GEMINI_KEY}" \
  --set-env-vars "LOCATION_PING_SECONDS=60"

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format 'value(status.url)')"
echo "-------------------------------------------------------------"
echo " Deployed: $URL"
echo " First run only: redeploy once adding --set-env-vars SEED_ON_START=1"
echo " to create the admin, then remove it. Login admin@ssdrecovery.in/admin123"
echo "-------------------------------------------------------------"
