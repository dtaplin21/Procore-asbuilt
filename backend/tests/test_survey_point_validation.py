"""Tests for survey point bbox placement validation."""

from __future__ import annotations

from ai.pipelines.survey_point_extractor import is_placed_survey_label_bbox


def test_placed_bbox_accepts_auto_index_pairing() -> None:
    bbox = {"x0": 0.518, "y0": 0.472, "x1": 0.566, "y1": 0.514}
    assert is_placed_survey_label_bbox(bbox, source="auto_index") is True


def test_placed_bbox_accepts_match_investigation_source() -> None:
    bbox = {"x0": 0.518, "y0": 0.472, "x1": 0.566, "y1": 0.514}
    assert is_placed_survey_label_bbox(bbox, source="match_investigation") is True


def test_placed_bbox_rejects_baseline_seed_source() -> None:
    bbox = {"x0": 0.518, "y0": 0.472, "x1": 0.566, "y1": 0.514}
    assert is_placed_survey_label_bbox(bbox, source="pre2_baseline_seed") is False


def test_placed_bbox_rejects_plain_text_fallback_placeholder() -> None:
    bbox = {"x0": 0.0, "y0": 0.0, "x1": 0.01, "y1": 0.01}
    meta = {"plain_text_fallback": True}
    assert is_placed_survey_label_bbox(bbox, source="lazy_match", meta_json=meta) is False


def test_placed_bbox_rejects_tiny_area() -> None:
    bbox = {"x0": 0.5, "y0": 0.5, "x1": 0.5001, "y1": 0.5001}
    assert is_placed_survey_label_bbox(bbox, source="auto_index") is False
