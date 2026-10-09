"""Viewport scale promotion to drawing-level scale_json."""

from __future__ import annotations

from ai.pipelines.viewport_scale_promotion import promote_scale

_SHEET_1722 = {
    "1": {
        "viewports": [
            {
                "viewport_id": "detail",
                "kind": "detail",
                "bbox_fractional": [0.09, 0.04, 0.34, 0.32],
                "scale": None,
            },
            {
                "viewport_id": "plan",
                "kind": "plan",
                "bbox_fractional": [0.03, 0.03, 0.82, 0.45],
                "scale": {
                    "raw_text": "1 INCH = 40'",
                    "real_feet_per_paper_inch": 40.0,
                    "confidence": 0.9,
                    "horizontal": {"numerator": 1.0, "denominator": 40.0, "units": "in=ft"},
                    "vertical": {"numerator": 1.0, "denominator": 40.0, "units": "in=ft"},
                },
            },
            {
                "viewport_id": "section",
                "kind": "section",
                "bbox_fractional": [0.40, 0.83, 0.65, 1.0],
                "scale": None,
            },
        ]
    }
}


def test_single_confident_plan_viewport_promotes() -> None:
    result = promote_scale(_SHEET_1722, existing_drawing_scale_json=None)
    assert result.promoted is True
    assert result.scale_found is True
    assert result.scale_json is not None
    assert result.scale_json["real_feet_per_paper_inch"] == 40.0
    assert result.scale_json["source"] == "viewport_promotion"
    assert result.source_viewport_id == "plan"
    assert result.ambiguous is False


def test_existing_drawing_scale_not_overwritten() -> None:
    existing = {"real_feet_per_paper_inch": 20.0, "raw_text": '1"=20\'', "confidence": 1.0}
    result = promote_scale(_SHEET_1722, existing_drawing_scale_json=existing)
    assert result.promoted is False
    assert result.scale_json == existing
    assert result.scale_found is True


def test_no_viewport_scales_no_promotion() -> None:
    empty_graph = {
        "1": {
            "viewports": [
                {
                    "viewport_id": "detail",
                    "kind": "detail",
                    "bbox_fractional": [0, 0, 1, 1],
                    "scale": None,
                },
            ]
        }
    }
    result = promote_scale(empty_graph, existing_drawing_scale_json=None)
    assert result.promoted is False
    assert result.scale_found is False
    assert result.scale_json is None
    assert result.ambiguous is False


def test_conflicting_scales_refuse_silent_promotion() -> None:
    conflicting = {
        "1": {
            "viewports": [
                {
                    "viewport_id": "plan_a",
                    "kind": "plan",
                    "bbox_fractional": [0.0, 0.0, 0.5, 0.5],
                    "scale": {
                        "raw_text": '1"=40\'',
                        "real_feet_per_paper_inch": 40.0,
                        "confidence": 0.85,
                    },
                },
                {
                    "viewport_id": "plan_b",
                    "kind": "plan",
                    "bbox_fractional": [0.5, 0.5, 1.0, 1.0],
                    "scale": {
                        "raw_text": '1"=20\'',
                        "real_feet_per_paper_inch": 20.0,
                        "confidence": 0.80,
                    },
                },
            ]
        }
    }
    result = promote_scale(conflicting, existing_drawing_scale_json=None)
    assert result.promoted is False
    assert result.scale_found is False
    assert result.ambiguous is True
    assert len(result.candidates) == 2


def test_ineligible_conflicting_scale_does_not_block_plan_promotion() -> None:
    """Section scale below confidence threshold must not force ambiguity."""
    graph = {
        "1": {
            "viewports": [
                {
                    "viewport_id": "plan",
                    "kind": "plan",
                    "bbox_fractional": [0.0, 0.0, 1.0, 0.55],
                    "scale": {
                        "raw_text": '1"=40\'',
                        "real_feet_per_paper_inch": 40.0,
                        "confidence": 0.9,
                    },
                },
                {
                    "viewport_id": "section_a",
                    "kind": "section",
                    "bbox_fractional": [0.0, 0.6, 1.0, 1.0],
                    "scale": {
                        "raw_text": '1"=4\'',
                        "real_feet_per_paper_inch": 4.0,
                        "confidence": 0.4,
                    },
                },
            ]
        }
    }
    result = promote_scale(graph, existing_drawing_scale_json=None)
    assert result.promoted is True
    assert result.ambiguous is False
    assert result.scale_json is not None
    assert result.scale_json["real_feet_per_paper_inch"] == 40.0


def test_scale_bar_vetoes_wrong_viewport_scale() -> None:
    wrong_plan = {
        "1": {
            "viewports": [
                {
                    "viewport_id": "plan",
                    "kind": "plan",
                    "bbox_fractional": [0.03, 0.03, 0.82, 0.45],
                    "scale": {
                        "raw_text": "1 INCH = 40'",
                        "real_feet_per_paper_inch": 40.0,
                        "confidence": 0.9,
                    },
                },
            ]
        }
    }
    vetoed = promote_scale(wrong_plan, None, scale_bar_feet_per_paper_inch=20.0)
    assert vetoed.promoted is False
    assert vetoed.ambiguous is True
    assert vetoed.scale_found is False

    right_plan = {
        "1": {
            "viewports": [
                {
                    "viewport_id": "plan",
                    "kind": "plan",
                    "bbox_fractional": [0.03, 0.03, 0.82, 0.45],
                    "scale": {
                        "raw_text": "1 INCH = 20 FT",
                        "real_feet_per_paper_inch": 20.0,
                        "confidence": 0.9,
                    },
                },
            ]
        }
    }
    ok = promote_scale(right_plan, None, scale_bar_feet_per_paper_inch=20.0)
    assert ok.promoted is True
    assert ok.scale_json is not None
    assert ok.scale_json["real_feet_per_paper_inch"] == 20.0
