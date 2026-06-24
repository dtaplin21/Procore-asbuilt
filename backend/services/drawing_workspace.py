"""Workspace helpers for drawing viewer serialization (non-compare)."""

from __future__ import annotations

from typing import Any, Dict, cast

from sqlalchemy.orm import Session

from models.models import Drawing
from services.storage import StorageService


def drawing_file_api_path(project_id: int, drawing_id: int) -> str:
    """Relative URL for GET /api/projects/{project}/drawings/{id}/file."""
    return f"/api/projects/{project_id}/drawings/{drawing_id}/file"


def serialize_drawing_for_workspace(
    db: Session, drawing: Drawing, active_page: int = 1
) -> Dict[str, Any]:
    """Serialize a drawing for workspace viewer, preferring rendered page image URL."""
    storage = StorageService(db)
    rendition = storage.get_drawing_rendition(cast(int, drawing.id), active_page)

    pid = cast(int, drawing.project_id)
    did = cast(int, drawing.id)
    source_file_url = drawing_file_api_path(pid, did)

    if rendition:
        file_url = f"/api/projects/{pid}/drawings/{did}/pages/{active_page}/image"
        width_px = rendition.width_px
        height_px = rendition.height_px
    else:
        file_url = source_file_url
        width_px = None
        height_px = None

    return {
        "id": did,
        "name": cast(str, drawing.name),
        "fileUrl": file_url,
        "sourceFileUrl": source_file_url,
        "pageCount": drawing.page_count or 1,
        "activePage": active_page,
        "widthPx": width_px,
        "heightPx": height_px,
        "processingStatus": getattr(drawing, "processing_status", "pending"),
        "processingError": getattr(drawing, "processing_error", None),
        "source": getattr(drawing, "source", None),
        "contentType": getattr(drawing, "content_type", None),
        "projectId": pid,
    }
