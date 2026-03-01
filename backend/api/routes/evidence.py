from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

router = APIRouter(tags=["evidence"])

STORAGE_ROOT = Path(os.getenv("LOCAL_UPLOAD_ROOT", "backend/storage"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _project_evidence_dir(project_id: int, evidence_type: str) -> Path:
    safe_type = (evidence_type or "general").strip().lower().replace("/", "_").replace("\\", "_")
    return STORAGE_ROOT / "projects" / str(project_id) / "evidence" / safe_type


def _meta_path(evidence_id: str, filename: str, dir_path: Path) -> Path:
    safe_name = filename.replace("/", "_").replace("\\", "_")
    return dir_path / f"{evidence_id}__{safe_name}.json"


def _file_path(evidence_id: str, filename: str, dir_path: Path) -> Path:
    safe_name = filename.replace("/", "_").replace("\\", "_")
    return dir_path / f"{evidence_id}__{safe_name}"


@router.post("/api/projects/{project_id}/evidence")
async def upload_evidence(
    project_id: int,
    file: UploadFile = File(...),
    type: str = Form("general"),  # evidence type comes from the multipart form field "type"
) -> Dict[str, Any]:
    """
    POST /api/projects/{project_id}/evidence
    Multipart upload evidence. Provide evidence type via form field: type=photo|video|pdf|etc
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    evidence_dir = _project_evidence_dir(project_id, type)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    evidence_id = str(uuid4())
    dst = _file_path(evidence_id, file.filename, evidence_dir)

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
        "id": evidence_id,
        "project_id": project_id,
        "type": (type or "general").strip().lower(),
        "filename": file.filename,
        "content_type": file.content_type,
        "size_bytes": size,
        "stored_path": str(dst),
        "created_at": _now_iso(),
    }

    try:
        mp = _meta_path(evidence_id, file.filename, evidence_dir)
        mp.write_text(json.dumps(meta, indent=2))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stored file but failed to write metadata: {e}")

    return meta


@router.get("/api/projects/{project_id}/evidence")
def list_evidence(
    project_id: int,
    type: Optional[str] = Query(default=None),  # /evidence?type=photo
) -> List[Dict[str, Any]]:
    """
    GET /api/projects/{project_id}/evidence?type=...
    Lists evidence metadata (optionally filtered by type).
    """
    base_dir = STORAGE_ROOT / "projects" / str(project_id) / "evidence"
    if not base_dir.exists():
        return []

    items: List[Dict[str, Any]] = []

    if type:
        dirs = [base_dir / type.strip().lower().replace("/", "_").replace("\\", "_")]
    else:
        dirs = [p for p in base_dir.iterdir() if p.is_dir()]

    for d in dirs:
        if not d.exists():
            continue
        for p in d.glob("*.json"):
            try:
                items.append(json.loads(p.read_text()))
            except Exception:
                continue

    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return items