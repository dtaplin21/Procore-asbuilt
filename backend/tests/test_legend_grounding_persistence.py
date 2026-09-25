"""DB persistence for legend grounding hits."""

from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from ai.pipelines.legend_grounding import GroundingHit
from ai.pipelines.legend_icon_extraction import LegendIconEntry
from models.drawing_legend_grounding_hit import DrawingLegendGroundingHit
from models.models import Drawing
from services.legend_grounding_service import (
    delete_grounding_hits_for_page,
    persist_grounding_hits,
)


def _ensure_grounding_hits_table(session: Session) -> None:
    bind = session.get_bind()
    if "drawing_legend_grounding_hits" in inspect(bind).get_table_names():
        return
    DrawingLegendGroundingHit.__table__.create(bind)


def test_persist_grounding_hits(db_session: Session, sample_pdf_drawing: Drawing) -> None:
    _ensure_grounding_hits_table(db_session)
    drawing_id = int(sample_pdf_drawing.id)
    entries = [
        LegendIconEntry(
            row_id=0,
            label_text="WATER LINE",
            icon_crop_path="/tmp/icon.png",
            icon_fractional_bbox=(0.66, 0.05, 0.72, 0.07),
            label_fractional_bbox=(0.72, 0.05, 0.90, 0.07),
            source="indexed_tokens",
        ),
    ]
    hits = {
        "WATER LINE": [
            GroundingHit(
                label_text="WATER LINE",
                confidence=0.92,
                page_fractional_bbox=(0.30, 0.40, 0.36, 0.42),
                match_method="template_match",
            ),
        ],
    }

    delete_grounding_hits_for_page(db_session, master_drawing_id=drawing_id, page=1)
    rows = persist_grounding_hits(
        db_session,
        master_drawing_id=drawing_id,
        page=1,
        grounding_run_id="test-run-1",
        legend_entries=entries,
        hits_by_label=hits,
    )
    db_session.commit()

    assert len(rows) == 1
    stored = (
        db_session.query(DrawingLegendGroundingHit)
        .filter(DrawingLegendGroundingHit.master_drawing_id == drawing_id)
        .all()
    )
    assert len(stored) == 1
    assert stored[0].match_method == "template_match"
    assert stored[0].bbox_json["x0"] == 0.30
