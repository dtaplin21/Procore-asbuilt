from typing import List, Optional, Any, cast
import json
import logging

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query, Depends
from sqlalchemy.orm import Session

from api.dependencies import get_db, get_idempotency_key
from ai.pipelines.inspection_mapping import DocumentEvidenceInput, map_document_to_overlays
from models.models import EvidenceRecord, InspectionRun, Project
from models.schemas import (
    EvidenceRecordResponse,
    EvidenceListResponse,
    InspectionRunEvidenceUploadResponse,
)
from services.evidence_document_extraction import ingest_evidence_document_extraction
from services.evidence_file_storage import (
    UnsupportedEvidenceFileType,
    evidence_storage_dir,
    save_upload,
    storage_key_from_path,
)
from services.file_storage import get_file_path, read_and_validate_upload, save_upload_from_bytes, sha256_bytes
from services.idempotency import begin_idempotent_operation, finish_idempotent_operation
from services.overlay_storage import create_drawing_overlays, flag_unresolved_evidence
from services.region_index_loader import build_region_index
from services.storage import StorageService
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["evidence"])


def _try_visual_registration(file_path: str, master_drawing_id: str):
    """Placeholder for Case A (alignment) registration — returns None until wired."""
    return None


def _maybe_trigger_run_completion(db: Session, run: InspectionRun) -> None:
    """Extension point (PR3 §3.3): update run status when evidence pipeline completes."""
    # Intentionally left as a no-op until run-completion rules are defined centrally.
    _ = (db, run)


@router.post(
    "/api/projects/{project_id}/inspections/runs/{inspection_run_id}/evidence",
    response_model=InspectionRunEvidenceUploadResponse,
)
async def upload_inspection_run_evidence(
    project_id: int,
    inspection_run_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> InspectionRunEvidenceUploadResponse:
    """Upload evidence against an inspection run and map it onto the master drawing."""
    storage = StorageService(db)
    if storage.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")

    run = storage.get_inspection_run(project_id, inspection_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Inspection run not found")

    master_drawing_id = cast(int, run.master_drawing_id)

    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    file_bytes, content_type, original_name = read_and_validate_upload(file, category="evidence")
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        saved_path = save_upload(
            original_name,
            file_bytes,
            storage_root=evidence_storage_dir(project_id),
        )
    except UnsupportedEvidenceFileType as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    storage_key = storage_key_from_path(saved_path)

    evidence = storage.create_evidence_record(
        project_id=project_id,
        type="inspection_doc",
        trade=None,
        spec_section=None,
        title=original_name,
        storage_key=storage_key,
        content_type=content_type,
        text_content=None,
        meta={"inspectionRunId": inspection_run_id},
    )
    evidence_id = cast(int, evidence.id)

    ingest_evidence_document_extraction(
        db,
        evidence_id=evidence_id,
        file_path=str(saved_path),
    )

    if getattr(run, "evidence_id", None) is None:
        setattr(run, "evidence_id", evidence_id)
        db.commit()
        db.refresh(run)

    region_load = build_region_index(db, master_drawing_id)
    registration = _try_visual_registration(str(saved_path), str(master_drawing_id))

    evidence_input = DocumentEvidenceInput(
        evidence_id=str(evidence_id),
        inspection_run_id=str(inspection_run_id),
        master_drawing_id=str(master_drawing_id),
        file_path=str(saved_path),
        region_index=region_load.regions,
        registration_transform=registration,
    )

    try:
        overlays, unresolved = map_document_to_overlays(evidence_input)
    except Exception:
        logger.exception(
            "map_document_to_overlays failed for evidence_id=%s run_id=%s drawing_id=%s",
            evidence_id,
            inspection_run_id,
            master_drawing_id,
        )
        raise HTTPException(
            status_code=422,
            detail=(
                "Could not process the uploaded evidence file. It may be "
                "corrupted, password-protected, or an unsupported format."
            ),
        ) from None

    saved_overlays = create_drawing_overlays(db, overlays) if overlays else []
    if unresolved:
        flag_unresolved_evidence(db, unresolved)

    storage.update_inspection_run_status(cast(int, run.id), "complete")

    if region_load.untagged_region_count > 0:
        logger.info(
            "Drawing %s has %d untagged regions — tag with inspection_type_tags/location_tags.",
            master_drawing_id,
            region_load.untagged_region_count,
        )

    _maybe_trigger_run_completion(db, run)

    return InspectionRunEvidenceUploadResponse(
        evidence_id=evidence_id,
        overlays_created=len(saved_overlays),
        unresolved_count=len(unresolved),
        untagged_region_count=region_load.untagged_region_count,
        overlay_ids=[cast(int, overlay.id) for overlay in saved_overlays],
    )


@router.post("/api/projects/{project_id}/evidence", response_model=EvidenceRecordResponse)
async def upload_evidence(
    project_id: int,
    file: UploadFile = File(...),
    type: str = Form(...),
    title: Optional[str] = Form(None),
    trade: Optional[str] = Form(None),
    spec_section: Optional[str] = Form(None),
    meta: Optional[str] = Form(None),
    idempotency_key: str = Depends(get_idempotency_key),
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

    type_lower = type.strip().lower() if type else None
    if type_lower not in ("spec", "inspection_doc"):
        raise HTTPException(
            status_code=400,
            detail="type must be 'spec' or 'inspection_doc'",
        )

    file_bytes, content_type, original_name = read_and_validate_upload(file, category="evidence")
    checksum = sha256_bytes(file_bytes)

    request_fingerprint = {
        "project_id": project_id,
        "checksum": checksum,
        "type": type_lower,
    }
    scope = f"evidence_upload:{project_id}:{checksum}:{type_lower}"

    try:
        idem_row, should_execute = begin_idempotent_operation(
            db,
            scope=scope,
            idempotency_key=idempotency_key,
            request_payload=request_fingerprint,
            ttl_minutes=60,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not should_execute:
        row_status = getattr(idem_row, "status", None)
        cached_resp = dict(getattr(idem_row, "response_payload", None) or {})
        if row_status == "completed" and cached_resp:
            return EvidenceRecordResponse(**cached_resp)
        if row_status == "in_progress":
            raise HTTPException(status_code=409, detail="Request already in progress")
        if row_status == "failed" and cached_resp:
            return EvidenceRecordResponse(**cached_resp)

    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    storage_key = save_upload_from_bytes(
        file_bytes, project_id, category="evidence", content_type=content_type, original_name=original_name
    )

    parsed_meta: Optional[dict] = None
    if meta:
        try:
            parsed_meta = json.loads(meta)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid meta JSON")

    evidence_title = title if title else original_name

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

    if type_lower == "inspection_doc":
        ingest_evidence_document_extraction(
            db,
            evidence_id=cast(int, evidence.id),
            file_path=get_file_path(storage_key),
        )

    evidence.file_url = f"/api/projects/{project_id}/evidence/{cast(int, evidence.id)}/file"
    db.commit()
    db.refresh(evidence)

    response_data = EvidenceRecordResponse.model_validate(evidence).model_dump(mode="json")
    response_data["file_url"] = f"/api/projects/{project_id}/evidence/{cast(int, evidence.id)}/file"
    finish_idempotent_operation(
        db,
        row_id=cast(int, idem_row.id),
        response_payload=response_data,
        resource_reference={"evidence_id": cast(int, evidence.id)},
    )
    return EvidenceRecordResponse(**response_data)


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