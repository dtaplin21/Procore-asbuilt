"""Human inspection reviews: pass / fail for an alignment or scoped region."""

from fastapi import APIRouter, Depends, HTTPException

from database import get_db
from models.schemas import (
    DrawingInspectionReviewListResponse,
    DrawingInspectionReviewResponse,
    InspectionReviewSubmit,
)
from services.storage import StorageService
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/projects", tags=["inspection-reviews"])


@router.post(
    "/{project_id}/alignments/{alignment_id}/inspection-reviews",
    response_model=DrawingInspectionReviewResponse,
)
def submit_inspection_review(
    project_id: int,
    alignment_id: int,
    body: InspectionReviewSubmit,
    db: Session = Depends(get_db),
):
    """
    Record a human decision: **passed** or **failed** for the whole alignment,
    or for a specific ``drawing_regions`` row (must belong to the alignment's master).
    """
    storage = StorageService(db)
    try:
        row = storage.create_drawing_inspection_review(
            project_id=project_id,
            alignment_id=alignment_id,
            outcome=body.outcome,
            region_id=body.region_id,
            notes=body.notes,
            reviewer_user_id=body.reviewer_user_id,
        )
        return DrawingInspectionReviewResponse.model_validate(row)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get(
    "/{project_id}/alignments/{alignment_id}/inspection-reviews",
    response_model=DrawingInspectionReviewListResponse,
)
def list_inspection_reviews(
    project_id: int,
    alignment_id: int,
    db: Session = Depends(get_db),
):
    """List reviews for an alignment (newest first)."""
    storage = StorageService(db)
    rows = storage.list_drawing_inspection_reviews(
        project_id=project_id,
        alignment_id=alignment_id,
    )
    return DrawingInspectionReviewListResponse(
        items=[DrawingInspectionReviewResponse.model_validate(r) for r in rows],
    )
