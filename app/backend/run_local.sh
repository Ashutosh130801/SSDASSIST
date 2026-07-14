#!/usr/bin/env bash
# Quick local run WITHOUT Docker/Postgres (uses a local SQLite file for a fast trial).
# For production use Postgres via ../docker-compose.yml
set -e
cd "$(dirname "$0")"
export DATABASE_URL="${DATABASE_URL:-sqlite:///./ssd_local.db}"
export SECRET_KEY="${SECRET_KEY:-local-dev-secret}"
pip install -r requirements.txt
python -m app.seed
echo ">> Open http://localhost:8000"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
