"""GCS cache keys for Document AI batch output (Phase 6)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from config import settings
from services.document_ai_storage import gcs_uri


def pdf_content_sha256(file_path: str | Path) -> str:
    path = Path(file_path)
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def cached_output_prefix(*, drawing_id: int, content_hash: str) -> str:
    """Stable GCS prefix for a drawing PDF at a given content hash."""
    bucket = settings.document_ai_gcs_output_bucket
    if not bucket:
        raise ValueError("DOCUMENT_AI_GCS_OUTPUT_BUCKET is not set")
    safe_hash = content_hash.strip().lower()
    return gcs_uri(bucket, f"batch-output/by-drawing/{int(drawing_id)}/{safe_hash}/")
