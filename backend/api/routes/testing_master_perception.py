"""Internal read of the stored master-drawing perception."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.dependencies import get_db
from services.master_perception import build_master_perception, list_master_drawings

router = APIRouter(prefix="/api/testing", tags=["testing"])


@router.get("/masters")
def get_testing_masters(
    q: str | None = Query(None),
    db: Session = Depends(get_db),
) -> dict:
    return {"masters": list_master_drawings(db, q)}


@router.get("/masters/{master_id}/perception")
def get_master_perception(
    master_id: int,
    page: int = Query(1, ge=1),
    evidenceRunId: int | None = Query(None),
    db: Session = Depends(get_db),
) -> dict:
    payload = build_master_perception(
        db,
        master_id,
        page=page,
        evidence_run_id=evidenceRunId,
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="Master drawing not found")
    return payload
