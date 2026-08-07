"""Shared overlay geometry constants."""

from __future__ import annotations

from typing import Any

# Unknown/unmapped geometry: full-page rect (normalized 0-1)
UNMAPPED_GEOMETRY: dict[str, Any] = {
    "page": 1,
    "type": "rect",
    "x": 0.0,
    "y": 0.0,
    "width": 1.0,
    "height": 1.0,
    "label": "unmapped",
}
