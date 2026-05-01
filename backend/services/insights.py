"""Build slim insight DTOs with workspace deep links (diff- or finding-backed)."""

from __future__ import annotations

from typing import Optional, cast

from models.models import DrawingAlignment, DrawingDiff, Finding
from models.schemas import InsightResponse, WorkspaceLinkMetadata
from services.findings import workspace_link_metadata_for_finding


def build_diff_related_insight(diff: DrawingDiff, alignment: DrawingAlignment) -> InsightResponse:
    diff_id = cast(int, diff.id)
    summary = getattr(diff, "summary", None) or None
    return InsightResponse(
        id=f"diff-{diff_id}",
        title=summary or f"Diff #{diff_id}",
        body=summary,
        type="drawing_diff",
        workspace_link=WorkspaceLinkMetadata(
            project_id=cast(int, alignment.project_id),
            master_drawing_id=cast(int, alignment.master_drawing_id),
            alignment_id=cast(int, alignment.id),
            diff_id=diff_id,
        ),
    )


def build_finding_related_insight(finding: Finding) -> InsightResponse:
    """InsightResponse derived from a Finding; workspace link matches Finding.workspace_link."""
    return InsightResponse(
        id=str(cast(int, finding.id)),
        title=cast(str, finding.title),
        body=cast(Optional[str], finding.description),
        type=cast(Optional[str], finding.type),
        workspace_link=workspace_link_metadata_for_finding(finding),
    )
