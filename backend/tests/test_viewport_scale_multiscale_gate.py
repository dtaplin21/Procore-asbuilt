"""Regression gate: multi-scale sheets must not share one global feet scale (PR-E E-1)."""

from __future__ import annotations

import pytest

from ai.pipelines.sheet_entity_graph import DrawingViewport, ViewportScale
from ai.pipelines.viewport_scale import fractional_delta_to_feet, scale_for_geometry


def _component(real_ft: float) -> dict[str, float | str]:
    return {"numerator": 1.0, "denominator": real_ft, "units": "in=ft"}


def _fixture_viewports() -> tuple[DrawingViewport, DrawingViewport]:
    """Plan at 20 ft/in and section at 4 ft/in on the same page."""
    plan = DrawingViewport(
        viewport_id="plan",
        kind="plan",
        page=1,
        bbox_fractional=(0.0, 0.0, 1.0, 0.55),
        scale=ViewportScale(
            raw_text='1"=20\'',
            real_feet_per_paper_inch=20.0,
            confidence=0.95,
            horizontal=_component(20.0),
            vertical=_component(20.0),
        ),
        source="manual",
    )
    section = DrawingViewport(
        viewport_id="section_a",
        kind="section",
        page=1,
        bbox_fractional=(0.05, 0.60, 0.95, 0.95),
        scale=ViewportScale(
            raw_text='1"=4\'',
            real_feet_per_paper_inch=4.0,
            confidence=0.95,
            horizontal=_component(4.0),
            vertical=_component(4.0),
        ),
        source="manual",
    )
    return plan, section


def test_identical_fractional_segment_yields_five_to_one_feet_ratio() -> None:
    """Same fractional length → feet_plan / feet_section == 20/4 == 5.

    Fails if conversion silently uses one sheet-global scale for both viewports.
    """
    plan, section = _fixture_viewports()
    viewports = (plan, section)

    plan_scale = scale_for_geometry(viewports, point=(0.50, 0.25))
    section_scale = scale_for_geometry(viewports, point=(0.50, 0.75))
    assert plan_scale is not None
    assert section_scale is not None
    assert plan_scale.real_feet_per_paper_inch == pytest.approx(20.0)
    assert section_scale.real_feet_per_paper_inch == pytest.approx(4.0)
    assert plan_scale.real_feet_per_paper_inch != section_scale.real_feet_per_paper_inch

    page_w, page_h = 36.0, 24.0
    delta_frac = 0.02  # identical fractional segment length
    feet_plan = fractional_delta_to_feet(
        delta_frac,
        axis="x",
        scale=plan_scale,
        page_width_in=page_w,
        page_height_in=page_h,
    )
    feet_section = fractional_delta_to_feet(
        delta_frac,
        axis="x",
        scale=section_scale,
        page_width_in=page_w,
        page_height_in=page_h,
    )

    assert feet_plan == pytest.approx(delta_frac * page_w * 20.0)
    assert feet_section == pytest.approx(delta_frac * page_w * 4.0)
    assert feet_plan / feet_section == pytest.approx(5.0)

    # Explicit anti-regression: a single global scale would make the ratio 1.
    assert feet_plan != pytest.approx(feet_section)


def test_multiscale_gate_y_axis_also_diverges() -> None:
    plan, section = _fixture_viewports()
    plan_scale = scale_for_geometry((plan, section), point=(0.40, 0.20))
    section_scale = scale_for_geometry((plan, section), point=(0.40, 0.80))
    assert plan_scale is not None and section_scale is not None

    page_w, page_h = 36.0, 24.0
    delta = 0.05
    feet_plan = fractional_delta_to_feet(
        delta, axis="y", scale=plan_scale, page_width_in=page_w, page_height_in=page_h
    )
    feet_section = fractional_delta_to_feet(
        delta, axis="y", scale=section_scale, page_width_in=page_w, page_height_in=page_h
    )
    assert feet_plan / feet_section == pytest.approx(5.0)
