"""Legend lookup against seeded C0.00 reference data."""

from __future__ import annotations

from scripts.seed_legend_reference import seed
from services.legend_lookup import (
    expand_abbreviation,
    find_codes_for_term,
    legend_code_matches_text,
)


def test_expand_abbreviation_ss_to_sanitary_sewer(db_session) -> None:
    seed(db_session, project_id=None)

    result = expand_abbreviation(db_session, "SS")

    assert result == "SANITARY SEWER"


def test_find_codes_for_sanitary_sewer_term(db_session) -> None:
    seed(db_session, project_id=None)

    codes = find_codes_for_term(db_session, "sanitary sewer")

    assert "SS" in codes
    assert "SSMH" in codes
    assert "SSCO" in codes


def test_legend_code_matches_whole_tokens_only() -> None:
    assert legend_code_matches_text("S", "DASHED") is False
    assert legend_code_matches_text("A", "DASHED") is False
    assert legend_code_matches_text("D", "DASHED") is False
    assert legend_code_matches_text("E", "DASHED") is False
    assert legend_code_matches_text("S", "S") is False
    assert legend_code_matches_text("SS", "DASHED") is False
    assert legend_code_matches_text("SS", "ASSESS") is False
    assert legend_code_matches_text("SS", "SSMH") is False
    assert legend_code_matches_text("SS", "SS") is True
    assert legend_code_matches_text("SS", "line ss main") is True
    assert legend_code_matches_text("SS", "SS-1") is True
    assert legend_code_matches_text("C&G", "C&G") is True
