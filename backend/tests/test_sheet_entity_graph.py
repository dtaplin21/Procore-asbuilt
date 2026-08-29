"""Tests for sheet entity graph viewport assignment (PR-V V-1)."""

from __future__ import annotations

from ai.pipelines.sheet_entity_graph import (
    DrawingViewport,
    ViewportScale,
    assign_viewport_id,
)


def _viewport(
    viewport_id: str,
    bbox: tuple[float, float, float, float],
    *,
    kind: str = "plan",
    scale_ft: float = 20.0,
) -> DrawingViewport:
    return DrawingViewport(
        viewport_id=viewport_id,
        kind=kind,  # type: ignore[arg-type]
        page=1,
        bbox_fractional=bbox,
        scale=ViewportScale(
            raw_text=f'1"= {scale_ft:.0f}\'',
            real_feet_per_paper_inch=scale_ft,
            confidence=0.9,
        ),
        source="manual",
    )


def test_assign_viewport_id_prefers_smallest_overlapping_bbox() -> None:
    plan = _viewport("plan", (0.0, 0.0, 1.0, 1.0), kind="plan", scale_ft=20.0)
    section = _viewport("section_a", (0.05, 0.05, 0.30, 0.35), kind="section", scale_ft=4.0)
    # Point inside both; section is smaller → must win (multi-scale hard rule).
    assert assign_viewport_id((0.15, 0.15), (plan, section)) == "section_a"
    assert assign_viewport_id((0.10, 0.10, 0.20, 0.20), (plan, section)) == "section_a"


def test_assign_viewport_id_returns_none_outside_all_viewports() -> None:
    section = _viewport("section_a", (0.05, 0.05, 0.30, 0.35), kind="section", scale_ft=4.0)
    assert assign_viewport_id((0.90, 0.90), (section,)) is None
    assert assign_viewport_id((0.90, 0.90), ()) is None


def test_assign_viewport_id_rejects_malformed_geometry() -> None:
    plan = _viewport("plan", (0.0, 0.0, 1.0, 1.0))
    assert assign_viewport_id((0.5,), (plan,)) is None
    assert assign_viewport_id((0.1, 0.2, 0.3), (plan,)) is None
