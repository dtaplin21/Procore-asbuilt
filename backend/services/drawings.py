from fastapi import HTTPException

from models.schemas import DrawingSummary
from services.storage import StorageService


class DrawingService:
    def __init__(self, db):
        self.db = db
        self.storage = StorageService(db)

    def _serialize_drawing(self, drawing, project_id: int):
        file_url = getattr(drawing, "file_url", None)
        if not file_url:
            file_url = f"/api/projects/{project_id}/drawings/{drawing.id}/file"
        return DrawingSummary(
            id=drawing.id,
            project_id=drawing.project_id,
            name=drawing.name,
            source=getattr(drawing, "source", None),
            file_url=file_url,
            content_type=getattr(drawing, "content_type", None),
            page_count=getattr(drawing, "page_count", None),
        )

    def list_project_drawings(self, project_id: int):
        project = self.storage.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        drawings = self.storage.list_drawings_by_project(project_id)

        return {
            "drawings": [
                self._serialize_drawing(drawing, project_id)
                for drawing in drawings
            ]
        }
