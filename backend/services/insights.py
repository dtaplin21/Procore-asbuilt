"""Build slim insight DTOs with workspace deep links (diff- or finding-backed)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from models.models import DrawingAlignment, DrawingDiff, Finding
from models.schemas import InsightResponse, WorkspaceLinkMetadata
from services.findings import workspace_link_metadata_for_finding
from services.storage import StorageService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def build_diff_related_insight(diff: DrawingDiff, alignment: DrawingAlignment) -> InsightResponse:
    summary = getattr(diff, "summary", None) or None
    return InsightResponse(
        id=f"diff-{diff.id}",
        title=summary or f"Diff #{diff.id}",
        body=summary,
        type="drawing_diff",
        workspace_link=WorkspaceLinkMetadata(
            project_id=alignment.project_id,
            master_drawing_id=alignment.master_drawing_id,
            alignment_id=alignment.id,
            diff_id=diff.id,
        ),
    )


def build_finding_related_insight(finding: Finding, db: Session) -> InsightResponse:
    """InsightResponse derived from a Finding; workspace link follows drawing_diff_id when present."""
    storage = StorageService(db)
    return InsightResponse(
        id=str(finding.id),
        title=finding.title,
        body=getattr(finding, "description", None),
        type=getattr(finding, "type", None),
        workspace_link=workspace_link_metadata_for_finding(finding, storage),
    )
