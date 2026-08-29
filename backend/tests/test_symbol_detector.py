"""Tests for optional symbol detector (PR-S S-2)."""

from __future__ import annotations

from pathlib import Path

from ai.pipelines.symbol_detector import (
    SYMBOL_DETECTOR_WEIGHTS_MISSING,
    detect_symbols,
    resolve_symbol_detector_weights_path,
)


def test_detect_symbols_returns_empty_when_weights_none(caplog) -> None:
    with caplog.at_level("INFO"):
        symbols = detect_symbols(Path("missing.png"), weights_path=None)
    assert symbols == []
    assert any(SYMBOL_DETECTOR_WEIGHTS_MISSING in record.message for record in caplog.records)


def test_detect_symbols_returns_empty_when_weights_file_missing(tmp_path: Path) -> None:
    missing = tmp_path / "no_such_weights.pt"
    assert detect_symbols(tmp_path / "page.png", weights_path=missing) == []


def test_resolve_symbol_detector_weights_path_none() -> None:
    assert resolve_symbol_detector_weights_path(None) is None
    assert resolve_symbol_detector_weights_path(Path("/definitely/not/here.pt")) is None
