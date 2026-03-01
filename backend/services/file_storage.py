from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Tuple
from uuid import uuid4
from fastapi import HTTPException, UploadFile

# Base upload directory (relative to project root)
BASE_UPLOAD_DIR = Path(__file__).parent.parent / "uploads"

# Allowed MIME types for uploads (expand as needed)
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/gif",
}

# Maximum acceptable upload size in bytes (e.g., 50 MiB)
MAX_UPLOAD_SIZE = 50 * 1024 * 1024


def _sanitize_filename(filename: str) -> str:
    # remove path separators and other dangerous chars
    name = os.path.basename(filename)
    name = re.sub(r"[^a-zA-Z0-9._-]", "_", name)
    return name


def save_upload(file: UploadFile, project_id: int, category: str) -> Tuple[str, str, str]:
    """Save an uploaded file to disk and return metadata.

    Returns (storage_key, content_type, original_name).
    """

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    # Check filesize by reading in chunks (can't rely solely on headers)
    size = 0
    contents = b""
    while True:
        chunk = file.file.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail="File too large")
        contents += chunk

    sanitized = _sanitize_filename(file.filename)
    key = f"projects/{project_id}/{category}/{uuid4().hex}_{sanitized}"
    dest_path = BASE_UPLOAD_DIR / key
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(dest_path, "wb") as f:
            f.write(contents)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save upload: {str(e)}")

    return key, file.content_type, file.filename


def get_file_path(storage_key: str) -> Path:
    """Return the absolute path of a stored file, raising if outside upload dir."""
    p = BASE_UPLOAD_DIR / storage_key
    try:
        p.resolve().relative_to(BASE_UPLOAD_DIR.resolve())
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid storage key")
    return p


def delete_file(storage_key: str) -> None:
    p = get_file_path(storage_key)
    if p.exists():
        p.unlink()
