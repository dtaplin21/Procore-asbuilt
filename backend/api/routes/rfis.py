from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from database import get_db
from services.storage import StorageService
from models.schemas import RFI, RFICreate

router = APIRouter(prefix="/api/rfis", tags=["rfis"])

@router.get("", response_model=List[RFI])
async def get_rfis(
    project_id: Optional[str] = Query(None),
    limit: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    storage = StorageService(db)
    try:
        rfis = storage.get_rfis(project_id)
        if limit:
            rfis = rfis[:limit]
        return rfis
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch RFIs: {str(e)}")

@router.get("/{rfi_id}", response_model=RFI)
async def get_rfi(rfi_id: str, db: Session = Depends(get_db)):
    storage = StorageService(db)
    try:
        rfi = storage.get_rfi(rfi_id)
        if not rfi:
            raise HTTPException(status_code=404, detail="RFI not found")
        return rfi
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch RFI: {str(e)}")

@router.post("", response_model=RFI, status_code=201)
async def create_rfi(rfi: RFICreate, db: Session = Depends(get_db)):
    storage = StorageService(db)
    try:
        rfi_data = rfi.model_dump()
        new_rfi = storage.create_rfi(rfi_data)
        return new_rfi
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create RFI: {str(e)}")

@router.patch("/{rfi_id}", response_model=RFI)
async def update_rfi(
    rfi_id: str,
    updates: dict,
    db: Session = Depends(get_db)
):
    storage = StorageService(db)
    try:
        rfi = storage.update_rfi(rfi_id, updates)
        if not rfi:
            raise HTTPException(status_code=404, detail="RFI not found")
        return rfi
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update RFI: {str(e)}")

