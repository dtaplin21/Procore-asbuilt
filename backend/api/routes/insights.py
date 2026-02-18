from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from database import get_db
from services.storage import StorageService
from models.schemas import AIInsightResponse

router = APIRouter(prefix="/api/insights", tags=["insights"])

@router.get("", response_model=List[AIInsightResponse])
async def get_insights(
    project_id: Optional[int] = Query(None),
    limit: Optional[int] = Query(4, ge=1, le=100),
    db: Session = Depends(get_db)
):
    storage = StorageService(db)
    return storage.get_insights(project_id, limit)

@router.patch("/{insight_id}/resolve", response_model=AIInsightResponse)
async def resolve_insight(insight_id: int, db: Session = Depends(get_db)):
    storage = StorageService(db)
    insight = storage.resolve_insight(insight_id)
    if not insight:
        raise HTTPException(status_code=404, detail="Insight not found")
    return insight

