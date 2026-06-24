"""Finding serialization helpers (workspace deep links via inspection run + overlay)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, List, Optional, cast

from models.models import DrawingOverlay, Finding
from models.schemas import FindingResponse, WorkspaceLinkMetadata
from services.storage import StorageService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_INSPECTION_RUN_AFFECTED_RE = re.compile(r"Inspection run #(\d+)")


def _parse_inspection_run_id_from_affected_items(finding: Finding) -> int | None:
    items = getattr(finding, "affected_items", None) or []
    for item in items:
        if not isinstance(item, str):
            continue
        match = _INSPECTION_RUN_AFFECTED_RE.search(item)
        if match:
            return int(match.group(1))
    return None


def _resolve_master_drawing_id(finding: Finding) -> int | None:
    master_id = getattr(finding, "drawing_id", None)
    if master_id is not None:
        return cast(int, master_id)
    diff_id = getattr(finding, "drawing_diff_id", None)
    if diff_id is None:
        return None
    diff = getattr(finding, "drawing_diff", None)
    if diff is None:
        return None
    alignment = getattr(diff, "alignment", None)
    if alignment is None:
        return None
    return cast(int | None, getattr(alignment, "master_drawing_id", None))


def _find_overlay_for_finding(db: Session, finding: Finding) -> DrawingOverlay | None:
    """Locate the overlay row tied to this finding (meta.finding_id or legacy diff_id)."""
    finding_id = cast(int, finding.id)
    master_id = _resolve_master_drawing_id(finding)

    if master_id is not None:
        overlays = (
            db.query(DrawingOverlay)
            .filter(DrawingOverlay.master_drawing_id == master_id)
            .order_by(DrawingOverlay.id.desc())
            .all()
        )
        for overlay in overlays:
            meta = getattr(overlay, "meta", None)
            if not isinstance(meta, dict):
                continue
            candidate = meta.get("finding_id")
            if candidate is None:
                continue
            try:
                if int(candidate) == finding_id:
                    return overlay
            except (TypeError, ValueError):
                continue

    diff_id = getattr(finding, "drawing_diff_id", None)
    if diff_id is not None:
        return (
            db.query(DrawingOverlay)
            .filter(DrawingOverlay.diff_id == diff_id)
            .order_by(DrawingOverlay.id.desc())
            .first()
        )
    return None


def build_finding_workspace_link_metadata(
    finding: Finding,
    db: Session,
) -> WorkspaceLinkMetadata | None:
    """Structured workspace deep-link metadata for a finding."""
    master_id = _resolve_master_drawing_id(finding)
    if master_id is None:
        return None

    overlay = _find_overlay_for_finding(db, finding)
    inspection_run_id: int | None = None
    overlay_id: int | None = None

    if overlay is not None:
        overlay_id = cast(int, overlay.id)
        raw_run_id = getattr(overlay, "inspection_run_id", None)
        if raw_run_id is not None:
            inspection_run_id = cast(int, raw_run_id)

    if inspection_run_id is None:
        inspection_run_id = _parse_inspection_run_id_from_affected_items(finding)

    return WorkspaceLinkMetadata(
        project_id=cast(int, finding.project_id),
        master_drawing_id=master_id,
        inspection_run_id=inspection_run_id,
        overlay_id=overlay_id,
    )


def build_finding_link(finding: Finding, db: Session) -> str | None:
    """Relative workspace URL with inspection run + overlay query params."""
    meta = build_finding_workspace_link_metadata(finding, db)
    if meta is None:
        return None

    base = (
        f"/projects/{meta.project_id}/drawings/{meta.master_drawing_id}/workspace"
    )
    params: list[str] = []
    if meta.inspection_run_id is not None:
        params.append(f"run={meta.inspection_run_id}")
    if meta.overlay_id is not None:
        params.append(f"overlay={meta.overlay_id}")
    if not params:
        return base
    return f"{base}?{'&'.join(params)}"


def workspace_link_metadata_for_finding(
    finding: Finding,
    db: Session,
) -> WorkspaceLinkMetadata | None:
    """Full workspace deep link metadata for API serialization."""
    return build_finding_workspace_link_metadata(finding, db)


class FindingService:
    def __init__(self, db: Session):
        self.db = db
        self.storage = StorageService(db)

    def _build_workspace_link_for_finding(self, finding: Finding) -> WorkspaceLinkMetadata | None:
        return workspace_link_metadata_for_finding(finding, self.db)

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
