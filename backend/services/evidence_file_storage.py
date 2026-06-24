"""Save uploaded inspection evidence files to disk for the document pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from services.file_storage import get_file_path, save_upload_from_bytes


class UnsupportedEvidenceFileType(ValueError):
    """Raised when an uploaded file type is not supported for document extraction."""


_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/gif",
    "image/tiff",
    "image/webp",
}


@dataclass(frozen=True)
class SavedEvidenceUpload:
    storage_key: str
    file_path: Path
    content_type: str
    original_name: str


def save_upload(
    original_name: str,
    file_bytes: bytes,
    *,
    project_id: int,
    content_type: str,
) -> SavedEvidenceUpload:
    """Persist evidence bytes and return paths for ``extract_document()``."""
    if not file_bytes:
        raise ValueError("Uploaded file is empty.")

    normalized_type = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized_type not in _ALLOWED_CONTENT_TYPES:
        raise UnsupportedEvidenceFileType(
            f"Unsupported evidence file type: {content_type or 'unknown'!r}"
        )

    storage_key = save_upload_from_bytes(
        file_bytes,
        project_id,
        category="evidence",
        content_type=normalized_type,
        original_name=original_name or "evidence",
    )
    return SavedEvidenceUpload(
        storage_key=storage_key,
        file_path=get_file_path(storage_key),
        content_type=normalized_type,
        original_name=original_name or "evidence",
    )
