from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from api.dependencies import get_db
from services.storage import StorageService, open_storage_path

router = APIRouter(tags=["drawing-files"])


@router.get("/api/projects/{project_id}/drawings/{drawing_id}/pages/{page_number}/image")
def get_rendered_drawing_page_image(
    project_id: int,
    drawing_id: int,
    page_number: int,
    db: Session = Depends(get_db),
):
    storage = StorageService(db)
    drawing = storage.get_drawing_by_id(drawing_id)

    if not drawing or drawing.project_id != project_id:
        raise HTTPException(status_code=404, detail="Drawing not found")

    rendition = storage.get_drawing_rendition(drawing_id, page_number)
    if not rendition:
        if drawing.processing_status in ("pending", "processing"):
            raise HTTPException(
                status_code=409, detail="Drawing rendition is not ready yet"
            )
        raise HTTPException(status_code=404, detail="Rendered page image not found")

    abs_path = open_storage_path(rendition.image_storage_key)
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="Rendered page image file missing")

    return FileResponse(
        path=str(abs_path),
        media_type=rendition.mime_type,
        filename=abs_path.name,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
