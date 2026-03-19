from __future__ import annotations

from typing import Any, Dict

from sqlalchemy.orm import Session

from models.models import Drawing
from services.storage import StorageService
from ai.pipelines.drawing_diff import run_drawing_diff


def build_identity_transform(page: int = 1) -> Dict[str, Any]:
    return {
        "type": "homography",
        "matrix": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
        "confidence": 1.0,
        "page": page,
    }


def _serialize_drawing(drawing: Drawing) -> Dict[str, Any]:
    return {
        "id": drawing.id,
        "project_id": drawing.project_id,
        "source": drawing.source,
        "name": drawing.name,
        "file_url": getattr(drawing, "file_url", None),
        "content_type": getattr(drawing, "content_type", None),
        "page_count": getattr(drawing, "page_count", None),
    }


def _validate_project_drawings(
    storage: StorageService,
    *,
    project_id: int,
    master_drawing_id: int,
    sub_drawing_id: int,
) -> tuple[Drawing, Drawing]:
    master = storage.get_drawing(project_id=project_id, drawing_id=master_drawing_id)
    if master is None:
        raise ValueError("Master drawing not found for project")

    sub = storage.get_drawing(project_id=project_id, drawing_id=sub_drawing_id)
    if sub is None:
        raise ValueError("Sub drawing not found for project")

    if master.project_id != project_id or sub.project_id != project_id:
        raise ValueError("Drawings do not belong to the requested project")

    if master.id == sub.id:
        raise ValueError("Master drawing and sub drawing must be different")

    return master, sub


def compare_sub_drawing_to_master(
    db: Session,
    *,
    project_id: int,
    master_drawing_id: int,
    sub_drawing_id: int,
    force_recompute: bool = False,
) -> Dict[str, Any]:
    storage = StorageService(db)

    master, sub = _validate_project_drawings(
        storage,
        project_id=project_id,
        master_drawing_id=master_drawing_id,
        sub_drawing_id=sub_drawing_id,
    )

    alignment = storage.get_alignment_by_drawing_pair(
        master_drawing_id=master_drawing_id,
        sub_drawing_id=sub_drawing_id,
    )

    if alignment is None:
        alignment = storage.create_drawing_alignment(
            master_drawing_id=master_drawing_id,
            sub_drawing_id=sub_drawing_id,
            method="manual",
            region_id=None,
        )

    diffs = storage.list_drawing_diffs_by_alignment(alignment.id)

    if force_recompute or not diffs:
        new_diffs = run_drawing_diff(db, alignment=alignment)
        if new_diffs:
            diffs = new_diffs
        else:
            diffs = storage.list_drawing_diffs_by_alignment(alignment.id)

    return {
        "master_drawing": _serialize_drawing(master),
        "sub_drawing": _serialize_drawing(sub),
        "alignment": alignment,
        "diffs": diffs,
    }
