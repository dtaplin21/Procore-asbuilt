"""Tests for evidence ↔ drawing sheet reference linking."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from services.evidence_linking import extract_sheet_refs, find_project_drawings_for_refs


def test_extract_sheet_refs_legacy_format() -> None:
    refs = extract_sheet_refs("See sheet C-101 and structural S-201A for details.")

    assert "C-101" in refs
    assert "S-201A" in refs


def test_extract_sheet_refs_procore_dot_format() -> None:
    text = "OSHPD Sheets C4.20 C4.21 C6.00 Attachments U1.C4.20 6.00 Sanitary Sewer Install.pdf"

    refs = extract_sheet_refs(text)

    assert "C4.20" in refs
    assert "C4.21" in refs
    assert "C6.00" in refs
    assert "U1.C4.20" in refs


def test_find_project_drawings_for_refs_matches_original_filename() -> None:
    db = MagicMock()
    drawing = SimpleNamespace(
        id=42,
        name="Sanitary Sewer Install",
        original_filename="7.20-7.24 U1.C4.20 6.00 Sanitary Sewer Install.pdf",
    )
    db.query.return_value.filter.return_value.all.return_value = [drawing]

    matches = find_project_drawings_for_refs(db, project_id=2, refs=["C4.20"])

    assert len(matches) == 1
    assert matches[0]["drawing_id"] == 42
    assert matches[0]["matched_text"] == "C4.20"
