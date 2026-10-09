"""Service-layer viewport scale promotion (stale scale + page resolution)."""

from __future__ import annotations

from services.drawing_scale_promotion import existing_scale_json_for_promotion


def test_stale_viewport_promotion_cleared_when_source_missing() -> None:
    pages = {
        "1": {
            "viewports": [
                {"viewport_id": "plan", "kind": "plan", "scale": {"real_feet_per_paper_inch": 40.0}},
            ]
        }
    }
    existing = {
        "source": "viewport_promotion",
        "source_viewport_id": "profile",
        "real_feet_per_paper_inch": 40.0,
    }
    assert existing_scale_json_for_promotion(existing, pages=pages) is None


def test_valid_viewport_promotion_kept() -> None:
    pages = {
        "1": {
            "viewports": [
                {"viewport_id": "plan", "kind": "plan", "scale": {"real_feet_per_paper_inch": 40.0}},
            ]
        }
    }
    existing = {
        "source": "viewport_promotion",
        "source_viewport_id": "plan",
        "real_feet_per_paper_inch": 40.0,
    }
    assert existing_scale_json_for_promotion(existing, pages=pages) == existing


def test_non_promotion_scale_never_cleared() -> None:
    pages = {"1": {"viewports": [{"viewport_id": "plan"}]}}
    existing = {"source": "titleblock", "real_feet_per_paper_inch": 20.0}
    assert existing_scale_json_for_promotion(existing, pages=pages) == existing
