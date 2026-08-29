"""Tests for OCR viewport proposals (PR-V V-5)."""

from __future__ import annotations

from dataclasses import dataclass

from ai.pipelines.sheet_entity_graph import DrawingViewport, ViewportScale
from ai.pipelines.viewport_detector import (
    filter_safe_ocr_commits,
    propose_viewports_from_tokens,
)


@dataclass(frozen=True)
class _Tok:
    text: str
    bbox_json: dict[str, float]


def test_propose_viewports_finds_plan_and_section_with_scales() -> None:
    tokens = [
        _Tok("PLAN", {"x0": 0.10, "y0": 0.08, "x1": 0.18, "y1": 0.12}),
        _Tok('1"=20\'', {"x0": 0.20, "y0": 0.08, "x1": 0.28, "y1": 0.11}),
        _Tok("SECTION", {"x0": 0.70, "y0": 0.10, "x1": 0.80, "y1": 0.14}),
        _Tok('1"=4\'', {"x0": 0.70, "y0": 0.15, "x1": 0.78, "y1": 0.18}),
    ]
    proposals = propose_viewports_from_tokens(tokens, page=1)
    kinds = {p.kind for p in proposals}
    assert "plan" in kinds
    assert "section" in kinds
    by_kind = {p.kind: p for p in proposals}
    assert by_kind["plan"].source == "ocr"
    assert by_kind["plan"].scale is not None
    assert by_kind["plan"].scale.real_feet_per_paper_inch == 20.0
    assert by_kind["section"].scale is not None
    assert by_kind["section"].scale.real_feet_per_paper_inch == 4.0


def test_filter_rejects_overlapping_plan_section_same_scale() -> None:
    plan = DrawingViewport(
        viewport_id="plan",
        kind="plan",
        page=1,
        bbox_fractional=(0.0, 0.0, 1.0, 1.0),
        scale=ViewportScale(raw_text='1"=10\'', real_feet_per_paper_inch=10.0, confidence=0.9),
        source="ocr",
    )
    section = DrawingViewport(
        viewport_id="section",
        kind="section",
        page=1,
        bbox_fractional=(0.1, 0.1, 0.4, 0.4),
        scale=ViewportScale(raw_text='1"=10\'', real_feet_per_paper_inch=10.0, confidence=0.5),
        source="ocr",
    )
    kept = filter_safe_ocr_commits([plan, section])
    assert len(kept) == 1
    assert kept[0].viewport_id == "plan"


def test_noise_tokens_ignored() -> None:
    tokens = [
        _Tok("Planning", {"x0": 0.90, "y0": 0.24, "x1": 0.92, "y1": 0.25}),
        _Tok("PROFILE.dwg", {"x0": 0.20, "y0": 0.98, "x1": 0.30, "y1": 0.99}),
        _Tok(r"\4_engineering\2_plan", {"x0": 0.05, "y0": 0.98, "x1": 0.15, "y1": 0.99}),
    ]
    assert propose_viewports_from_tokens(tokens, page=1) == []
