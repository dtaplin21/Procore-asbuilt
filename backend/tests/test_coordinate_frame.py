"""Tests for normalized coordinate rotation helpers."""

from __future__ import annotations

import pytest

from ai.pipelines.coordinate_frame import rotate_bbox, rotate_point


def test_rotate_point_180_deg_flips_around_center() -> None:
    x, y = rotate_point(0.1, 0.2, 180.0)
    assert x == pytest.approx(0.9)
    assert y == pytest.approx(0.8)


def test_rotate_bbox_180_deg_swaps_y_extent() -> None:
    x0, y0, x1, y1 = rotate_bbox((0.1, 0.1, 0.2, 0.2), 180.0)
    assert x0 == pytest.approx(0.8)
    assert y0 == pytest.approx(0.8)
    assert x1 == pytest.approx(0.9)
    assert y1 == pytest.approx(0.9)
