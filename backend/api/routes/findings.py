from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.dependencies import get_db
from models.schemas import FindingListResponse
from services.findings import FindingService
from services.storage import StorageService

router = APIRouter(prefix="/api/projects", tags=["findings"])


@router.get("/{project_id}/findings", response_model=FindingListResponse)
def list_project_findings(
    project_id: int,
    limit: int | None = Query(5),
    db: Session = Depends(get_db),
):
    """List findings for a project with serialized rows (includes workspaceLink when diff-backed)."""
    storage = StorageService(db)
    if storage.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")

    service = FindingService(db)
    rows = service.list_project_findings(project_id, limit=limit)
    return FindingListResponse(findings=[service.serialize_finding(f) for f in rows])
