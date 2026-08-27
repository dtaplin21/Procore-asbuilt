"""Tests for auxiliary drawing station range extraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from sqlalchemy.orm import Session

from ai.pipelines.station_range_extractor import (
    StationRangeResult,
    extract_station_range_for_drawings,
    extract_station_range_from_tokens,
    station_chainage,
)
from models.drawing_text_element import DrawingTextElement
from models.models import Drawing


@dataclass(frozen=True)
class _Token:
    text: str
    bbox_json: dict[str, float]


def test_station_chainage_orders_stations() -> None:
    assert station_chainage("10+00") < station_chainage("10+90.95")
    assert station_chainage("10+90.95") < station_chainage("11+14.23")


def test_extract_station_range_from_tokens_ignores_profile_strip() -> None:
    tokens = (
        _Token("SAN STA 10+00", {"x0": 0.08, "y0": 0.18, "x1": 0.12, "y1": 0.22}),
        _Token("10+90.95", {"x0": 0.27, "y0": 0.26, "x1": 0.31, "y1": 0.28}),
        _Token("10+00", {"x0": 0.08, "y0": 0.94, "x1": 0.12, "y1": 0.96}),
    )

    result = extract_station_range_from_tokens(tokens, max_profile_y=0.85)

    assert result.station_from == "10+00"
    assert result.station_to == "10+90.95"
    assert result.station_from_bbox_json is not None
    assert result.station_to_bbox_json is not None


def test_extract_station_range_from_tokens_pairs_plan_with_profile_minimum() -> None:
    tokens = (
        _Token("10+90.95", {"x0": 0.27, "y0": 0.26, "x1": 0.31, "y1": 0.28}),
        _Token("10+00", {"x0": 0.08, "y0": 0.94, "x1": 0.12, "y1": 0.96}),
    )

    result = extract_station_range_from_tokens(tokens, max_profile_y=0.85)

    assert result.station_from == "10+00"
    assert result.station_to == "10+90.95"


def test_extract_station_range_from_tokens_picks_widest_major_when_plan_spans_majors() -> None:
    """C4.20 has 10+90.95 and 11+14.23 on plan plus profile-grid majors."""
    tokens = (
        _Token("10+90.95", {"x0": 0.27, "y0": 0.26, "x1": 0.31, "y1": 0.28}),
        _Token("11+14.23", {"x0": 0.35, "y0": 0.27, "x1": 0.39, "y1": 0.29}),
        _Token("10+00", {"x0": 0.08, "y0": 0.94, "x1": 0.12, "y1": 0.96}),
        _Token("11+00", {"x0": 0.33, "y0": 0.94, "x1": 0.37, "y1": 0.96}),
    )

    result = extract_station_range_from_tokens(tokens, max_profile_y=0.85)

    assert result.station_from == "10+00"
    assert result.station_to == "10+90.95"


def test_extract_station_range_from_tokens_requires_two_plan_stations_without_profile_pair() -> None:
    tokens = (
        _Token("10+90.95", {"x0": 0.27, "y0": 0.26, "x1": 0.31, "y1": 0.28}),
    )

    result = extract_station_range_from_tokens(tokens, max_profile_y=0.85)

    assert result.station_from is None
    assert result.station_to is None


def test_extract_station_range_for_drawings_picks_richest_linked_sheet(
    db_session: Session,
    project,
) -> None:
    project_id = cast(int, project.id)
    sparse = Drawing(
        project_id=project_id,
        source="linked_evidence",
        name="sparse.pdf",
        content_type="application/pdf",
        processing_status="ready",
        index_status="ready",
    )
    rich = Drawing(
        project_id=project_id,
        source="linked_evidence",
        name="c4-20.pdf",
        content_type="application/pdf",
        processing_status="ready",
        index_status="ready",
    )
    db_session.add_all([sparse, rich])
    db_session.flush()

    sparse_id = cast(int, sparse.id)
    rich_id = cast(int, rich.id)

    db_session.add(
        DrawingTextElement(
            master_drawing_id=sparse_id,
            page=1,
            text="11+00",
            text_normalized="11+00",
            bbox_json={"x0": 0.2, "y0": 0.2, "x1": 0.22, "y1": 0.22},
            source="tesseract",
        )
    )
    db_session.add_all(
        [
            DrawingTextElement(
                master_drawing_id=rich_id,
                page=1,
                text="SAN STA 10+00",
                text_normalized="san sta 10+00",
                bbox_json={"x0": 0.08, "y0": 0.18, "x1": 0.12, "y1": 0.22},
                source="tesseract",
            ),
            DrawingTextElement(
                master_drawing_id=rich_id,
                page=1,
                text="10+90.95",
                text_normalized="10+90.95",
                bbox_json={"x0": 0.27, "y0": 0.26, "x1": 0.31, "y1": 0.28},
                source="tesseract",
            ),
        ]
    )
    db_session.commit()

    result = extract_station_range_for_drawings(db_session, [sparse_id, rich_id])

    assert result == StationRangeResult(
        station_from="10+00",
        station_to="10+90.95",
        station_from_bbox_json={"x0": 0.08, "y0": 0.18, "x1": 0.12, "y1": 0.22},
        station_to_bbox_json={"x0": 0.27, "y0": 0.26, "x1": 0.31, "y1": 0.28},
        source_drawing_id=rich_id,
    )
