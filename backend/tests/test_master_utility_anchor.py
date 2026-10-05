"""Tests for master utility corridor anchor fallback."""

from __future__ import annotations

from dataclasses import dataclass

from ai.pipelines.master_utility_anchor import utility_corridor_anchor_from_text_elements


@dataclass
class _El:
    page: int
    text: str
    bbox_json: dict[str, float]


def test_utility_corridor_anchor_clusters_highway_and_sanitary() -> None:
    elements = [
        _El(1, "HIGHWAY", {"x0": 0.35, "y0": 0.40, "x1": 0.42, "y1": 0.42}),
        _El(1, "SANITARY", {"x0": 0.50, "y0": 0.41, "x1": 0.58, "y1": 0.43}),
        _El(1, "STATE", {"x0": 0.60, "y0": 0.05, "x1": 0.65, "y1": 0.07}),
    ]
    bbox = utility_corridor_anchor_from_text_elements(elements)
    assert bbox is not None
    x0, y0, x1, y1 = bbox
    assert x0 < 0.35
    assert x1 > 0.58
    assert y0 < 0.40
    assert y1 > 0.43
