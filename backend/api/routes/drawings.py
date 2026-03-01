from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile

router = APIRouter(tags=["drawings"])

# Local file storage root (adjust if you already have a standard storage location)
STORAGE_ROOT = Path(os.getenv("LOCAL_UPLOAD_ROOT", "backend/storage"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _project_drawings_dir(project_id: int) -> Path:
    return STORAGE_ROOT / "projects" / str(project_id) / "drawings"


def _meta_path(drawing_id: str, filename: str, dir_path: Path) -> Path:
    # keep metadata stable and easy to locate
    safe_name = filename.replace("/", "_").replace("\\", "_")
    return dir_path / f"{drawing_id}__{safe_name}.json"


def _file_path(drawing_id: str, filename: str, dir_path: Path) -> Path:
    safe_name = filename.replace("/", "_").replace("\\", "_")
    return dir_path / f"{drawing_id}__{safe_name}"


@router.post("/api/projects/{project_id}/drawings")
async def upload_drawing(project_id: int, file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    POST /api/projects/{project_id}/drawings
    Multipart upload a drawing file; persists file + sidecar metadata JSON.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    drawings_dir = _project_drawings_dir(project_id)
    drawings_dir.mkdir(parents=True, exist_ok=True)

    drawing_id = str(uuid4())
    dst = _file_path(drawing_id, file.filename, drawings_dir)

    # Stream to disk
    size = 0
    try:
        with dst.open("wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                f.write(chunk)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store file: {e}")

    meta = {
        "id": drawing_id,
        "project_id": project_id,
        "filename": file.filename,
        "content_type": file.content_type,
        "size_bytes": size,
        "stored_path": str(dst),
        "created_at": _now_iso(),
    }

    try:
        mp = _meta_path(drawing_id, file.filename, drawings_dir)
        mp.write_text(json.dumps(meta, indent=2))
    except Exception as e:
        # If metadata write fails, file exists but endpoint should signal issue
        raise HTTPException(status_code=500, detail=f"Stored file but failed to write metadata: {e}")

    return meta


@router.get("/api/projects/{project_id}/drawings")
def list_drawings(project_id: int) -> List[Dict[str, Any]]:
    """
    GET /api/projects/{project_id}/drawings
    Lists metadata for all uploaded drawings in local storage.
    """
    drawings_dir = _project_drawings_dir(project_id)
    if not drawings_dir.exists():
        return []

    items: List[Dict[str, Any]] = []
    for p in drawings_dir.glob("*.json"):
        try:
            items.append(json.loads(p.read_text()))
        except Exception:
            # Skip corrupted metadata files
            continue

    # Optional: sort newest first
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return items


@router.get("/api/projects/{project_id}/drawings/{drawing_id}")
def get_drawing_metadata(project_id: int, drawing_id: str) -> Dict[str, Any]:
    """
    GET /api/projects/{project_id}/drawings/{drawing_id}
    Returns metadata only (not the file bytes).
    """
    drawings_dir = _project_drawings_dir(project_id)
    if not drawings_dir.exists():
        raise HTTPException(status_code=404, detail="Drawing not found")

    # find metadata file by drawing_id prefix
    matches = list(drawings_dir.glob(f"{drawing_id}__*.json"))
    if not matches:
        raise HTTPException(status_code=404, detail="Drawing not found")

    try:
        meta = json.loads(matches[0].read_text())
    except Exception:
        raise HTTPException(status_code=500, detail="Drawing metadata is corrupted")

    # sanity check project match
    if int(meta.get("project_id", -1)) != project_id:
        raise HTTPException(status_code=404, detail="Drawing not found")

    return meta