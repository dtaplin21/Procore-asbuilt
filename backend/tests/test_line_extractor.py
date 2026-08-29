"""Tests for deterministic OpenCV line extraction (PR-L L-1)."""

from __future__ import annotations

from pathlib import Path

import cv2  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]

from ai.pipelines.landmark_extractor import TITLE_BLOCK_X_MIN, TITLE_BLOCK_Y_MIN
from ai.pipelines.line_extractor import extract_line_polylines
from ai.pipelines.sheet_entity_graph import DrawingViewport, ViewportScale


def _synthetic_diagonal(path: Path, *, width: int = 800, height: int = 600) -> None:
    image = np.full((height, width), 255, dtype=np.uint8)
    # Thick black diagonal toward bottom-right (away from titleblock corner).
    cv2.line(image, (50, 50), (750, 550), 0, 8)
    cv2.imwrite(str(path), image)


def test_extract_line_polylines_finds_synthetic_diagonal(tmp_path: Path) -> None:
    png = tmp_path / "diagonal.png"
    _synthetic_diagonal(png)

    lines = extract_line_polylines(png, max_lines=50)
    assert len(lines) >= 1

    expected_a = (50 / 800, 50 / 600)
    expected_b = (750 / 800, 550 / 600)

    def _near(p: tuple[float, float], q: tuple[float, float], tol: float = 0.05) -> bool:
        return abs(p[0] - q[0]) <= tol and abs(p[1] - q[1]) <= tol

    matched = False
    for line in lines:
        assert len(line.points) >= 2
        start, end = line.points[0], line.points[-1]
        if (_near(start, expected_a) and _near(end, expected_b)) or (
            _near(start, expected_b) and _near(end, expected_a)
        ):
            matched = True
            assert line.viewport_id is None
            break
    assert matched, f"no polyline near diagonal corners; got {[ln.points for ln in lines]}"


def test_extract_line_polylines_attaches_viewport_and_maps_full_page(
    tmp_path: Path,
) -> None:
    png = tmp_path / "diagonal.png"
    _synthetic_diagonal(png)
    viewport = DrawingViewport(
        viewport_id="plan",
        kind="plan",
        page=1,
        bbox_fractional=(0.0, 0.0, 1.0, 1.0),
        scale=ViewportScale(raw_text='1"=10\'', real_feet_per_paper_inch=10.0, confidence=0.9),
        source="manual",
    )
    lines = extract_line_polylines(png, viewport=viewport, max_lines=20)
    assert lines
    assert all(line.viewport_id == "plan" for line in lines)
    # Fractional coords must be page-relative (within [0,1]).
    for line in lines:
        for x, y in line.points:
            assert 0.0 <= x <= 1.0
            assert 0.0 <= y <= 1.0


def test_extract_line_polylines_skips_titleblock_only_line(tmp_path: Path) -> None:
    png = tmp_path / "titleblock.png"
    image = np.full((600, 800), 255, dtype=np.uint8)
    # Line entirely inside titleblock zone (x>=0.75, y>=0.75).
    x0 = int(TITLE_BLOCK_X_MIN * 800) + 10
    y0 = int(TITLE_BLOCK_Y_MIN * 600) + 10
    cv2.line(image, (x0, y0), (790, 590), 0, 6)
    cv2.imwrite(str(png), image)

    lines = extract_line_polylines(png, max_lines=50)
    for line in lines:
        mx = sum(p[0] for p in line.points) / len(line.points)
        my = sum(p[1] for p in line.points) / len(line.points)
        assert not (mx >= TITLE_BLOCK_X_MIN and my >= TITLE_BLOCK_Y_MIN)
