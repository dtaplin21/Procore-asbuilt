"""
Tests for services.region_index_loader — drawing_regions → MasterRegion index.

Exercises ``build_region_index`` against a REAL database (SQLite in-memory)
rather than mocking the ORM layer — the production model uses Postgres
ARRAY columns, which SQLite does not support natively, so this test defines a
SQLite-compatible mirror of DrawingRegion using JSON-backed columns for the
two tag fields. The production model (models/drawing_region.py) uses
postgresql.ARRAY directly; this test double exists purely so the loader's
QUERY and CONVERSION logic gets verified against a real, queryable database
instead of hand-rolled fakes.

IMPORTANT: this test double registers on the SAME shared models.base.Base as
every real model (DrawingOverlay, InspectionRun, etc.), not a separate
declarative_base(). Cross-model foreign keys (e.g. DrawingOverlay.region_id
→ drawing_regions.id) only resolve at mapper-configuration time if both tables
live in one shared metadata registry — using a second, disconnected Base here
was a real bug that broke every test importing both this module and
models.drawing_overlay together (NoReferencedTableError).

Reconciled with this codebase: integer PK/FK ``master_drawing_id``, normalized
0–1 ``geometry`` JSON (not legacy pixel x/y/width columns).
"""

from __future__ import annotations

import pytest
from sqlalchemy import Column, ForeignKey, Integer, String, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import JSON

from ai.pipelines.drawing_location_resolver import MasterRegion, resolve_document_location
from ai.pipelines.positioned_term_extractor import PositionedTerm
from ai.pipelines.term_extractor import ConfidenceLabel, ExtractedTerm
from models.base import Base as SQLiteModelBase
from models.drawing_region import DrawingRegion
from services import region_index_loader as loader_module
from services.inspection_vocabulary import VocabCategory
from services.region_index_loader import (
    build_region_index,
    drawing_region_to_master_region,
    geometry_to_bounding_box,
    load_master_regions,
)


class DrawingRegionSQLite(SQLiteModelBase):
    """SQLite-compatible test double for models.drawing_region.DrawingRegion.

    Same columns as production, JSON instead of ARRAY for tag fields (SQLite
    has no array type). See module docstring.

    extend_existing=True: models.drawing_region.DrawingRegion already registers
    a table named ``drawing_regions`` on this same shared Base when that module
    is imported (transitively, via services.region_index_loader, which imports
    the real DrawingRegion class directly) — without this flag, SQLAlchemy
    raises on the duplicate table name.

    NOTE: index=True is deliberately OMITTED on master_drawing_id here (unlike
    the production model) — with extend_existing, both classes mapped to one
    table name in one registry would each try to issue their own CREATE INDEX
    for the same index name, which collides ("index ... already exists"). The
    production DrawingRegion model already declares this index in the same
    shared metadata, so it is redundant (and breaks table creation) to repeat
    it here.
    """

    __tablename__ = "drawing_regions"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    master_drawing_id = Column(
        Integer,
        ForeignKey("drawings.id", ondelete="CASCADE"),
        nullable=False,
    )
    label = Column(String(length=255), nullable=False)
    page = Column(Integer, nullable=False, default=1)
    geometry = Column(JSON, nullable=False)
    polygon_points = Column(JSON, nullable=True)
    inspection_type_tags = Column(JSON, nullable=True)
    location_tags = Column(JSON, nullable=True)


@pytest.fixture
def db_session(monkeypatch: pytest.MonkeyPatch):
    """Real, ephemeral SQLite DB per test, with the loader module monkeypatched
    to query the SQLite-compatible model instead of the production Postgres one.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.close()

    SQLiteModelBase.metadata.create_all(
        engine,
        tables=[SQLiteModelBase.metadata.tables["drawing_regions"]],
    )
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


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
