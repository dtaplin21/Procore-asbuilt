"""Tests for services.region_index_loader — drawing_regions → MasterRegion index."""

from __future__ import annotations

from typing import cast

import pytest
from sqlalchemy.orm import Session

from ai.pipelines.drawing_location_resolver import MasterRegion, resolve_document_location
from ai.pipelines.positioned_term_extractor import PositionedTerm
from ai.pipelines.term_extractor import ExtractedTerm
from models.models import Drawing, DrawingRegion
from services.inspection_vocabulary import VocabCategory
from services.region_index_loader import (
    drawing_region_to_master_region,
    geometry_to_bounding_box,
    load_master_regions,
)


def _extracted(canonical: str, category: VocabCategory) -> ExtractedTerm:
    return ExtractedTerm(
        raw=canonical,
        canonical=canonical,
        category=category,
        confidence=0.9,
    )


def _positioned(canonical: str, category: VocabCategory) -> PositionedTerm:
    from ai.pipelines.document_text_extraction import BoundingBox

    return PositionedTerm(
        term=_extracted(canonical, category),
        page_index=0,
        bbox=BoundingBox(0, 0, 10, 10, 100, 100),
    )


class TestGeometryToBoundingBox:
    def test_rect_geometry(self) -> None:
        bbox = geometry_to_bounding_box(
            {"type": "rect", "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4}
        )
        assert bbox is not None
        assert bbox.to_fractional() == pytest.approx((0.1, 0.2, 0.4, 0.6))

    def test_polygon_geometry_uses_axis_aligned_bounds(self) -> None:
        bbox = geometry_to_bounding_box(
            {
                "type": "polygon",
                "points": [[0.1, 0.1], [0.5, 0.1], [0.5, 0.4], [0.1, 0.4]],
            }
        )
        assert bbox is not None
        assert bbox.to_fractional() == pytest.approx((0.1, 0.1, 0.5, 0.4))

    def test_invalid_geometry_returns_none(self) -> None:
        assert geometry_to_bounding_box({"type": "line"}) is None


class TestDrawingRegionToMasterRegion:
    def test_maps_tags_and_geometry(self) -> None:
        row = DrawingRegion(
            id=42,
            master_drawing_id=7,
            label="Zone A",
            page=1,
            geometry={"type": "rect", "x": 0.0, "y": 0.0, "width": 0.5, "height": 0.5},
            inspection_type_tags=["Underground Fire Water Rough In", "Rough In"],
            location_tags=["Utility MR", "utility mr"],
        )
        region = drawing_region_to_master_region(row)
        assert region is not None
        assert region.region_id == "42"
        assert region.master_drawing_id == "7"
        assert region.inspection_types == ("Underground Fire Water Rough In", "Rough In")
        assert region.location_labels == ("Utility MR",)
        assert region.bbox_on_master.to_fractional() == pytest.approx((0.0, 0.0, 0.5, 0.5))

    def test_empty_tags_still_produces_region_for_alignment_overlap(self) -> None:
        row = DrawingRegion(
            id=1,
            master_drawing_id=1,
            label="Untagged",
            page=1,
            geometry={"type": "rect", "x": 0.0, "y": 0.0, "width": 0.1, "height": 0.1},
        )
        region = drawing_region_to_master_region(row)
        assert region is not None
        assert region.inspection_types == ()
        assert region.location_labels == ()


class TestLoadMasterRegions:
    def test_load_from_db(
        self,
        db_session: Session,
        master_drawing: Drawing,
    ) -> None:
        db_session.add(
            DrawingRegion(
                master_drawing_id=master_drawing.id,
                label="Tagged zone",
                page=1,
                geometry={"type": "rect", "x": 0.2, "y": 0.2, "width": 0.1, "height": 0.1},
                inspection_type_tags=["Rough In"],
                location_tags=["Utility MR"],
            )
        )
        db_session.commit()

        index = load_master_regions(db_session, cast(int, master_drawing.id))
        assert len(index) == 1
        assert index[0].inspection_types == ("Rough In",)
        assert index[0].location_labels == ("Utility MR",)

    def test_case_b_resolves_against_loaded_index(
        self,
        db_session: Session,
        master_drawing: Drawing,
    ) -> None:
        db_session.add(
            DrawingRegion(
                master_drawing_id=master_drawing.id,
                label="Utility room",
                page=1,
                geometry={"type": "rect", "x": 0.3, "y": 0.3, "width": 0.2, "height": 0.2},
                inspection_type_tags=["Underground Fire Water Rough In"],
                location_tags=["Utility MR"],
            )
        )
        db_session.commit()

        index = load_master_regions(db_session, cast(int, master_drawing.id))
        terms = [
            _positioned("Underground Fire Water Rough In", VocabCategory.INSPECTION_TYPE),
            _positioned("Utility MR", VocabCategory.LOCATION_TERM),
        ]
        resolved = resolve_document_location(
            terms,
            str(master_drawing.id),
            index,
        )
        assert resolved.bbox_fractional == pytest.approx((0.3, 0.3, 0.5, 0.5))
        assert resolved.matched_region is not None
        assert resolved.confidence_score == pytest.approx(0.92)


@pytest.fixture
def master_drawing(db_session: Session, project) -> Drawing:
    drawing = Drawing(
        project_id=project.id,
        source="upload",
        name="master.pdf",
        storage_key=None,
        content_type="application/pdf",
    )
    db_session.add(drawing)
    db_session.commit()
    db_session.refresh(drawing)
    return drawing
