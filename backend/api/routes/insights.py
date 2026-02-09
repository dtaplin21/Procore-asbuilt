from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from database import get_db
from services.storage import StorageService
from models.schemas import AIInsight

router = APIRouter(prefix="/api/insights", tags=["insights"])

@router.get("", response_model=List[AIInsight])
async def get_insights(
    project_id: Optional[str] = Query(None),
    limit: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    storage = StorageService(db)
    try:
        insights = storage.get_insights(project_id, limit)
        return insights
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch insights: {str(e)}")

@router.patch("/{insight_id}/resolve", response_model=AIInsight)
async def resolve_insight(insight_id: str, db: Session = Depends(get_db)):
    storage = StorageService(db)
    try:
        insight = storage.resolve_insight(insight_id)
        if not insight:
            raise HTTPException(status_code=404, detail="Insight not found")
        return insight
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to resolve insight: {str(e)}")

