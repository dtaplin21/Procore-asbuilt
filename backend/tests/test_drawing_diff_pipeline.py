"""P1.7 — drawing diff raster detection (blur, absdiff, Otsu, contours)."""

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from ai.pipelines.drawing_diff import _generate_and_score_diff


def test_identical_rasters_yield_no_regions():
    h, w = 120, 160
    master = np.full((h, w), 200, dtype=np.uint8)
    warped = master.copy()
    out = _generate_and_score_diff(master, warped, page=1)
    assert out == []


def test_synthetic_rectangle_change_has_at_least_one_region():
    h, w = 220, 320
    master = np.full((h, w), 240, dtype=np.uint8)
    warped = master.copy()
    # Strong contrast vs background; area 80×100 = 8000 > _DIFF_MIN_REGION_AREA_PX
    warped[70:150, 110:210] = 25

    out = _generate_and_score_diff(master, warped, page=3)
    assert len(out) == 1
    item = out[0]
    assert (item.get("summary") or "").strip()
    regions = item.get("diff_regions") or []
    assert len(regions) >= 1
    for r in regions:
        assert r.get("page") == 3
        bbox = r.get("bbox") or {}
        assert {"x", "y", "width", "height"} <= set(bbox.keys())
        assert bbox["width"] > 0 and bbox["height"] > 0

    sem = item.get("semantic_summary")
    assert isinstance(sem, dict)
    assert sem.get("scope") == "sheet"
    assert sem.get("page") == 3
    assert sem.get("region_count") == len(regions)
    assert sem.get("change_type")
    assert sem.get("description")
    assert sem.get("severity") in ("low", "medium", "high", "critical")
