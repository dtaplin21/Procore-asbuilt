"""Finding serialization helpers (includes workspace deep links for diff-backed findings)."""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from models.models import Finding
from models.schemas import FindingResponse, WorkspaceLinkMetadata
from services.storage import StorageService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def workspace_link_metadata_for_finding(
    finding: Finding,
    storage: StorageService,
) -> WorkspaceLinkMetadata | None:
    """Resolve workspace deep link for a finding when it is tied to a drawing diff + alignment."""
    drawing_diff_id = getattr(finding, "drawing_diff_id", None)
    if not drawing_diff_id:
        return None

    drawing_diff = storage.get_drawing_diff(drawing_diff_id)
    if not drawing_diff:
        return None

    alignment = storage.get_alignment(drawing_diff.alignment_id)
    if not alignment:
        return None

    return WorkspaceLinkMetadata(
        project_id=alignment.project_id,
        master_drawing_id=alignment.master_drawing_id,
        alignment_id=alignment.id,
        diff_id=drawing_diff.id,
    )


class FindingService:
    def __init__(self, db: Session):
        self.db = db
        self.storage = StorageService(db)

    def _build_workspace_link_for_finding(self, finding: Finding) -> WorkspaceLinkMetadata | None:
        return workspace_link_metadata_for_finding(finding, self.storage)

    def serialize_finding(self, finding: Finding) -> FindingResponse:
        return FindingResponse(
            id=finding.id,
            project_id=finding.project_id,
            title=finding.title,
            description=getattr(finding, "description", None),
            severity=getattr(finding, "severity", None),
            type=getattr(finding, "type", None),
            created_at=getattr(finding, "created_at", None),
            workspace_link=self._build_workspace_link_for_finding(finding),
        )

    def list_project_findings(self, project_id: int, limit: Optional[int] = None) -> List[Finding]:
        return self.storage.list_findings_by_project(project_id, limit=limit)
