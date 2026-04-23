from typing import List, Literal, Optional, cast

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from api.dependencies import get_db, get_idempotency_key
from api.upload_intent_form import coalesce_upload_intent_form
from models.models import Drawing
from models.schemas import (
    DrawingOverlayResponse,
    DrawingResponse,
    DrawingSummary,
    EvidenceContextMatch,
    EvidenceContextResponse,
    EvidenceMatchReason,
    EvidenceRecordResponse,
    EvidenceDrawingLinkResponse,
    ProjectDrawingsListResponse,
)
from services.drawing_render_jobs import enqueue_drawing_render_job
from services.drawings import DrawingService
from services.storage import StorageService
from services.evidence_retrieval import EvidenceRetrievalService
from services.file_storage import (
    get_file_path,
    read_and_validate_upload,
    save_upload_from_bytes,
    sha256_bytes,
)
from services.idempotency import begin_idempotent_operation, finish_idempotent_operation
from fastapi.responses import FileResponse

router = APIRouter(tags=["drawings"])



@router.post("/api/projects/{project_id}/drawings", response_model=DrawingResponse)
async def upload_drawing(
    project_id: int,
    file: UploadFile = File(...),
    upload_intent: str | None = Form(default=None),
    uploadIntent: str | None = Form(default=None),
    idempotency_key: str = Depends(get_idempotency_key),
    db: Session = Depends(get_db),
) -> DrawingResponse:
    """
    POST /api/projects/{project_id}/drawings
    Upload a drawing file and persist metadata to database.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    normalized_upload_intent = coalesce_upload_intent_form(
        upload_intent, uploadIntent
    )
    if normalized_upload_intent not in (None, "master", "sub"):
        raise HTTPException(
            status_code=400,
            detail="upload_intent must be one of: master, sub",
        )
    upload_intent_for_create: Literal["master", "sub"] | None
    if normalized_upload_intent == "master":
        upload_intent_for_create = "master"
    elif normalized_upload_intent == "sub":
        upload_intent_for_create = "sub"
    else:
        upload_intent_for_create = None

    file_bytes, content_type, original_name = read_and_validate_upload(file, category="drawings")
    checksum = sha256_bytes(file_bytes)
    source = "upload"

    # Must include normalized_upload_intent: same bytes + same Idempotency-Key would otherwise
    # hash identically for master vs sub and return the wrong cached DrawingResponse.
    request_fingerprint = {
        "project_id": project_id,
        "checksum": checksum,
        "source": source,
        "upload_intent": normalized_upload_intent,
    }
    scope = f"drawing_upload:{project_id}:{checksum}:{source}"

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
            return DrawingResponse(**cached_resp)
        if row_status == "in_progress":
            raise HTTPException(status_code=409, detail="Request already in progress")
        if row_status == "failed" and cached_resp:
            return DrawingResponse(**cached_resp)

    storage_key = save_upload_from_bytes(
        file_bytes, project_id, category="drawings", content_type=content_type, original_name=original_name
    )

    service = StorageService(db)
    drawing = service.create_drawing(
        project_id=project_id,
        source=source,
        name=original_name,
        storage_key=storage_key,
        content_type=content_type,
        page_count=None,
        upload_intent=upload_intent_for_create,
    )

    response = DrawingResponse.model_validate(drawing)
    response_data = response.model_dump(mode="json")
    response_data["file_url"] = f"/api/projects/{project_id}/drawings/{cast(int, drawing.id)}/file"
    # Explicit for idempotency cache + clarity (also present on model_dump from ORM).
    response_data["upload_intent"] = drawing.upload_intent

    # Enqueue async render job for PDF/image rendition generation
    enqueue_drawing_render_job(db, project_id, cast(int, drawing.id))

    finish_idempotent_operation(
        db,
        row_id=cast(int, idem_row.id),
        response_payload=response_data,
        resource_reference={"drawing_id": cast(int, drawing.id)},
    )
    return DrawingResponse(**response_data)


@router.get(
    "/api/projects/{project_id}/drawings",
    response_model=ProjectDrawingsListResponse,
)
def list_drawings(
    project_id: int,
    db: Session = Depends(get_db),
):
    """
    GET /api/projects/{project_id}/drawings
    List all drawings for a project. Returns workspace-ready candidates with camelCase fields.
    """
    service = DrawingService(db)
    try:
        return service.list_project_drawings(project_id=project_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load project drawings: {str(e)}",
        )


@router.get("/api/projects/{project_id}/drawings/{drawing_id}", response_model=DrawingResponse)
def get_drawing(
    project_id: int,
    drawing_id: int,
    db: Session = Depends(get_db),
) -> DrawingResponse:
    """
    GET /api/projects/{project_id}/drawings/{drawing_id}
    Get a specific drawing by ID.
    """
    service = StorageService(db)
    drawing = service.get_drawing(project_id, drawing_id)
    if not drawing:
        raise HTTPException(status_code=404, detail="Drawing not found")
    return DrawingResponse.model_validate(drawing)


@router.get(
    "/api/projects/{project_id}/drawings/{drawing_id}/evidence-context",
    response_model=EvidenceContextResponse,
)
def get_drawing_evidence_context(
    project_id: int,
    drawing_id: int,
    limit: int = Query(15, ge=1, le=50),
    db: Session = Depends(get_db),
) -> EvidenceContextResponse:
    """
    GET /api/projects/{project_id}/drawings/{drawing_id}/evidence-context

    Return ranked evidence matches for a drawing using direct links, discipline overlap, and revision timing.
    """
    retrieval = EvidenceRetrievalService(db)
    result = retrieval.get_context_for_drawing(project_id, drawing_id, limit=limit)
    if result is None:
        raise HTTPException(status_code=404, detail="Drawing not found")

    drawing_response = DrawingResponse.model_validate(result.drawing).model_copy(
        update={
            "file_url": f"/api/projects/{project_id}/drawings/{drawing_id}/file",
        }
    )
    matches: List[EvidenceContextMatch] = []
    for match in result.matches:
        evidence_schema = EvidenceRecordResponse.model_validate(match.evidence)
        link_schemas = [
            EvidenceDrawingLinkResponse.model_validate(link) for link in match.direct_links
        ]
        reason_schemas = [
            EvidenceMatchReason(
                reason=reason["reason"],
                weight=reason["weight"],
                details=reason.get("details"),
            )
            for reason in match.reasons
        ]
        matches.append(
            EvidenceContextMatch(
                evidence=evidence_schema,
                score=match.score,
                reasons=reason_schemas,
                direct_links=link_schemas,
                discipline_overlap=match.discipline_overlap,
                revision_proximity_days=match.revision_proximity_days,
            )
        )

    return EvidenceContextResponse(drawing=drawing_response, matches=matches)


@router.get("/api/projects/{project_id}/drawings/{drawing_id}/file", response_class=FileResponse)
def download_drawing_file(
    project_id: int,
    drawing_id: int,
    db: Session = Depends(get_db),
) -> FileResponse:
    """Download the file bytes for a drawing, verifying project scope."""
    service = StorageService(db)
    drawing = service.get_drawing(project_id, drawing_id)
    if not drawing:
        raise HTTPException(status_code=404, detail="Drawing not found")

    storage_key = cast(Optional[str], drawing.storage_key)
    if not storage_key:
        raise HTTPException(status_code=404, detail="File not available")

    path = get_file_path(storage_key)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")

    content_type = cast(Optional[str], drawing.content_type) or "application/octet-stream"
    name = cast(str, drawing.name)
    return FileResponse(
        path,
        media_type=content_type,
        filename=name,
    )


@router.get(
    "/api/projects/{project_id}/drawings/{drawing_id}/overlays",
    response_model=List[DrawingOverlayResponse],
)
def list_drawing_overlays(
    project_id: int,
    drawing_id: int,
    inspection_run_id: Optional[int] = Query(None, description="Filter by inspection run"),
    diff_id: Optional[int] = Query(None, description="Filter by diff"),
    db: Session = Depends(get_db),
) -> List[DrawingOverlayResponse]:
    """
    GET /api/projects/{project_id}/drawings/{drawing_id}/overlays

    List overlays for a drawing (master drawing). Sorted by created_at desc.
    Optional filters: inspection_run_id, diff_id.
    """
    service = StorageService(db)
    drawing = service.get_drawing(project_id, drawing_id)
    if not drawing:
        raise HTTPException(status_code=404, detail="Drawing not found")

    overlays = service.list_drawing_overlays(
        master_drawing_id=drawing_id,
        inspection_run_id=inspection_run_id,
        diff_id=diff_id,
    )
    return [DrawingOverlayResponse.model_validate(o) for o in overlays]
