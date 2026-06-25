"""Save uploaded inspection evidence files to disk for the document pipeline.

Minimal local-disk helper for ``api.routes.evidence``. Returns a path that
``document_text_extraction.extract_document()`` can read. Swap ``storage_root``
or replace this module with S3/GCS when deploying to object storage.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from services.file_storage import BASE_UPLOAD_DIR

# Override in deployment via EVIDENCE_STORAGE_ROOT; defaults under backend/uploads.
EVIDENCE_STORAGE_ROOT = Path(
    os.environ.get("EVIDENCE_STORAGE_ROOT", str(BASE_UPLOAD_DIR / "evidence_uploads"))
)

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}


class UnsupportedEvidenceFileType(ValueError):
    """Raised when the uploaded file extension is not supported."""


def evidence_storage_dir(project_id: int) -> Path:
    """Per-project subdirectory under the evidence upload root."""
    return EVIDENCE_STORAGE_ROOT / "projects" / str(project_id)


def storage_key_from_path(saved_path: Path) -> str:
    """Relative key stored on EvidenceRecord.storage_key (under BASE_UPLOAD_DIR layout)."""
    resolved = saved_path.resolve()
    uploads_root = BASE_UPLOAD_DIR.resolve()
    try:
        return str(resolved.relative_to(uploads_root))
    except ValueError:
        return str(saved_path)


def save_upload(
    original_filename: str,
    file_bytes: bytes,
    *,
    storage_root: Path | None = None,
) -> Path:
    """Persist an uploaded evidence file to disk and return its absolute path."""
    if not file_bytes:
        raise ValueError("Uploaded file is empty.")

    suffix = Path(original_filename or "evidence").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise UnsupportedEvidenceFileType(
            f"Unsupported evidence file type {suffix!r}. "
            f"Allowed: {sorted(ALLOWED_EXTENSIONS)}"
        )

    root = storage_root or EVIDENCE_STORAGE_ROOT
    root.mkdir(parents=True, exist_ok=True)

    saved_path = root / f"{uuid.uuid4().hex}{suffix}"
    saved_path.write_bytes(file_bytes)
    return saved_path.resolve()


def delete_upload(path: Path) -> None:
    """Best-effort cleanup — never raises if the file is already gone."""
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass
