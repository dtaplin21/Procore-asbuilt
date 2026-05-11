"""Tests for per-crop semantic delta helper."""

import numpy as np
import pytest

pytest.importorskip("numpy")

from ai.pipelines.diff_semantics import compare_cropped_regions_semantics


def test_identical_crops_minimal_or_low_signal():
    h, w = 64, 64
    m = np.full((h, w), 200, dtype=np.uint8)
    out = compare_cropped_regions_semantics(m, m.copy())
    assert out["change_type"] == "minimal_difference"
    assert out["severity"] == "low"
    assert "description" in out and out["description"]


def test_darker_sub_patch_added_annotation():
    h, w = 80, 80
    m = np.full((h, w), 250, dtype=np.uint8)
    s = m.copy()
    s[10:70, 10:70] = 40
    out = compare_cropped_regions_semantics(m, s)
    assert out["change_type"] == "added_annotation"
    assert out["severity"] in ("medium", "high", "critical")
    assert "sub drawing" in out["description"].lower()


def test_mismatched_shape_raises():
    m = np.zeros((10, 10), dtype=np.uint8)
    s = np.zeros((12, 10), dtype=np.uint8)
    with pytest.raises(ValueError, match="shape"):
        compare_cropped_regions_semantics(m, s)
