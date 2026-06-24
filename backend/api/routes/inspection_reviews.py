"""Human inspection reviews: pass / fail for an alignment, inspection run, or region."""

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


def _submit_review(
    storage: StorageService,
    *,
    project_id: int,
    body: InspectionReviewSubmit,
    alignment_id: int | None = None,
    inspection_run_id: int | None = None,
) -> DrawingInspectionReviewResponse:
    try:
        row = storage.create_drawing_inspection_review(
            project_id=project_id,
            alignment_id=alignment_id,
            inspection_run_id=inspection_run_id,
            outcome=body.outcome,
            region_id=body.region_id,
            notes=body.notes,
            reviewer_user_id=body.reviewer_user_id,
        )
        return DrawingInspectionReviewResponse.model_validate(row)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post(
    "/{project_id}/alignments/{alignment_id}/inspection-reviews",
    response_model=DrawingInspectionReviewResponse,
)
def submit_inspection_review_for_alignment(
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
    return _submit_review(
        storage,
        project_id=project_id,
        body=body,
        alignment_id=alignment_id,
    )


@router.get(
    "/{project_id}/alignments/{alignment_id}/inspection-reviews",
    response_model=DrawingInspectionReviewListResponse,
)
def list_inspection_reviews_for_alignment(
    project_id: int,
    alignment_id: int,
    db: Session = Depends(get_db),
):
    """List reviews for an alignment (newest first)."""
    storage = StorageService(db)
    try:
        rows = storage.list_drawing_inspection_reviews(
            project_id=project_id,
            alignment_id=alignment_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return DrawingInspectionReviewListResponse(
        items=[DrawingInspectionReviewResponse.model_validate(r) for r in rows],
    )


@router.post(
    "/{project_id}/inspections/runs/{inspection_run_id}/inspection-reviews",
    response_model=DrawingInspectionReviewResponse,
)
def submit_inspection_review_for_run(
    project_id: int,
    inspection_run_id: int,
    body: InspectionReviewSubmit,
    db: Session = Depends(get_db),
):
    """
    Record a human decision for an inspection run (whole run or a scoped drawing region
    on the run's master sheet).
    """
    storage = StorageService(db)
    return _submit_review(
        storage,
        project_id=project_id,
        body=body,
        inspection_run_id=inspection_run_id,
    )


@router.get(
    "/{project_id}/inspections/runs/{inspection_run_id}/inspection-reviews",
    response_model=DrawingInspectionReviewListResponse,
)
def list_inspection_reviews_for_run(
    project_id: int,
    inspection_run_id: int,
    db: Session = Depends(get_db),
):
    """List reviews for an inspection run (newest first)."""
    storage = StorageService(db)
    try:
        rows = storage.list_drawing_inspection_reviews(
            project_id=project_id,
            inspection_run_id=inspection_run_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return DrawingInspectionReviewListResponse(
        items=[DrawingInspectionReviewResponse.model_validate(r) for r in rows],
    )
