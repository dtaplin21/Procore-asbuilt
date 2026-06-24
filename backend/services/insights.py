"""Build slim insight DTOs with workspace deep links (finding-backed)."""

from __future__ import annotations

from typing import Optional, cast

from sqlalchemy.orm import Session

from models.models import Finding
from models.schemas import InsightResponse
from services.findings import workspace_link_metadata_for_finding


def build_finding_related_insight(finding: Finding, db: Session) -> InsightResponse:
    """InsightResponse derived from a Finding; workspace link uses inspection run + overlay."""
    return InsightResponse(
        id=str(cast(int, finding.id)),
        title=cast(str, finding.title),
        body=cast(Optional[str], finding.description),
        type=cast(Optional[str], finding.type),
        workspace_link=workspace_link_metadata_for_finding(finding, db),
    )
