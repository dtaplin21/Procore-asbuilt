from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.dependencies import get_db
from services.storage import StorageService
from models.schemas import (
    EvidenceRecordCreate,
    EvidenceRecordUpdate,
    EvidenceRecordResponse,
    EvidenceRecordListResponse,
)

router = APIRouter(prefix="/api/projects", tags=["evidence-records"])


@router.post("/{project_id}/evidence-records", response_model=EvidenceRecordResponse)
def create_evidence_record(
    project_id: int,
    payload: EvidenceRecordCreate,
    db: Session = Depends(get_db),
):
    storage = StorageService(db)

    project = storage.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    record = storage.create_evidence_record_from_data(project_id=project_id, data=payload.model_dump())
    return record


@router.get("/{project_id}/evidence-records", response_model=EvidenceRecordListResponse)
def list_evidence_records(
    project_id: int,
    limit: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    storage = StorageService(db)

    project = storage.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    items, _ = storage.list_evidence_records(
        project_id=project_id,
        limit=limit or 50,
        offset=0,
    )
    return {"evidence_records": items}


@router.get("/{project_id}/evidence-records/{evidence_id}", response_model=EvidenceRecordResponse)
def get_evidence_record(
    project_id: int,
    evidence_id: int,
    db: Session = Depends(get_db),
):
    storage = StorageService(db)

    record = storage.get_evidence_record(project_id=project_id, evidence_id=evidence_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Evidence record not found")

    return record


@router.patch("/{project_id}/evidence-records/{evidence_id}", response_model=EvidenceRecordResponse)
def update_evidence_record(
    project_id: int,
    evidence_id: int,
    payload: EvidenceRecordUpdate,
    db: Session = Depends(get_db),
):
    storage = StorageService(db)

    record = storage.update_evidence_record(
        project_id=project_id,
        evidence_id=evidence_id,
        updates=payload.model_dump(exclude_unset=True),
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Evidence record not found")

    return record


@router.delete("/{project_id}/evidence-records/{evidence_id}")
def delete_evidence_record(
    project_id: int,
    evidence_id: int,
    db: Session = Depends(get_db),
):
    storage = StorageService(db)

    deleted = storage.delete_evidence_record(project_id=project_id, evidence_id=evidence_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Evidence record not found")

    return {"ok": True}
