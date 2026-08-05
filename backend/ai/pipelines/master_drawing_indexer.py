"""Master drawing OCR index pipeline (Phase 2+).

Phase 1a wires the job; OCR ingest, scale parsing, and region building land here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy.orm import Session

from models.models import Drawing, DrawingRendition


@dataclass(frozen=True)
class IndexResult:
    pages: int = 0
    text_elements: int = 0
    regions: int = 0
    scale_found: bool = False
    scale_json: dict[str, Any] | None = None
    page_meta_json: list[dict[str, Any]] | None = None

    def to_stats_json(self) -> dict[str, Any]:
        return {
            "pages": self.pages,
            "text_elements": self.text_elements,
            "regions": self.regions,
            "scale_found": self.scale_found,
        }


def index_master_drawing(drawing_id: int, session: Session) -> IndexResult:
    """Run OCR ingest, scale extraction, legend tagging, and region build.

    Stub until Phase 2–5 are implemented; returns page count from the drawing.
    """
    drawing = session.get(Drawing, drawing_id)
    if drawing is None:
        raise ValueError(f"Drawing {drawing_id} not found")

    pages = cast(int | None, drawing.page_count)
    if not pages:
        pages = (
            session.query(DrawingRendition)
            .filter(DrawingRendition.drawing_id == drawing_id)
            .count()
        )

    return IndexResult(pages=int(pages or 0))
