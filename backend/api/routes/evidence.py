from typing import List, Optional, Any, cast
import json

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query, Depends
from sqlalchemy.orm import Session

from api.dependencies import get_db
from models.models import EvidenceRecord, Project
from models.schemas import EvidenceRecordResponse, EvidenceListResponse
from services.storage import StorageService
from services.file_storage import save_upload, get_file_path
from fastapi.responses import FileResponse

router = APIRouter(tags=["evidence"])



@router.post("/api/projects/{project_id}/evidence", response_model=EvidenceRecordResponse)
async def upload_evidence(
    project_id: int,
    file: UploadFile = File(...),
    type: str = Form(...),
    title: Optional[str] = Form(None),
    trade: Optional[str] = Form(None),
    spec_section: Optional[str] = Form(None),
    meta: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Upload evidence record (photo, video, document, spec, etc.) for a project.
    
    Form Fields:
    - file: multipart file (required)
    - type: 'spec' or 'inspection_doc' (required)
    - title: display name for evidence (optional, defaults to filename)
    - trade: e.g., 'HVAC', 'Electrical' (optional)
    - spec_section: e.g., '15830 - HVAC Controls' (optional)
    - meta: JSON string with custom metadata (optional)
    
    Returns: EvidenceRecordResponse with file_url for download
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    # Validate type is one of the allowed values
    type_lower = type.strip().lower() if type else None
    if type_lower not in ("spec", "inspection_doc"):
        raise HTTPException(
            status_code=400,
            detail="type must be 'spec' or 'inspection_doc'",
        )

    # Verify project exists
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    # Persist file via helper (validates size/type and writes to disk)
    storage_key, content_type, original_name = save_upload(
        file, project_id, category="evidence"
    )

    # Parse meta JSON if provided
    parsed_meta: Optional[dict] = None
    if meta:
        try:
            parsed_meta = json.loads(meta)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid meta JSON")

    # Use provided title or fall back to filename
    evidence_title = title if title else original_name

    # Create evidence record via service layer
    service = StorageService(db)
    evidence = service.create_evidence_record(
        project_id=project_id,
        type=type_lower,
        trade=trade.strip() if trade else None,
        spec_section=spec_section.strip() if spec_section else None,
        title=evidence_title,
        storage_key=storage_key,
        content_type=content_type,
        text_content=None,
        meta=parsed_meta,
    )

    # Set file_url to point to the /file route
    evidence.file_url = f"/api/projects/{project_id}/evidence/{evidence.id}/file"
    db.commit()
    db.refresh(evidence)

    return evidence


@router.get("/api/projects/{project_id}/evidence", response_model=EvidenceListResponse)
def list_evidence(
    project_id: int,
    type: Optional[str] = Query(default=None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List evidence records for a project with pagination (limit, offset).
    
    - Metadata comes from database, no filesystem reads
    - Optionally filter by type (e.g., ?type=spec)
    - Returns evidence sorted by creation date (newest first)
    
    Query Parameters:
    - type: optional filter by evidence type ('spec' or 'inspection_doc')
    - limit, offset: pagination
    """
    # Verify project exists
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    service = StorageService(db)
    type_param = type.strip().lower() if type else None
    evidence_list, total = service.list_evidence_records(
        project_id, type=type_param, limit=limit, offset=offset
    )

    # Set file_url on each record
    for evidence in evidence_list:
        evidence.file_url = f"/api/projects/{project_id}/evidence/{evidence.id}/file"

    db.commit()

    items = [EvidenceRecordResponse.model_validate(e) for e in evidence_list]
    return EvidenceListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/api/projects/{project_id}/evidence/{evidence_id}", response_model=EvidenceRecordResponse)
def get_evidence(
    project_id: int,
    evidence_id: int,
    db: Session = Depends(get_db),
):
    """Get metadata for a specific evidence record.
    
    - Metadata comes from database, no filesystem reads
    - Returns evidence details including file_url
    """
    service = StorageService(db)
    evidence = service.get_evidence_record(project_id, evidence_id)
    
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")
    
    # Set file_url to point to /file endpoint
    evidence.file_url = f"/api/projects/{project_id}/evidence/{evidence.id}/file"
    db.commit()

    return evidence


@router.get("/api/projects/{project_id}/evidence/{evidence_id}/file", response_class=FileResponse)
def download_evidence_file(
    project_id: int,
    evidence_id: int,
    db: Session = Depends(get_db),
):
    """Secure file download for an evidence record.

    Flow:
    - Load evidence via StorageService.get_evidence_record(project_id, evidence_id)
    - If not found -> 404
    - Resolve on-disk path via get_file_path(evidence.storage_key)
    - Return FileResponse(path, media_type=..., filename=evidence.title)
    """
    service = StorageService(db)
    evidence = service.get_evidence_record(project_id, evidence_id)
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")

    storage_key = cast(Optional[str], evidence.storage_key)
    if not storage_key:
        raise HTTPException(status_code=404, detail="No file available")

    path = get_file_path(storage_key)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")

    content_type = cast(Optional[str], evidence.content_type) or "application/octet-stream"
    filename = cast(Optional[str], evidence.title) or "download"
    return FileResponse(
        path,
        media_type=content_type,
        filename=filename,
    )