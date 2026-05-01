from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.dependencies import get_db, get_idempotency_key
from services.procore_client import ProcoreAPIClient
from services.storage import StorageService
from services.rfi_ingestion import ingest_rfis_for_project
from models.schemas import RfiIngestionResponse
from typing import Optional, cast
from errors import ProcoreNotConnected
from services.procore_connection_store import get_active_connection

from services.idempotency import (
    begin_idempotent_operation,
    finish_idempotent_operation,
    fail_idempotent_operation,
)

router = APIRouter(prefix="/api/procore", tags=["procore"])


@router.post("/sync")
async def sync_procore(
    user_id: str = Query(...),
    project_id: Optional[str] = Query(None),
    idempotency_key: str = Depends(get_idempotency_key),
    db: Session = Depends(get_db),
):
    """Sync data from Procore. Repeated button clicks return in-progress or completed response."""
    sync_type = "projects" if not project_id else "project"
    scope = f"procore_sync:{user_id}:{project_id or 'all'}:{sync_type}"
    request_payload = {"user_id": user_id, "project_id": project_id}

    try:
        idem_row, should_execute = begin_idempotent_operation(
            db,
            scope=scope,
            idempotency_key=idempotency_key,
            request_payload=request_payload,
            ttl_minutes=60,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not should_execute:
        row_status = getattr(idem_row, "status", None)
        cached_resp = dict(getattr(idem_row, "response_payload", None) or {})
        if row_status == "completed":
            return cached_resp
        if row_status == "in_progress":
            raise HTTPException(status_code=409, detail="Sync already in progress")
        if row_status == "failed":
            return cached_resp

    conn = get_active_connection(db, user_id)
    if not conn:
        fail_idempotent_operation(
            db, row_id=cast(int, idem_row.id), response_payload={"error": "Procore not connected", "user_id": user_id}
        )
        raise ProcoreNotConnected(details={"user_id": user_id})

    try:
        async with ProcoreAPIClient(db, user_id) as client:
            if not project_id:
                projects = await client.get_projects()
                # TODO: Store projects in local database
                response = {"synced": len(projects), "message": f"Synced {len(projects)} projects"}
            else:
                # Sync specific project data
                # TODO: Sync submittals, RFIs, inspections, etc.
                response = {"synced": True, "project_id": project_id}
        finish_idempotent_operation(db, row_id=cast(int, idem_row.id), response_payload=response)
        return response
    except Exception as e:
        fail_idempotent_operation(
            db,
            row_id=cast(int, idem_row.id),
            response_payload={"error": str(e), "synced": False},
        )
        raise


@router.post("/projects/{project_id}/rfis/ingest", response_model=RfiIngestionResponse)
async def ingest_project_rfis(
    project_id: int,
    user_id: str = Query(...),
    db: Session = Depends(get_db),
):
    storage = StorageService(db)

    project = storage.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    records = await ingest_rfis_for_project(
        db,
        user_id=user_id,
        project=project,
    )

    # Return hydrated records if you prefer, or keep the summary list from the service
    full_records, _ = storage.list_evidence_records(project_id=project_id)

    return {
        "imported_count": len(records),
        "records": full_records,
    }

