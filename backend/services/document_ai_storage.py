"""GCS helpers for Document AI batch input/output."""

from __future__ import annotations

import uuid
from pathlib import Path

from config import settings


def _storage_client():
    from google.cloud import storage

    project = settings.google_cloud_project
    if project:
        return storage.Client(project=project)
    return storage.Client()


def split_gcs_uri(gcs_uri: str) -> tuple[str, str]:
    """Return ``(bucket_name, object_name)`` from ``gs://bucket/path/to/object``."""
    uri = gcs_uri.strip()
    if not uri.startswith("gs://"):
        raise ValueError(f"Expected gs:// URI, got {gcs_uri!r}")
    rest = uri[5:]
    bucket, _, blob = rest.partition("/")
    if not bucket or not blob:
        raise ValueError(f"Invalid GCS URI (need bucket and object path): {gcs_uri!r}")
    return bucket, blob


def gcs_uri(bucket: str, object_name: str) -> str:
    name = object_name.lstrip("/")
    return f"gs://{bucket}/{name}"


def upload_pdf(
    local_path: str | Path,
    *,
    bucket_name: str | None = None,
    object_name: str | None = None,
) -> str:
    """Upload a PDF and return its ``gs://`` URI."""
    bucket_name = bucket_name or settings.document_ai_gcs_input_bucket
    if not bucket_name:
        raise ValueError("DOCUMENT_AI_GCS_INPUT_BUCKET is not set")

    path = Path(local_path)
    if not path.is_file():
        raise FileNotFoundError(str(path))

    blob_name = object_name or f"batch-input/{uuid.uuid4().hex}/{path.name}"
    client = _storage_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(str(path), content_type="application/pdf")
    return gcs_uri(bucket_name, blob_name)


def download_bytes(*, bucket_name: str, object_name: str) -> bytes:
    client = _storage_client()
    blob = client.bucket(bucket_name).blob(object_name)
    return blob.download_as_bytes()


def download_gcs_uri(gcs_uri_str: str) -> bytes:
    bucket, blob = split_gcs_uri(gcs_uri_str)
    return download_bytes(bucket_name=bucket, object_name=blob)


def list_blob_names(*, bucket_name: str, prefix: str) -> list[str]:
    client = _storage_client()
    names: list[str] = []
    for blob in client.list_blobs(bucket_name, prefix=prefix.lstrip("/")):
        if blob.name.endswith("/"):
            continue
        names.append(blob.name)
    return sorted(names)
