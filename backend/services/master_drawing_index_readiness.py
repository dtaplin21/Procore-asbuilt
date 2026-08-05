"""Master drawing auto-index readiness for inspection matching."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from models.drawing_region import DrawingRegion
from models.models import Drawing


@dataclass(frozen=True)
class MasterDrawingIndexReadiness:
    index_status: str
    region_count: int
    is_ready_for_matching: bool

    @property
    def upload_response_status(self) -> str:
        """Frontend-safe index status for evidence upload responses."""
        if self.is_ready_for_matching:
            return "ready"
        if self.index_status == "processing":
            return "processing"
        if self.index_status == "failed":
            return "failed"
        return "pending"


def get_master_drawing_index_readiness(
    session: Session,
    drawing_id: int,
) -> MasterDrawingIndexReadiness:
    drawing = session.get(Drawing, drawing_id)
    if drawing is None:
        return MasterDrawingIndexReadiness(
            index_status="pending",
            region_count=0,
            is_ready_for_matching=False,
        )

    index_status = str(getattr(drawing, "index_status", "pending") or "pending")
    region_count = (
        session.query(DrawingRegion)
        .filter(DrawingRegion.master_drawing_id == drawing_id)
        .count()
    )
    is_ready = index_status == "ready" and region_count > 0
    return MasterDrawingIndexReadiness(
        index_status=index_status,
        region_count=region_count,
        is_ready_for_matching=is_ready,
    )
