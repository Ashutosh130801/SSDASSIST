"""Photo storage — Google Cloud Storage when GCS_BUCKET is set, else local ./uploads.

Visit photos on Cloud Run must NOT live on the container disk (it's ephemeral and
per-instance). Set GCS_BUCKET and the app uploads each photo to that bucket and serves
it back through a short-lived signed URL. With no bucket configured it transparently
falls back to the local uploads folder, so nothing breaks in local/dev.
"""
import os
import uuid
from datetime import timedelta

from .config import get_settings

settings = get_settings()

_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(_UPLOAD_DIR, exist_ok=True)

_GCS_PREFIX = "gcs://"
_client = None


def _bucket():
    global _client
    if _client is None:
        from google.cloud import storage as gcs  # imported lazily; optional dependency
        _client = gcs.Client()
    return _client.bucket(settings.gcs_bucket)


def save_photo(content: bytes, filename: str = "", content_type: str = "image/jpeg") -> str:
    """Persist bytes and return a stored reference (an opaque string)."""
    ext = (os.path.splitext(filename or "")[1] or ".jpg").lower()
    key = f"visits/{uuid.uuid4().hex}{ext}"
    if settings.gcs_bucket:
        blob = _bucket().blob(key)
        blob.upload_from_string(content, content_type=content_type or "image/jpeg")
        return f"{_GCS_PREFIX}{key}"
    # local fallback — flat filename served by the /uploads static mount
    fname = key.replace("/", "_")
    with open(os.path.join(_UPLOAD_DIR, fname), "wb") as f:
        f.write(content)
    return f"/uploads/{fname}"


def resolve(ref):
    """Turn a stored reference into a URL a browser <img> can load.

    Local refs ('/uploads/..') are already servable and returned as-is.
    GCS refs are turned into a fresh signed URL each time.
    """
    if not ref:
        return ref
    if ref.startswith(_GCS_PREFIX):
        key = ref[len(_GCS_PREFIX):]
        try:
            return _bucket().blob(key).generate_signed_url(
                version="v4",
                expiration=timedelta(seconds=settings.gcs_signed_url_seconds),
                method="GET",
            )
        except Exception:
            return None
    return ref
