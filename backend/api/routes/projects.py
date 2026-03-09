from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional, cast

from api.dependencies import get_db, get_idempotency_key
from services.idempotency import (
    begin_idempotent_operation,
    finish_idempotent_operation,
    fail_idempotent_operation,
)
from services.storage import StorageService
from models.schemas import (
    ProjectResponse,
    ProjectListResponse,
    DashboardSummaryResponse,
    DrawingResponse,
    InspectionItemWritebackRequest,
    InspectionItemWritebackResponse,
    ObservationWritebackRequest,
    ObservationWritebackResponse,
    PunchItemWritebackRequest,
    PunchItemWritebackResponse,
)
from models.models import Drawing, InspectionRun, Project
from services.file_storage import save_upload, get_file_path
from services.procore_writeback_contract import build_writeback_contract
from services.procore_writeback import (
    build_observation_writeback_contract,
    translate_contract_to_procore_observation_payload,
    build_punch_item_writeback_contract,
    translate_contract_to_procore_punch_item_payload,
    build_inspection_item_contract,
    translate_contract_to_procore_inspection_item_payload,
)
from services.procore_client import ProcoreAPIClient
from services.procore_connection_store import get_active_connection
from errors import ProcoreNotConnected


router = APIRouter(prefix="/api/projects", tags=["projects"])

@router.get("", response_model=ProjectListResponse)
async def get_projects(
    company_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List projects with pagination (limit, offset)."""
    storage = StorageService(db)
    items, total = storage.get_projects(company_id=company_id, limit=limit, offset=offset)
    return ProjectListResponse(
        items=[ProjectResponse.model_validate(p) for p in items],
        total=total,
        limit=limit,
        offset=offset,
    )

@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: int, db: Session = Depends(get_db)):
    storage = StorageService(db)
    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/{project_id}/dashboard/summary", response_model=DashboardSummaryResponse)
async def get_project_dashboard_summary(
    project_id: int,
    user_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Return a high‑level dashboard summary for a given project.

    * ``project_id`` is required and used to look up the project in storage.
    * ``user_id`` is optional and, when provided, is passed through to
      :class:`~services.storage.StorageService.get_project_dashboard_summary`
      so that the service can return an active Procore company context if the
      user has an active connection.

    The storage method will return an empty dict if the project does not
    exist; we translate that into an HTTP 404 so clients can react
    appropriately.
    """

    storage = StorageService(db)
    summary = storage.get_project_dashboard_summary(
        project_id=project_id, procore_user_id=user_id
    )

    if not summary:
        # storage returns an empty dict when no project is found
        raise HTTPException(status_code=404, detail="Project not found")

    return summary


@router.post(
    "/{project_id}/procore/inspection_items/writeback",
    response_model=InspectionItemWritebackResponse,
)
async def procore_inspection_items_writeback(
    project_id: int,
    body: InspectionItemWritebackRequest,
    user_id: str = Query(..., description="Procore user ID for auth"),
    db: Session = Depends(get_db),
) -> InspectionItemWritebackResponse:
    """
    Write inspection items to Procore (second phase; inspection header must already exist).

    Requires inspection_run to have procore_inspection_id set (from prior writeback commit).
    - **dry_run**: Returns item contract + translated payloads (no API call).
    - **commit**: Calls create_inspection_item for each item.
    """
    if body.mode not in ("dry_run", "commit"):
        raise HTTPException(
            status_code=400,
            detail="mode must be 'dry_run' or 'commit'",
        )

    contract = build_writeback_contract(db, project_id, body.inspection_run_id)
    procore_project_id = contract.get("project", {}).get("procore_project_id", "") or ""
    if not procore_project_id:
        raise HTTPException(
            status_code=400,
            detail="Project has no procore_project_id; sync project from Procore first",
        )

    items_contract = build_inspection_item_contract(db, project_id, body.inspection_run_id)
    item_payloads = [
        translate_contract_to_procore_inspection_item_payload(item)
        for item in items_contract
    ]

    if body.mode == "dry_run":
        return InspectionItemWritebackResponse(
            mode="dry_run",
            inspection_items_contract=items_contract,
            inspection_item_payloads=item_payloads,
        )

    run = (
        db.query(InspectionRun)
        .filter(
            InspectionRun.project_id == project_id,
            InspectionRun.id == body.inspection_run_id,
        )
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Inspection run not found")
    procore_inspection_id = getattr(run, "procore_inspection_id", None)
    if not procore_inspection_id:
        raise HTTPException(
            status_code=400,
            detail="Inspection run has no procore_inspection_id; run header writeback (commit) first",
        )

    if get_active_connection(db, user_id) is None:
        raise ProcoreNotConnected(details={"user_id": user_id})

    created_items: list = []
    async with ProcoreAPIClient(db, user_id) as client:
        for payload in item_payloads:
            created = await client.create_inspection_item(
                project_id=str(procore_project_id),
                inspection_id=str(procore_inspection_id),
                payload=payload,
            )
            created_items.append(created)

    return InspectionItemWritebackResponse(
        mode="commit",
        procore_inspection_items=created_items,
    )


@router.post(
    "/{project_id}/procore/observations/writeback",
    response_model=ObservationWritebackResponse,
)
async def procore_observation_writeback(
    project_id: int,
    body: ObservationWritebackRequest,
    user_id: str = Query(..., description="Procore user ID for auth"),
    idempotency_key: str = Depends(get_idempotency_key),
    db: Session = Depends(get_db),
) -> ObservationWritebackResponse:
    """
    Write finding to Procore as an observation.

    - **dry_run**: Returns contract + payload (no API call).
    - **commit**: Calls Procore create_observation and returns the created observation.
    """
    request_fingerprint = {
        "project_id": project_id,
        "finding_id": body.finding_id,
        "mode": body.mode,
        "writeback_type": "observation",
    }
    scope = f"procore:observation:{project_id}:{body.finding_id}:{body.mode}"

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
        cached_resp.setdefault("mode", body.mode)
        if row_status == "completed":
            return ObservationWritebackResponse(**cached_resp)
        if row_status == "in_progress":
            raise HTTPException(status_code=409, detail="Request already in progress")
        if row_status == "failed":
            return ObservationWritebackResponse(**cached_resp)

    if body.mode not in ("dry_run", "commit"):
        raise HTTPException(
            status_code=400,
            detail="mode must be 'dry_run' or 'commit'",
        )

    try:
        contract = build_observation_writeback_contract(db, project_id, body.finding_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    translated_payload = translate_contract_to_procore_observation_payload(contract)

    if body.mode == "dry_run":
        dry_run_response = ObservationWritebackResponse(
            mode="dry_run",
            contract=contract,
            payload=translated_payload,
        )
        finish_idempotent_operation(
            db,
            row_id=cast(int, idem_row.id),
            response_payload=dry_run_response.model_dump(exclude_none=False),
        )
        return dry_run_response

    if get_active_connection(db, user_id) is None:
        raise ProcoreNotConnected(details={"user_id": user_id})

    procore_project_id = contract.get("procore_project_id", "") or ""
    if not procore_project_id:
        raise HTTPException(
            status_code=400,
            detail="Project has no procore_project_id; sync project from Procore first",
        )

    storage = StorageService(db)
    wb = storage.create_procore_writeback(
        project_id=project_id,
        finding_id=body.finding_id,
        writeback_type="observation",
        mode=body.mode,
        idempotency_key=idempotency_key,
        payload=translated_payload,
    )

    try:
        async with ProcoreAPIClient(db, user_id) as client:
            procore_response = await client.create_observation(
                project_id=str(procore_project_id),
                payload=translated_payload,
            )

        response_payload = {
            "mode": body.mode,
            "payload": translated_payload,
            "procore_observation": procore_response,
        }
        storage.update_procore_writeback(
            cast(int, wb.id),
            status="completed",
            procore_response=procore_response,
            resource_reference={"procore_observation_id": procore_response.get("id")},
        )
        finish_idempotent_operation(
            db,
            row_id=cast(int, idem_row.id),
            response_payload=response_payload,
            resource_reference={
                "writeback_id": cast(int, wb.id),
                "procore_observation_id": procore_response.get("id"),
            },
        )
        return ObservationWritebackResponse(**response_payload)
    except Exception as exc:
        error_payload = {"mode": "commit", "procore_observation": {"error": str(exc)}}
        storage.update_procore_writeback(
            cast(int, wb.id),
            status="failed",
            procore_response={"error": str(exc)},
        )
        fail_idempotent_operation(
            db,
            row_id=cast(int, idem_row.id),
            response_payload=error_payload,
        )
        raise


@router.post(
    "/{project_id}/procore/punch_items/writeback",
    response_model=PunchItemWritebackResponse,
)
async def procore_punch_item_writeback(
    project_id: int,
    body: PunchItemWritebackRequest,
    user_id: str = Query(..., description="Procore user ID for auth"),
    db: Session = Depends(get_db),
) -> PunchItemWritebackResponse:
    """
    Write finding to Procore as a punch item.

    - **dry_run**: Returns contract + payload (no API call).
    - **commit**: Calls Procore create_punch_item and returns the created punch item.
    """
    if body.mode not in ("dry_run", "commit"):
        raise HTTPException(
            status_code=400,
            detail="mode must be 'dry_run' or 'commit'",
        )

    try:
        contract = build_punch_item_writeback_contract(db, project_id, body.finding_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    payload = translate_contract_to_procore_punch_item_payload(contract)

    if body.mode == "dry_run":
        return PunchItemWritebackResponse(
            mode="dry_run",
            contract=contract,
            payload=payload,
        )

    if get_active_connection(db, user_id) is None:
        raise ProcoreNotConnected(details={"user_id": user_id})

    procore_project_id = contract.get("procore_project_id", "") or ""
    if not procore_project_id:
        raise HTTPException(
            status_code=400,
            detail="Project has no procore_project_id; sync project from Procore first",
        )

    async with ProcoreAPIClient(db, user_id) as client:
        created = await client.create_punch_item(
            project_id=str(procore_project_id),
            payload=payload,
        )

    return PunchItemWritebackResponse(
        mode="commit",
        procore_punch_item=created,
    )


@router.post("/{project_id}/drawings", response_model=DrawingResponse)
async def upload_project_drawing(
    project_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload a drawing file for a project.
    
    - Validates file type and size
    - Saves file to disk
    - Creates database record with file_url pointing to /file endpoint
    """
    # Verify project exists
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    # Persist file via helper (validates size/type and writes to disk)
    storage_key, content_type, original_name = save_upload(file, project_id, category="drawings")

    # Create drawing record via service layer
    service = StorageService(db)
    drawing = service.create_drawing(
        project_id=project_id,
        source="upload",
        name=original_name,
        storage_key=storage_key,
        content_type=content_type,
        page_count=None,
    )
    
    # Set file_url to point to the /file route (will be implemented in next step)
    setattr(drawing, "file_url", f"/api/projects/{project_id}/drawings/{cast(int, drawing.id)}/file")
    db.commit()
    db.refresh(drawing)

    return drawing


@router.get("/{project_id}/drawings", response_model=List[DrawingResponse])
def list_project_drawings(
    project_id: int,
    db: Session = Depends(get_db),
):
    """List all drawings for a project.
    
    - Metadata comes from database, no filesystem reads
    - Returns drawings sorted by creation date (newest first)
    """
    # Verify project exists
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    service = StorageService(db)
    drawings = service.list_drawings(project_id)
    
    # Set file_url on each drawing to point to /file endpoint
    for drawing in drawings:
        setattr(drawing, "file_url", f"/api/projects/{project_id}/drawings/{cast(int, drawing.id)}/file")
    
    db.commit()  # Persist file_url changes
    
    return drawings


@router.get("/{project_id}/drawings/{drawing_id}", response_model=DrawingResponse)
def get_project_drawing(
    project_id: int,
    drawing_id: int,
    db: Session = Depends(get_db),
):
    """Get metadata for a specific drawing.
    
    - Metadata comes from database, no filesystem reads
    - Returns drawing details including file_url
    """
    service = StorageService(db)
    drawing = service.get_drawing(project_id, drawing_id)
    
    if not drawing:
        raise HTTPException(status_code=404, detail="Drawing not found")
    
    # Set file_url to point to /file endpoint
    setattr(drawing, "file_url", f"/api/projects/{project_id}/drawings/{cast(int, drawing.id)}/file")
    db.commit()

    return drawing


@router.get(
    "/{project_id}/drawings/{drawing_id}/download",
    response_class=FileResponse,
)
def download_project_drawing(
    project_id: int,
    drawing_id: int,
    db: Session = Depends(get_db),
):
    # ensure the requested drawing belongs to the project
    drawing = (
        db.query(Drawing)
        .filter(Drawing.id == drawing_id, Drawing.project_id == project_id)
        .first()
    )
    if not drawing:
        raise HTTPException(status_code=404, detail="Drawing not found")

    storage_key = cast(Optional[str], drawing.storage_key)
    if not storage_key:
        raise HTTPException(status_code=404, detail="No file available")

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


@router.get("/{project_id}/drawings/{drawing_id}/file", response_class=FileResponse)
def download_project_drawing_file(
    project_id: int,
    drawing_id: int,
    db: Session = Depends(get_db),
):
    """Secure file download for a drawing. Returns file bytes with correct content-type.

    Flow:
    - Load drawing via StorageService.get_drawing(project_id, drawing_id)
    - If not found -> 404
    - Resolve on-disk path via get_file_path(drawing.storage_key)
    - Return FileResponse(path, media_type=..., filename=drawing.name)
    """
    service = StorageService(db)
    drawing = service.get_drawing(project_id, drawing_id)
    if not drawing:
        raise HTTPException(status_code=404, detail="Drawing not found")

    storage_key = cast(Optional[str], drawing.storage_key)
    if not storage_key:
        raise HTTPException(status_code=404, detail="No file available")

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

