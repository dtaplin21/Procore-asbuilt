from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Any, Dict, List, Optional
from database import get_db
from services.storage import StorageService

router = APIRouter(prefix="/api/rfis", tags=["rfis"])

@router.get("")
async def get_rfis(
    project_id: Optional[str] = Query(None),
    limit: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    storage = StorageService(db)
    rfis = storage.get_rfis(project_id)
    if limit:
        rfis = rfis[:limit]
    return rfis

@router.get("/{rfi_id}")
async def get_rfi(rfi_id: str, db: Session = Depends(get_db)):
    storage = StorageService(db)
    rfi = storage.get_rfi(rfi_id)
    if not rfi:
        raise HTTPException(status_code=404, detail="RFI not found")
    return rfi

@router.post("", status_code=201)
async def create_rfi(rfi: Dict[str, Any], db: Session = Depends(get_db)):
    storage = StorageService(db)
    return storage.create_rfi(rfi)

@router.patch("/{rfi_id}")
async def update_rfi(
    rfi_id: str,
    updates: dict,
    db: Session = Depends(get_db)
):
    storage = StorageService(db)
    rfi = storage.update_rfi(rfi_id, updates)
    if not rfi:
        raise HTTPException(status_code=404, detail="RFI not found")
    return rfi

