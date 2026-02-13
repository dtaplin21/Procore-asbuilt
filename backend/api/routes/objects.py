from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from database import get_db
from services.storage import StorageService

router = APIRouter(prefix="/api/objects", tags=["objects"])

@router.get("")
async def get_objects(
    project_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    storage = StorageService(db)
    return storage.get_objects(project_id)

@router.get("/{object_id}")
async def get_object(object_id: str, db: Session = Depends(get_db)):
    storage = StorageService(db)
    obj = storage.get_object(object_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Object not found")
    return obj

