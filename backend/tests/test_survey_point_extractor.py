"""Tests for survey point extraction from OCR tokens."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from ai.pipelines.survey_point_extractor import (
    extract_survey_points_from_elements,
    resolve_pairing_scale,
)


@dataclass
class _FakeElement:
    page: int
    text: str
    bbox_json: dict[str, float]
    ocr_confidence: float = 0.95


ARCH_PAGE_META = [
    {
        "page": 1,
        "width_pt": 2592.0,  # 36 in
        "height_pt": 1728.0,  # 24 in
        "rotation": 0,
    }
]

SCALE_1_IN_10_FT = {
    "raw_text": '1" = 10\'',
    "paper_inches_per_real_foot": 0.1,
    "real_feet_per_paper_inch": 10.0,
    "confidence": 0.9,
    "page": 1,
}


def test_survey_point_extractor_pairs_n_e_at_one_inch_equals_ten_feet() -> None:
    elements = [
        _FakeElement(1, "N 2131764.84", {"x0": 0.10, "y0": 0.20, "x1": 0.14, "y1": 0.22}),
        _FakeElement(1, "E 6051541.82", {"x0": 0.12, "y0": 0.20, "x1": 0.16, "y1": 0.22}),
    ]

    points = extract_survey_points_from_elements(
        elements,
        scale_json=SCALE_1_IN_10_FT,
        page_meta_json=ARCH_PAGE_META,
    )

    assert len(points) == 1
    point = points[0]
    assert point.northing == pytest.approx(2131764.84)
    assert point.easting == pytest.approx(6051541.82)
    assert point.meta_json["pairing_scale_mode"] == "physical"
    assert point.meta_json["pairing_distance_ft"] <= 15.0


def test_survey_point_extractor_rejects_distant_e() -> None:
    elements = [
        _FakeElement(1, "N 2131764.84", {"x0": 0.10, "y0": 0.20, "x1": 0.14, "y1": 0.22}),
        _FakeElement(1, "E 6051541.82", {"x0": 0.60, "y0": 0.20, "x1": 0.64, "y1": 0.22}),
    ]

    points = extract_survey_points_from_elements(
        elements,
        scale_json=SCALE_1_IN_10_FT,
        page_meta_json=ARCH_PAGE_META,
    )

    assert points == []


def test_survey_point_extractor_campus_default_without_scale_json() -> None:
    elements = [
        _FakeElement(1, "N 2131764.84", {"x0": 0.10, "y0": 0.20, "x1": 0.14, "y1": 0.22}),
        _FakeElement(1, "E 6051541.82", {"x0": 0.12, "y0": 0.20, "x1": 0.16, "y1": 0.22}),
    ]

    points = extract_survey_points_from_elements(
        elements,
        scale_json=None,
        page_meta_json=ARCH_PAGE_META,
    )

    assert len(points) == 1
    ctx = resolve_pairing_scale(
        scale_json=None,
        page_meta=ARCH_PAGE_META[0],
        scale_source="evidence_extract",
    )
    assert ctx.scale_source == "campus_default"
    assert points[0].meta_json["pairing_scale_source"] == "campus_default"
    assert points[0].meta_json["scale_fallback"] is True


def test_survey_point_extractor_normalized_fallback_without_page_dims() -> None:
    elements = [
        _FakeElement(1, "N 2131764.84", {"x0": 0.10, "y0": 0.20, "x1": 0.14, "y1": 0.22}),
        _FakeElement(1, "E 6051541.82", {"x0": 0.12, "y0": 0.20, "x1": 0.16, "y1": 0.22}),
    ]

    points = extract_survey_points_from_elements(
        elements,
        scale_json=None,
        page_meta_json=[{"page": 1}],
    )

    assert len(points) == 1
    assert points[0].meta_json["pairing_scale_mode"] == "normalized_fallback"
    assert points[0].meta_json["scale_fallback"] is True
