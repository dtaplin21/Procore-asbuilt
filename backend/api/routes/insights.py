from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from database import get_db
from services.storage import StorageService

router = APIRouter(prefix="/api/insights", tags=["insights"])

@router.get("")
async def get_insights(
    project_id: Optional[str] = Query(None),
    limit: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    storage = StorageService(db)
    return storage.get_insights(project_id, limit)

@router.patch("/{insight_id}/resolve")
async def resolve_insight(insight_id: str, db: Session = Depends(get_db)):
    storage = StorageService(db)
    insight = storage.resolve_insight(insight_id)
    if not insight:
        raise HTTPException(status_code=404, detail="Insight not found")
    return insight

