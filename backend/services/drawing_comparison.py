from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy.orm import Session

from models.models import Drawing, DrawingAlignment, DrawingDiff
from models.schemas import (
    DrawingSummary,
    DrawingAlignmentResponse,
    DrawingDiffResponse,
    DrawingDiffRegion,
)
from services.storage import StorageService
from ai.pipelines.drawing_diff import run_drawing_diff


class DrawingComparisonService:
    def __init__(self, db):
        self.db = db
        self.storage = StorageService(db)

    def _serialize_drawing(self, drawing: Drawing) -> DrawingSummary:
        return DrawingSummary(
            id=drawing.id,
            project_id=drawing.project_id,
            source=getattr(drawing, "source", None),
            name=drawing.name,
            file_url=getattr(drawing, "file_url", None),
            content_type=getattr(drawing, "content_type", None),
            page_count=getattr(drawing, "page_count", None),
        )

    def _serialize_alignment(self, alignment: DrawingAlignment) -> DrawingAlignmentResponse:
        project_id = None
        if alignment.master_drawing:
            project_id = alignment.master_drawing.project_id
        return DrawingAlignmentResponse(
            id=alignment.id,
            project_id=project_id,
            master_drawing_id=alignment.master_drawing_id,
            sub_drawing_id=alignment.sub_drawing_id,
            transform_matrix=getattr(alignment, "transform_matrix", None) or getattr(alignment, "transform", None),
            alignment_status=getattr(alignment, "alignment_status", None) or getattr(alignment, "status", None),
            created_at=alignment.created_at.isoformat() if getattr(alignment, "created_at", None) else None,
        )

    def _serialize_diff(self, diff: DrawingDiff) -> DrawingDiffResponse:
        raw_regions = getattr(diff, "diff_regions", None) or []

        diff_regions = [
            DrawingDiffRegion(
                page=region.get("page"),
                bbox=region.get("bbox"),
                change_type=region.get("change_type") or region.get("type"),
                note=region.get("note") or region.get("label"),
            )
            for region in raw_regions
        ]

        return DrawingDiffResponse(
            id=diff.id,
            alignment_id=diff.alignment_id,
            summary=getattr(diff, "summary", None),
            status=getattr(diff, "severity", None),
            diff_regions=diff_regions,
            created_at=diff.created_at.isoformat() if getattr(diff, "created_at", None) else None,
        )

    def _validate_project_drawings(
        self, project_id: int, master_drawing_id: int, sub_drawing_id: int
    ) -> tuple[Drawing, Drawing]:
        master_drawing = self.storage.get_drawing(project_id, master_drawing_id)
        sub_drawing = self.storage.get_drawing(project_id, sub_drawing_id)

        if not master_drawing:
            raise ValueError(f"Master drawing {master_drawing_id} not found")

        if not sub_drawing:
            raise ValueError(f"Sub drawing {sub_drawing_id} not found")

        if master_drawing.project_id != project_id:
            raise ValueError(
                f"Master drawing {master_drawing_id} does not belong to project {project_id}"
            )

        if sub_drawing.project_id != project_id:
            raise ValueError(
                f"Sub drawing {sub_drawing_id} does not belong to project {project_id}"
            )

        if master_drawing.id == sub_drawing.id:
            raise ValueError("Master drawing and sub drawing must be different")

        return master_drawing, sub_drawing


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
