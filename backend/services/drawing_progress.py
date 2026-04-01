"""Aggregate drawing comparison progress for workspace / dashboard."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.schemas import DrawingProgressSummary
from services.storage import StorageService


class DrawingProgressService:
    def __init__(self, db: Session):
        self.db = db
        self.storage = StorageService(db)

    def get_master_drawing_progress(
        self,
        project_id: int,
        master_drawing_id: int,
    ) -> DrawingProgressSummary:
        if not self.storage.drawing_exists_in_project(project_id, master_drawing_id):
            raise HTTPException(status_code=404, detail=f"Drawing {master_drawing_id} not found")

        compared_sub_drawings_count = self.storage.count_compared_sub_drawings_for_master(
            project_id=project_id,
            master_drawing_id=master_drawing_id,
        )

        open_high_severity_diffs_count = self.storage.count_open_high_severity_diffs_for_master(
            project_id=project_id,
            master_drawing_id=master_drawing_id,
        )

        return DrawingProgressSummary(
            master_drawing_id=master_drawing_id,
            compared_sub_drawings_count=compared_sub_drawings_count,
            open_high_severity_diffs_count=open_high_severity_diffs_count,
        )
