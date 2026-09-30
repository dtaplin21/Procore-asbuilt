"""Legend manifest loading (array root, page_fractional_bbox alias)."""

from __future__ import annotations

import json
from pathlib import Path

from ai.pipelines.legend_grounding import (
    load_legend_manifest_entries,
    load_legend_manifest_file,
    load_legend_manifest_raw_entries,
)

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "legend_manifest_u2_c4_00_golden.json"


def test_load_raw_entries_from_bare_array() -> None:
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    rows = load_legend_manifest_raw_entries(data)
    assert len(rows) == 9
    assert rows[0]["label_text"] == "PROPERTY LINE"


def test_load_raw_entries_from_wrapped_object() -> None:
    data = {"rows": [{"label_text": "A", "icon_crop_path": "a.png", "page_fractional_bbox": [0, 0, 1, 1]}]}
    rows = load_legend_manifest_raw_entries(data)
    assert len(rows) == 1


def test_golden_manifest_parses_to_legend_icon_entries() -> None:
    entries = load_legend_manifest_file(_FIXTURE)
    assert len(entries) == 9
    assert entries[0].label_text == "PROPERTY LINE"
    assert entries[0].icon_fractional_bbox[0] == 0.7
    assert entries[8].row_id == 8


def test_page_fractional_bbox_maps_to_icon_exclude_region() -> None:
    entries = load_legend_manifest_entries(
        json.loads(_FIXTURE.read_text(encoding="utf-8")),
    )
    assert entries[2].label_text == "UTILITY LINE"
    x0, _y0, x1, _y1 = entries[2].icon_fractional_bbox
    assert x0 == 0.7
    assert abs(x1 - 0.7846280991735537) < 1e-9
