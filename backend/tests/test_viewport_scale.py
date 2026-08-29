"""Tests for per-viewport scale conversion (PR-V V-4)."""

from __future__ import annotations

from typing import cast

import pytest

from ai.pipelines.sheet_entity_graph import DrawingViewport, ViewportScale
from ai.pipelines.viewport_scale import (
    fractional_delta_to_feet,
    load_viewports,
    scale_for_geometry,
    viewport_scale_from_json,
)
from models.drawing_viewport import DrawingViewport as DrawingViewportRow
from services.storage import StorageService


def _component(real_ft: float) -> dict[str, float | str]:
    return {"numerator": 1.0, "denominator": real_ft, "units": "in=ft"}


def _viewport(
    viewport_id: str,
    bbox: tuple[float, float, float, float],
    *,
    kind: str,
    scale_ft: float,
) -> DrawingViewport:
    return DrawingViewport(
        viewport_id=viewport_id,
        kind=kind,  # type: ignore[arg-type]
        page=1,
        bbox_fractional=bbox,
        scale=ViewportScale(
            raw_text=f'1"={scale_ft:.0f}\'',
            real_feet_per_paper_inch=scale_ft,
            confidence=0.9,
            horizontal=_component(scale_ft),
            vertical=_component(scale_ft),
        ),
        source="manual",
    )


def test_scale_for_geometry_plan_vs_section_multiscale() -> None:
    plan = _viewport("plan", (0.0, 0.0, 1.0, 0.8), kind="plan", scale_ft=20.0)
    section = _viewport("section_a", (0.05, 0.05, 0.35, 0.40), kind="section", scale_ft=4.0)
    viewports = (plan, section)

    # Inside section inset → section scale (smaller bbox wins).
    section_scale = scale_for_geometry(viewports, point=(0.15, 0.15))
    assert section_scale is not None
    assert section_scale.real_feet_per_paper_inch == pytest.approx(4.0)

    # Outside section, inside plan → plan scale.
    plan_scale = scale_for_geometry(viewports, point=(0.70, 0.50))
    assert plan_scale is not None
    assert plan_scale.real_feet_per_paper_inch == pytest.approx(20.0)

    # Same fractional length → different feet (20/4 == 5).
    page_w, page_h = 36.0, 24.0
    delta = 0.01
    feet_plan = fractional_delta_to_feet(
        delta, axis="x", scale=plan_scale, page_width_in=page_w, page_height_in=page_h
    )
    feet_section = fractional_delta_to_feet(
        delta, axis="x", scale=section_scale, page_width_in=page_w, page_height_in=page_h
    )
    assert feet_plan == pytest.approx(delta * page_w * 20.0)
    assert feet_section == pytest.approx(delta * page_w * 4.0)
    assert feet_plan / feet_section == pytest.approx(5.0)


def test_scale_for_geometry_returns_none_outside_all_viewports() -> None:
    plan = _viewport("plan", (0.0, 0.0, 0.5, 0.5), kind="plan", scale_ft=20.0)
    assert scale_for_geometry((plan,), point=(0.9, 0.9)) is None
    assert scale_for_geometry((plan,), bbox=(0.8, 0.8, 0.95, 0.95)) is None
    # No silent global fallback even with empty viewport list.
    assert scale_for_geometry((), point=(0.1, 0.1)) is None


def test_scale_for_geometry_rejects_both_point_and_bbox() -> None:
    plan = _viewport("plan", (0.0, 0.0, 1.0, 1.0), kind="plan", scale_ft=20.0)
    with pytest.raises(ValueError, match="only one"):
        scale_for_geometry((plan,), point=(0.1, 0.1), bbox=(0.0, 0.0, 0.2, 0.2))


def test_viewport_scale_from_json_and_load_viewports(db_session, project) -> None:
    storage = StorageService(db_session)
    drawing = storage.create_drawing(
        project_id=cast(int, project.id),
        source="upload",
        name="MultiScale.pdf",
        storage_key="projects/2/drawings/multiscale.pdf",
        content_type="application/pdf",
    )
    drawing_id = cast(int, drawing.id)

    db_session.add(
        DrawingViewportRow(
            drawing_id=drawing_id,
            page=1,
            viewport_id="plan",
            kind="plan",
            bbox_json={"x0": 0.0, "y0": 0.0, "x1": 1.0, "y1": 0.7},
            scale_json={
                "raw_text": '1"=20\'',
                "real_feet_per_paper_inch": 20.0,
                "confidence": 0.9,
                "horizontal": _component(20.0),
                "vertical": _component(20.0),
            },
            source="manual",
        )
    )
    db_session.commit()

    loaded = load_viewports(db_session, drawing_id, page=1)
    assert len(loaded) == 1
    assert loaded[0].viewport_id == "plan"
    assert loaded[0].scale is not None
    assert loaded[0].scale.real_feet_per_paper_inch == pytest.approx(20.0)

    assert viewport_scale_from_json(None) is None
    assert viewport_scale_from_json({"real_feet_per_paper_inch": 0}) is None
