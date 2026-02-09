from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from database import get_db
from services.storage import StorageService
from models.schemas import DrawingObject, DrawingObjectCreate

router = APIRouter(prefix="/api/objects", tags=["objects"])

@router.get("", response_model=List[DrawingObject])
async def get_objects(
    project_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    storage = StorageService(db)
    try:
        objects = storage.get_objects(project_id)
        return objects
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch objects: {str(e)}")

@router.get("/{object_id}", response_model=DrawingObject)
async def get_object(object_id: str, db: Session = Depends(get_db)):
    storage = StorageService(db)
    try:
        obj = storage.get_object(object_id)
        if not obj:
            raise HTTPException(status_code=404, detail="Object not found")
        return obj
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch object: {str(e)}")

