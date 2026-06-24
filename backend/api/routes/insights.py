from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from api.dependencies import get_db
from models.schemas import AIInsightResponse, InsightListResponse
from services.findings import workspace_link_metadata_for_finding
from services.storage import StorageService

router = APIRouter(prefix="/api/insights", tags=["insights"])


def _finding_to_insight(finding, db: Session) -> AIInsightResponse:
    """Convert Finding ORM to AIInsightResponse (id/str, camelCase, workspaceLink from run/overlay)."""
    base = AIInsightResponse.model_validate(finding)
    link = workspace_link_metadata_for_finding(finding, db)
    if link == base.workspace_link:
        return base
    return base.model_copy(update={"workspace_link": link})


@router.get("", response_model=InsightListResponse)
async def get_insights(
    project_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List AI findings/insights with pagination. Includes workspaceLink when tied to a drawing context."""
    storage = StorageService(db)
    items, total = storage.get_insights(project_id, limit=limit, offset=offset)
    insight_items = [_finding_to_insight(f, db) for f in items]
    return InsightListResponse(items=insight_items, total=total, limit=limit, offset=offset)


@router.patch("/{insight_id}/resolve", response_model=AIInsightResponse)
async def resolve_insight(insight_id: int, db: Session = Depends(get_db)):
    storage = StorageService(db)
    insight = storage.resolve_insight(insight_id)
    if not insight:
        raise HTTPException(status_code=404, detail="Insight not found")
    return _finding_to_insight(insight, db)

