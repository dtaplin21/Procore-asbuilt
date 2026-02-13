from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Any, Dict, List, Optional
from database import get_db
from services.storage import StorageService

router = APIRouter(prefix="/api/submittals", tags=["submittals"])

@router.get("")
async def get_submittals(
    project_id: Optional[str] = Query(None),
    limit: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    storage = StorageService(db)
    submittals = storage.get_submittals(project_id)
    if limit:
        submittals = submittals[:limit]
    return submittals

@router.get("/{submittal_id}")
async def get_submittal(submittal_id: str, db: Session = Depends(get_db)):
    storage = StorageService(db)
    submittal = storage.get_submittal(submittal_id)
    if not submittal:
        raise HTTPException(status_code=404, detail="Submittal not found")
    return submittal

@router.post("", status_code=201)
async def create_submittal(submittal: Dict[str, Any], db: Session = Depends(get_db)):
    storage = StorageService(db)
    return storage.create_submittal(submittal)

@router.patch("/{submittal_id}")
async def update_submittal(
    submittal_id: str,
    updates: dict,
    db: Session = Depends(get_db)
):
    storage = StorageService(db)
    submittal = storage.update_submittal(submittal_id, updates)
    if not submittal:
        raise HTTPException(status_code=404, detail="Submittal not found")
    return submittal

