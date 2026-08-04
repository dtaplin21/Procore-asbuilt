"""Legend lookup against seeded C0.00 reference data."""

from __future__ import annotations

from scripts.seed_legend_reference import seed
from services.legend_lookup import expand_abbreviation, find_codes_for_term


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
