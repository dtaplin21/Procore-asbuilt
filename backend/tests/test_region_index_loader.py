"""Tests for services.region_index_loader — drawing_regions → MasterRegion index.

``build_region_index`` integration tests use an in-memory SQLite database with a
SQLite-compatible mirror of ``DrawingRegion`` (JSON tag columns instead of
Postgres ARRAY). The loader module is monkeypatched to query that model so
query + conversion logic is verified against a real, queryable DB without
requiring Postgres or the a3f9c1d8e2b4 migration at test time.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.types import JSON

from ai.pipelines.drawing_location_resolver import MasterRegion, resolve_document_location
from ai.pipelines.positioned_term_extractor import PositionedTerm
from ai.pipelines.term_extractor import ConfidenceLabel, ExtractedTerm
from models.models import DrawingRegion
from services import region_index_loader as loader_module
from services.inspection_vocabulary import VocabCategory
from services.region_index_loader import (
    build_region_index,
    drawing_region_to_master_region,
    geometry_to_bounding_box,
    load_master_regions,
)

SQLiteModelBase = declarative_base()


class DrawingRegionSQLite(SQLiteModelBase):
    """SQLite test double for models.models.DrawingRegion — JSON tags, same shape."""

    __tablename__ = "drawing_regions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    master_drawing_id = Column(Integer, nullable=False, index=True)
    label = Column(String(length=255), nullable=False)
    page = Column(Integer, nullable=False, default=1)
    geometry = Column(JSON, nullable=False)
    inspection_type_tags = Column(JSON, nullable=True)
    location_tags = Column(JSON, nullable=True)


@pytest.fixture
def db_session(monkeypatch: pytest.MonkeyPatch):
    """Ephemeral SQLite DB; loader queries DrawingRegionSQLite for these tests."""
    engine = create_engine("sqlite:///:memory:")
    SQLiteModelBase.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    monkeypatch.setattr(loader_module, "DrawingRegion", DrawingRegionSQLite)

    yield session
    session.close()


def _rect_geometry(
    x: float,
    y: float,
    width: float,
    height: float,
) -> dict[str, float | str]:
    return {"type": "rect", "x": x, "y": y, "width": width, "height": height}


def _insert_region(
    db: Session,
    *,
    master_drawing_id: int = 1,
    label: str = "Region",
    geometry: dict | None = None,
    inspection_type_tags: list[str] | None = None,
    location_tags: list[str] | None = None,
) -> DrawingRegionSQLite:
    region = DrawingRegionSQLite(
        master_drawing_id=master_drawing_id,
        label=label,
        page=1,
        geometry=geometry or _rect_geometry(0.0, 0.0, 0.1, 0.1),
        inspection_type_tags=inspection_type_tags,
        location_tags=location_tags,
    )
    db.add(region)
    db.commit()
    db.refresh(region)
    return region


def _extracted(canonical: str, category: VocabCategory) -> ExtractedTerm:
    return ExtractedTerm(
        category=category,
        canonical=canonical,
        matched_text=canonical,
        start=0,
        end=len(canonical),
        confidence_score=0.9,
        confidence_label=ConfidenceLabel.HIGH,
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
        bbox = geometry_to_bounding_box(_rect_geometry(0.1, 0.2, 0.3, 0.4))
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
            geometry=_rect_geometry(0.0, 0.0, 0.5, 0.5),
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
            geometry=_rect_geometry(0.0, 0.0, 0.1, 0.1),
        )
        region = drawing_region_to_master_region(row)
        assert region is not None
        assert region.inspection_types == ()
        assert region.location_labels == ()


class TestBuildRegionIndexBasics:
    def test_loads_tagged_region_into_master_region(self, db_session: Session) -> None:
        row = _insert_region(
            db_session,
            inspection_type_tags=["Underground Fire Water Rough In"],
            location_tags=["Utility MR"],
        )
        result = build_region_index(db_session, 1)

        assert result.total_region_count == 1
        assert result.untagged_region_count == 0
        assert len(result.regions) == 1

        region = result.regions[0]
        assert isinstance(region, MasterRegion)
        assert region.region_id == str(row.id)
        assert region.master_drawing_id == "1"
        assert region.inspection_types == ("Underground Fire Water Rough In",)
        assert region.location_labels == ("Utility MR",)

    def test_bbox_converted_correctly(self, db_session: Session) -> None:
        _insert_region(
            db_session,
            location_tags=["Roof"],
            geometry=_rect_geometry(0.01, 0.02, 0.03, 0.04),
        )
        result = build_region_index(db_session, 1)
        bbox = result.regions[0].bbox_on_master
        assert bbox.x == pytest.approx(0.01)
        assert bbox.y == pytest.approx(0.02)
        assert bbox.width == pytest.approx(0.03)
        assert bbox.height == pytest.approx(0.04)
        assert bbox.page_width == pytest.approx(1.0)
        assert bbox.page_height == pytest.approx(1.0)

    def test_only_loads_regions_for_the_requested_drawing(self, db_session: Session) -> None:
        row_a = _insert_region(db_session, master_drawing_id=1, location_tags=["Roof"])
        _insert_region(db_session, master_drawing_id=2, location_tags=["Yard"])

        result = build_region_index(db_session, 1)
        assert result.total_region_count == 1
        assert result.regions[0].region_id == str(row_a.id)

    def test_no_regions_for_drawing_returns_empty_result(self, db_session: Session) -> None:
        result = build_region_index(db_session, 1)
        assert result.regions == []
        assert result.total_region_count == 0
        assert result.untagged_region_count == 0
        assert result.has_any_taggable_regions is False
        assert result.has_any_usable_regions is False


class TestUntaggedRegionFiltering:
    def test_untagged_region_excluded_by_default(self, db_session: Session) -> None:
        tagged = _insert_region(db_session, label="tagged", location_tags=["Roof"])
        _insert_region(db_session, label="untagged")

        result = build_region_index(db_session, 1)
        assert result.total_region_count == 2
        assert result.untagged_region_count == 1
        assert len(result.regions) == 1
        assert result.regions[0].region_id == str(tagged.id)

    def test_region_with_empty_list_tags_counts_as_untagged(self, db_session: Session) -> None:
        _insert_region(
            db_session,
            inspection_type_tags=[],
            location_tags=[],
        )
        result = build_region_index(db_session, 1)
        assert result.untagged_region_count == 1
        assert result.regions == []

    def test_include_untagged_returns_everything(self, db_session: Session) -> None:
        tagged = _insert_region(db_session, label="tagged", location_tags=["Roof"])
        untagged = _insert_region(db_session, label="untagged")

        result = build_region_index(db_session, 1, include_untagged=True)
        assert len(result.regions) == 2
        region_ids = {r.region_id for r in result.regions}
        assert region_ids == {str(tagged.id), str(untagged.id)}

    def test_region_with_only_inspection_type_is_not_untagged(self, db_session: Session) -> None:
        _insert_region(db_session, inspection_type_tags=["Final"])
        result = build_region_index(db_session, 1)
        assert result.untagged_region_count == 0
        assert len(result.regions) == 1


class TestRealisticMultiRegionScenario:
    def test_drawing_with_several_regions_loads_correctly(self, db_session: Session) -> None:
        _insert_region(
            db_session,
            label="r1",
            inspection_type_tags=["Underground Fire Water Rough In"],
            location_tags=["Utility MR"],
            geometry=_rect_geometry(0.0, 0.0, 0.1, 0.1),
        )
        row_r2 = _insert_region(
            db_session,
            label="r2",
            inspection_type_tags=["Final", "Hydrostatic Test"],
            location_tags=["Mechanical Room"],
            geometry=_rect_geometry(0.2, 0.0, 0.1, 0.1),
        )
        _insert_region(db_session, label="r3")

        result = build_region_index(db_session, 1)
        assert result.total_region_count == 3
        assert result.untagged_region_count == 1
        assert len(result.regions) == 2

        by_id = {r.region_id: r for r in result.regions}
        assert by_id[str(row_r2.id)].inspection_types == ("Final", "Hydrostatic Test")


class TestResolverIntegration:
    def test_case_b_resolves_against_loaded_index(self, db_session: Session) -> None:
        _insert_region(
            db_session,
            geometry=_rect_geometry(0.3, 0.3, 0.2, 0.2),
            inspection_type_tags=["Underground Fire Water Rough In"],
            location_tags=["Utility MR"],
        )

        index = load_master_regions(db_session, 1)
        terms = [
            _positioned("Underground Fire Water Rough In", VocabCategory.INSPECTION_TYPE),
            _positioned("Utility MR", VocabCategory.LOCATION_TERM),
        ]
        resolved = resolve_document_location(terms, "1", index)
        assert resolved.bbox_fractional == pytest.approx((0.3, 0.3, 0.5, 0.5))
        assert resolved.matched_region is not None
        assert resolved.confidence_score == pytest.approx(0.92)
