from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Tuple
from uuid import uuid4
from fastapi import HTTPException, UploadFile
from fastapi import Request
from fastapi.responses import FileResponse, Response

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

    sanitized = _sanitize_filename(file.filename or "upload")
    key = f"projects/{project_id}/{category}/{uuid4().hex}_{sanitized}"
    dest_path = BASE_UPLOAD_DIR / key
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(dest_path, "wb") as f:
            f.write(contents)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save upload: {str(e)}")

    return key, file.content_type, file.filename or "upload"


def get_file_path(storage_key: str) -> Path:
    """Return the absolute path of a stored file, raising if outside upload dir."""
    p = BASE_UPLOAD_DIR / storage_key
    try:
        p.resolve().relative_to(BASE_UPLOAD_DIR.resolve())
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid storage key")
    return p


def range_file_response(
    path: Path,
    request: Request,
    media_type: str,
    filename: str,
) -> Response:
    """Return a file response honoring a `Range` header if present.

    If the requester includes ``Range: bytes=start-end`` we slice the file
    and return a 206 partial response with appropriate ``Content-Range`` and
    ``Accept-Ranges`` headers.  Otherwise we fall back to a normal
    :class:`~fastapi.responses.FileResponse`.

    This helper keeps range logic in one place so callers in the routers can
    stay small and we can evolve the implementation later (streaming,
    caching, etc.) without touching every endpoint.
    """

    size = path.stat().st_size
    range_header = request.headers.get("range")
    if range_header:
        # simple parser; only support single range
        m = re.match(r"bytes=(\d*)-(\d*)", range_header)
        if m:
            try:
                start = int(m.group(1)) if m.group(1) else 0
                end = int(m.group(2)) if m.group(2) else size - 1
            except ValueError:
                return Response(status_code=400)
            if end >= size:
                end = size - 1
            if start > end:
                return Response(status_code=416)
            length = end - start + 1
            with open(path, "rb") as f:
                f.seek(start)
                data = f.read(length)
            headers = {
                "Content-Range": f"bytes {start}-{end}/{size}",
                "Accept-Ranges": "bytes",
            }
            return Response(data, status_code=206, media_type=media_type, headers=headers)
    # no range requested, send full file
    return FileResponse(path, media_type=media_type, filename=filename)


def delete_file(storage_key: str) -> None:
    p = get_file_path(storage_key)
    if p.exists():
        p.unlink()
