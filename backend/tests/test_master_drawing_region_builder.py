"""Tests for auto-generated drawing regions (Phase 5)."""

from __future__ import annotations

from typing import cast

from unittest.mock import patch

import pytest

from ai.pipelines.master_drawing_region_builder import (
    AUTO_INDEX_REGION_SOURCE,
    IndexedElement,
    _union_rect_geometry,
    build_auto_regions_from_text_elements,
    cluster_elements_by_fixed_grid,
    cluster_elements_by_grid,
    is_junk_text_element,
)
from models.drawing_region import DrawingRegion
from models.drawing_text_element import DrawingTextElement
from models.models import Drawing
from scripts.seed_legend_reference import seed
from services.master_drawing_legend_tagger import enrich_text_element
from services.storage import StorageService


def _element(
    *,
    text: str,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    page: int = 1,
    confidence: float = 0.9,
) -> DrawingTextElement:
    return DrawingTextElement(
        master_drawing_id=1,
        page=page,
        text=text,
        text_normalized=text.lower(),
        bbox_json={"x0": x0, "y0": y0, "x1": x1, "y1": y1},
        ocr_confidence=confidence,
        source="native_pdf",
    )


def test_union_rect_geometry_clamps_off_page_ocr_cluster() -> None:
    elements = [
        IndexedElement(
            row=_element(text="UCSF", x0=0.22, y0=1.27, x1=0.24, y1=1.36),
            x0=0.22,
            y0=1.27,
            x1=0.24,
            y1=1.36,
            centroid_x=0.23,
            centroid_y=1.315,
        ),
    ]

    geometry = _union_rect_geometry(elements)

    assert geometry["y"] <= 1.0
    assert geometry["y"] + geometry["height"] <= 1.001


def test_is_junk_text_element_filters_low_confidence_and_noise() -> None:
    assert is_junk_text_element(_element(text="SS", x0=0.1, y0=0.1, x1=0.11, y1=0.11)) is False
    assert is_junk_text_element(
        _element(text="SS", x0=0.1, y0=0.1, x1=0.11, y1=0.11, confidence=0.4)
    ) is True
    assert is_junk_text_element(_element(text="3", x0=0.1, y0=0.1, x1=0.11, y1=0.11)) is True
    assert is_junk_text_element(_element(text="...", x0=0.1, y0=0.1, x1=0.11, y1=0.11)) is True


def test_cluster_elements_by_grid_groups_nearby_tokens() -> None:
    elements = [
        IndexedElement(
            row=_element(text="SS", x0=0.10, y0=0.10, x1=0.12, y1=0.12),
            x0=0.10,
            y0=0.10,
            x1=0.12,
            y1=0.12,
            centroid_x=0.11,
            centroid_y=0.11,
        ),
        IndexedElement(
            row=_element(text="COLO", x0=0.11, y0=0.11, x1=0.14, y1=0.13),
            x0=0.11,
            y0=0.11,
            x1=0.14,
            y1=0.13,
            centroid_x=0.125,
            centroid_y=0.12,
        ),
        IndexedElement(
            row=_element(text="MLK", x0=0.80, y0=0.80, x1=0.83, y1=0.82),
            x0=0.80,
            y0=0.80,
            x1=0.83,
            y1=0.82,
            centroid_x=0.815,
            centroid_y=0.81,
        ),
    ]

    clusters = cluster_elements_by_grid(elements, bucket_size=0.05)
    assert len(clusters) == 2
    cluster_sizes = sorted(len(cluster) for cluster in clusters)
    assert cluster_sizes == [1, 2]


def test_build_auto_regions_creates_searchable_regions(db_session, project) -> None:
    seed(db_session, project_id=None)
    project_id = cast(int, project.id)

    storage = StorageService(db_session)
    drawing = storage.create_drawing(
        project_id=project_id,
        source="upload",
        name="Master.pdf",
        storage_key="projects/2/drawings/master.pdf",
        content_type="application/pdf",
    )
    drawing_id = cast(int, drawing.id)

    ss = _element(text="SS", x0=0.10, y0=0.10, x1=0.12, y1=0.12)
    sewer = _element(text="SANITARY", x0=0.105, y0=0.105, x1=0.115, y1=0.115)
    sewer2 = _element(text="SEWER", x0=0.108, y0=0.108, x1=0.112, y1=0.112)
    for row in (ss, sewer, sewer2):
        row.master_drawing_id = drawing_id
        enrich_text_element(db_session, row, project_id=project_id)
    db_session.add_all([ss, sewer, sewer2])
    db_session.commit()

    created = build_auto_regions_from_text_elements(db_session, drawing_id)
    db_session.commit()

    assert created == 1
    region = (
        db_session.query(DrawingRegion)
        .filter(DrawingRegion.master_drawing_id == drawing_id)
        .one()
    )
    assert region.label == "SANITARY SEWER"
    assert region.geometry["meta"]["source"] == AUTO_INDEX_REGION_SOURCE
    assert "SS" in region.location_tags
    assert "SANITARY SEWER" in region.location_tags
    assert region.inspection_type_tags == ["33-Sanitary Sewerage"]

    master = db_session.get(Drawing, drawing_id)
    assert master is not None


def test_fixed_grid_mode_creates_one_region_per_occupied_cell(db_session, project) -> None:
    project_id = cast(int, project.id)
    storage = StorageService(db_session)
    drawing = storage.create_drawing(
        project_id=project_id,
        source="upload",
        name="Master.pdf",
        storage_key="projects/2/drawings/master.pdf",
        content_type="application/pdf",
    )
    drawing_id = cast(int, drawing.id)

    isolated = _element(text="COLO", x0=0.05, y0=0.05, x1=0.06, y1=0.06)
    distant = _element(text="MLK", x0=0.85, y0=0.85, x1=0.86, y1=0.86)
    for row in (isolated, distant):
        row.master_drawing_id = drawing_id
    db_session.add_all([isolated, distant])
    db_session.commit()

    with patch("ai.pipelines.master_drawing_region_builder.settings") as mock_settings:
        mock_settings.drawing_index_auto_region_mode = "grid"
        created = build_auto_regions_from_text_elements(db_session, drawing_id)
    db_session.commit()

    regions = (
        db_session.query(DrawingRegion)
        .filter(DrawingRegion.master_drawing_id == drawing_id)
        .order_by(DrawingRegion.label.asc())
        .all()
    )
    assert created == 2
    assert all(region.geometry["meta"]["source"] == AUTO_INDEX_REGION_SOURCE for region in regions)
    assert all("grid" in region.geometry["meta"] for region in regions)


def test_hybrid_mode_creates_title_legend_and_body_regions(db_session, project) -> None:
    seed(db_session, project_id=None)
    project_id = cast(int, project.id)
    storage = StorageService(db_session)
    drawing = storage.create_drawing(
        project_id=project_id,
        source="upload",
        name="Master.pdf",
        storage_key="projects/2/drawings/master.pdf",
        content_type="application/pdf",
    )
    drawing_id = cast(int, drawing.id)

    title = _element(text="SHEET", x0=0.80, y0=0.80, x1=0.82, y1=0.82)
    scale = _element(text='1"=10\'', x0=0.82, y0=0.82, x1=0.86, y1=0.84)
    legend = _element(text="LEGEND", x0=0.05, y0=0.30, x1=0.08, y1=0.32)
    ss = _element(text="SS", x0=0.10, y0=0.30, x1=0.12, y1=0.32)
    ssmh = _element(text="SSMH", x0=0.12, y0=0.31, x1=0.15, y1=0.33)
    body_a = _element(text="COLO", x0=0.40, y0=0.40, x1=0.43, y1=0.42)
    body_b = _element(text="MLK", x0=0.41, y0=0.41, x1=0.44, y1=0.43)

    for row in (title, scale, legend, ss, ssmh, body_a, body_b):
        row.master_drawing_id = drawing_id
        enrich_text_element(db_session, row, project_id=project_id)
    db_session.add_all([title, scale, legend, ss, ssmh, body_a, body_b])
    db_session.commit()

    with patch("ai.pipelines.master_drawing_region_builder.settings") as mock_settings:
        mock_settings.drawing_index_auto_region_mode = "hybrid"
        mock_settings.drawing_index_min_cluster_words = 2
        created = build_auto_regions_from_text_elements(db_session, drawing_id)
    db_session.commit()

    regions = (
        db_session.query(DrawingRegion)
        .filter(DrawingRegion.master_drawing_id == drawing_id)
        .order_by(DrawingRegion.label.asc())
        .all()
    )
    labels = {region.label for region in regions}
    zones = {
        region.geometry.get("meta", {}).get("zone")
        for region in regions
        if isinstance(region.geometry, dict)
    }

    assert created >= 3
    assert "Title block" in labels
    assert "Legend" in labels
    assert {"title_block", "legend_block"} <= zones
    assert any(region.label not in {"Title block", "Legend"} for region in regions)


def test_cluster_elements_by_fixed_grid_uses_full_cell_keys() -> None:
    elements = [
        IndexedElement(
            row=_element(text="A", x0=0.01, y0=0.01, x1=0.02, y1=0.02),
            x0=0.01,
            y0=0.01,
            x1=0.02,
            y1=0.02,
            centroid_x=0.015,
            centroid_y=0.015,
        ),
        IndexedElement(
            row=_element(text="B", x0=0.90, y0=0.90, x1=0.91, y1=0.91),
            x0=0.90,
            y0=0.90,
            x1=0.91,
            y1=0.91,
            centroid_x=0.905,
            centroid_y=0.905,
        ),
    ]
    grouped = cluster_elements_by_fixed_grid(elements, divisions=12)
    assert len(grouped) == 2
    assert grouped[0][0].column != grouped[1][0].column
