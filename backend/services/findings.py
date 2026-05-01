"""Finding serialization helpers (includes workspace deep links for diff-backed findings)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional, cast

from models.models import Finding
from models.schemas import FindingResponse, WorkspaceLinkMetadata
from services.storage import StorageService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def workspace_link_metadata_for_finding(finding: Finding) -> WorkspaceLinkMetadata | None:
    """
    Full workspace deep link for a finding: project, master drawing, optional alignment + diff.

    Delegates to :py:attr:`Finding.workspace_link` so insights (ORM) and findings (serialized)
    stay consistent and diff-backed rows always carry alignmentId + diffId when the ORM can
    resolve relationships.
    """
    raw = finding.workspace_link
    if raw is None:
        return None
    return WorkspaceLinkMetadata.model_validate(raw)


class FindingService:
    def __init__(self, db: Session):
        self.db = db
        self.storage = StorageService(db)

    def _build_workspace_link_for_finding(self, finding: Finding) -> WorkspaceLinkMetadata | None:
        return workspace_link_metadata_for_finding(finding)

    def serialize_finding(self, finding: Finding) -> FindingResponse:
        return FindingResponse(
            id=cast(int, finding.id),
            project_id=cast(int, finding.project_id),
            title=cast(str, finding.title),
            description=cast(Optional[str], getattr(finding, "description", None)),
            severity=cast(Optional[str], getattr(finding, "severity", None)),
            type=cast(Optional[str], getattr(finding, "type", None)),
            created_at=cast(Any, getattr(finding, "created_at", None)),
            workspace_link=self._build_workspace_link_for_finding(finding),
        )

    def list_project_findings(self, project_id: int, limit: Optional[int] = None) -> List[Finding]:
        return self.storage.list_findings_by_project(project_id, limit=limit)
