# Production image for Google Cloud Run — serves the API AND the frontend PWA.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

# Install Python deps first (better layer caching)
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

# App code + the frontend it serves (main.py serves ../frontend at "/")
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/

# Cloud Run provides $PORT (defaults to 8080). Bind uvicorn to it.
ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
