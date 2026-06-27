"""
Tests for scripts/seed_drawing_regions.py against real fixture files and
Postgres (via conftest) — reconciled with normalized geometry JSON and
integer master_drawing_id.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from models.drawing_region import DrawingRegion
from scripts.seed_drawing_regions import (
    _geometry_from_entry,
    _label_from_entry,
    load_fixture,
    seed_regions_from_fixture,
)

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "sample_drawing_regions.json"
UTILITY_PLAN_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "utility_plan_regions.json"
)


class TestLoadFixture:
    def test_loads_real_fixture_file(self) -> None:
        entries = load_fixture(FIXTURE_PATH)
        assert len(entries) == 3
        assert entries[0]["label"] == "Utility MR"
        assert entries[0]["location_tags"] == ["Utility MR"]

    def test_raises_on_missing_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_fixture(Path("/nonexistent/fixture.json"))

    def test_raises_on_non_array_fixture(self, tmp_path: Path) -> None:
        bad_fixture = tmp_path / "bad.json"
        bad_fixture.write_text('{"not": "an array"}', encoding="utf-8")

        with pytest.raises(ValueError, match="Expected a JSON array"):
            load_fixture(bad_fixture)


class TestSeedRegionsFromFixture:
    def test_seeds_all_entries_from_real_fixture(
        self, db_session, sample_pdf_drawing
    ) -> None:
        master_id = cast(int, sample_pdf_drawing.id)
        count = seed_regions_from_fixture(db_session, master_id, FIXTURE_PATH)
        assert count == 3

        rows = (
            db_session.query(DrawingRegion)
            .filter(DrawingRegion.master_drawing_id == master_id)
            .all()
        )
        assert len(rows) == 3

    def test_seeded_region_has_correct_geometry_and_tags(
        self, db_session, sample_pdf_drawing
    ) -> None:
        master_id = cast(int, sample_pdf_drawing.id)
        seed_regions_from_fixture(db_session, master_id, FIXTURE_PATH)
        rows = (
            db_session.query(DrawingRegion)
            .filter(DrawingRegion.master_drawing_id == master_id)
            .all()
        )

        utility_mr = next(r for r in rows if r.label == "Utility MR")
        geometry = cast(dict, utility_mr.geometry)
        assert geometry["x"] == pytest.approx(0.08)
        assert utility_mr.location_tags == ["Utility MR"]
        assert utility_mr.inspection_type_tags == ["Rough In"]

    def test_seeded_polygon_region_persists_points(
        self, db_session, sample_pdf_drawing
    ) -> None:
        master_id = cast(int, sample_pdf_drawing.id)
        seed_regions_from_fixture(db_session, master_id, FIXTURE_PATH)
        rows = (
            db_session.query(DrawingRegion)
            .filter(DrawingRegion.master_drawing_id == master_id)
            .all()
        )

        polygon_region = next(r for r in rows if r.polygon_points is not None)
        assert len(cast(list, polygon_region.polygon_points)) == 4

    def test_raises_on_entry_missing_geometry(
        self, db_session, sample_pdf_drawing, tmp_path: Path
    ) -> None:
        master_id = cast(int, sample_pdf_drawing.id)
        bad_fixture = tmp_path / "bad.json"
        bad_fixture.write_text('[{"label": "X", "tags": {}}]', encoding="utf-8")

        with pytest.raises(ValueError, match="requires a geometry object"):
            seed_regions_from_fixture(db_session, master_id, bad_fixture)

    def test_raises_on_missing_drawing(self, db_session) -> None:
        with pytest.raises(ValueError, match="not found"):
            seed_regions_from_fixture(db_session, 999999, FIXTURE_PATH)


class TestLegacyFixtureHelpers:
    def test_geometry_from_entry_legacy_pixel_bbox(self) -> None:
        geometry, polygon = _geometry_from_entry(
            {
                "geometry": {
                    "x": 61.2,
                    "y": 95.04,
                    "width": 122.4,
                    "height": 142.56,
                    "page_width": 612.0,
                    "page_height": 792.0,
                }
            },
            0,
        )
        assert geometry["type"] == "rect"
        assert geometry["x"] == pytest.approx(0.1)
        assert geometry["width"] == pytest.approx(0.2)
        assert polygon is None

    def test_geometry_from_entry_normalizes_polygon_in_legacy_geometry(self) -> None:
        geometry, polygon = _geometry_from_entry(
            {
                "geometry": {
                    "x": 600,
                    "y": 450,
                    "width": 80,
                    "height": 80,
                    "page_width": 2000,
                    "page_height": 1500,
                    "polygon_points": [[600, 450], [680, 450], [660, 530], [610, 510]],
                }
            },
            2,
        )
        assert geometry["x"] == pytest.approx(0.3)
        assert polygon is not None
        assert polygon[0] == pytest.approx([0.3, 0.3])
        assert polygon[1][0] == pytest.approx(0.34)

    def test_label_from_entry_uses_location_tag_when_label_omitted(self) -> None:
        label = _label_from_entry(
            {},
            0,
            ["Hydrostatic Test"],
            ["Utility MR"],
        )
        assert label == "Utility MR"


class TestUtilityPlanFixture:
    def test_seeds_legacy_pixel_fixture_with_derived_labels(
        self, db_session, sample_pdf_drawing
    ) -> None:
        master_id = cast(int, sample_pdf_drawing.id)
        count = seed_regions_from_fixture(db_session, master_id, UTILITY_PLAN_FIXTURE)
        assert count == 3

        rows = (
            db_session.query(DrawingRegion)
            .filter(DrawingRegion.master_drawing_id == master_id)
            .order_by(DrawingRegion.id.asc())
            .all()
        )
        assert rows[0].label == "Utility MR"
        assert rows[0].inspection_type_tags == [
            "Underground Fire Water Rough In",
            "Hydrostatic Test",
        ]
        assert rows[2].label == "Yard"
        assert rows[2].polygon_points is not None
        assert len(cast(list, rows[2].polygon_points)) == 4
