"""Tests for label↔symbol association (PR-A A-1)."""

from __future__ import annotations

from ai.pipelines.sheet_association import (
    associate_labels_to_symbols,
    normalize_symbol_class,
)
from ai.pipelines.sheet_entity_graph import SheetLabel, SheetSymbol
from scripts.seed_legend_reference import seed


def test_associate_nearest_label_above_symbol() -> None:
    symbol = SheetSymbol(
        symbol_class="ssmh",
        bbox_fractional=(0.40, 0.40, 0.44, 0.44),
        viewport_id="plan",
        confidence=0.9,
        detector="manual",
    )
    label = SheetLabel(
        text="SSMH",
        bbox_fractional=(0.39, 0.34, 0.45, 0.38),
        viewport_id="plan",
        confidence=0.95,
    )
    far = SheetLabel(
        text="OTHER",
        bbox_fractional=(0.80, 0.80, 0.85, 0.85),
        viewport_id="plan",
        confidence=0.9,
    )

    associations = associate_labels_to_symbols([label, far], [symbol])
    assert len(associations) == 1
    row = associations[0]
    assert row["symbol_index"] == 0
    assert row["label_index"] == 0
    assert row["label_text"] == "SSMH"
    assert row["method"] == "nearest_neighbor"
    assert row["distance"] < 0.08


def test_associate_respects_viewport_mismatch() -> None:
    symbol = SheetSymbol(
        symbol_class="ssmh",
        bbox_fractional=(0.40, 0.40, 0.44, 0.44),
        viewport_id="plan",
        confidence=1.0,
        detector="manual",
    )
    label = SheetLabel(
        text="SSMH",
        bbox_fractional=(0.39, 0.34, 0.45, 0.38),
        viewport_id="profile",
        confidence=1.0,
    )
    assert associate_labels_to_symbols([label], [symbol]) == []


def test_normalize_symbol_class_via_legend(db_session) -> None:
    seed(db_session, project_id=None)
    assert normalize_symbol_class("SS", legend_session=db_session) == "sanitary sewer"
    # SSMH is a legend symbol code; without abbrev row, falls back to lowercased class.
    assert normalize_symbol_class("SSMH", legend_session=db_session) in {
        "ssmh",
        "sanitary sewer manhole",
    }
