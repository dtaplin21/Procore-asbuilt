"""Sanity checks on the transcribed data itself — catches typos/duplicates before
they ever hit the DB."""

from __future__ import annotations

from data.legend_seed_data import ABBREVIATIONS, LINE_TYPES, SYMBOLS


def test_no_duplicate_abbreviations() -> None:
    codes = [abbrev for abbrev, _, _ in ABBREVIATIONS]
    assert len(codes) == len(set(codes)), "duplicate abbreviation codes in seed data"


def test_key_utility_abbreviations_present() -> None:
    codes = {abbrev for abbrev, _, _ in ABBREVIATIONS}
    for expected in ["SS", "SD", "FW", "DW", "FDC", "MH", "CO", "STA", "INV"]:
        assert expected in codes, f"expected abbreviation {expected} missing from seed data"


def test_sanitary_sewer_line_type_has_code() -> None:
    match = next(line_type for line_type in LINE_TYPES if line_type[0] == "Sanitary Sewer Main")
    assert match[1] == "SS"


def test_no_empty_expansions() -> None:
    for abbrev, expansion, _ in ABBREVIATIONS:
        assert expansion.strip() != "", f"empty expansion for abbreviation {abbrev!r}"
