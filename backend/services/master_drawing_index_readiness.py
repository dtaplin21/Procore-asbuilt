"""Master drawing auto-index readiness for inspection matching."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from models.drawing_region import DrawingRegion
from models.models import Drawing
from services.master_sheet_line_inventory import (
    MasterSheetLineInventory,
    get_master_sheet_line_inventory,
    master_sheet_lines_required_for_matching,
)


@dataclass(frozen=True)
class MasterDrawingIndexReadiness:
    index_status: str
    region_count: int
    is_ready_for_matching: bool
    sheet_line_inventory: MasterSheetLineInventory | None = None

    @property
    def upload_response_status(self) -> str:
        """Frontend-safe index status for evidence upload responses."""
        if self.is_ready_for_matching:
            return "ready"
        if self.index_status == "processing":
            return "processing"
        if self.index_status == "needs_review":
            return "needs_review"
        if self.index_status == "failed":
            return "failed"
        return "pending"

    @property
    def sheet_line_blocker_code(self) -> str | None:
        inv = self.sheet_line_inventory
        if inv is None or inv.is_placable:
            return None
        return inv.blocker_code

    def not_ready_message(self) -> str:
        if self.index_status != "ready" or self.region_count == 0:
            return (
                f"Master drawing index not ready "
                f"(status={self.index_status}, regions={self.region_count})."
            )
        inv = self.sheet_line_inventory
        if inv is not None and not inv.is_placable:
            code = inv.blocker_code or "MASTER_SHEET_LINES_NOT_PLACABLE"
            detail = inv.blocker_message or "Master sheet lines not ready for placement"
            return f"Master sheet lines not ready [{code}] {detail}"
        return "Master drawing not ready for matching."


def get_master_drawing_index_readiness(
    session: Session,
    drawing_id: int,
    *,
    page: int = 1,
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
    base_ready = index_status == "ready" and region_count > 0

    inventory: MasterSheetLineInventory | None = None
    sheet_ok = True
    if base_ready and master_sheet_lines_required_for_matching():
        inventory = get_master_sheet_line_inventory(session, drawing_id, page=page)
        sheet_ok = inventory.is_placable

    is_ready = base_ready and sheet_ok
    return MasterDrawingIndexReadiness(
        index_status=index_status,
        region_count=region_count,
        is_ready_for_matching=is_ready,
        sheet_line_inventory=inventory,
    )
