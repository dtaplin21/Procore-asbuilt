"""Tests for construction clue expansion."""

from ai.pipelines.clue_expander import expand_clue_value


def test_expand_sanitary_sewerage_includes_abbreviations() -> None:
    terms = expand_clue_value("33-Sanitary Sewerage")
    lowered = {term.lower() for term in terms}

    assert "33-sanitary sewerage" in lowered
    assert "sanitary sewer" in lowered
    assert "ss" in lowered
    assert "san" in lowered
    assert "sewer lateral" in lowered
    assert "cleanout" in lowered
    assert "manhole" in lowered


def test_expand_clue_value_deduplicates_case_insensitive() -> None:
    terms = expand_clue_value("sanitary sewer SS")
    lowered = [term.lower() for term in terms]

    assert lowered.count("ss") == 1
    assert lowered.count("sanitary sewer") == 1


def test_expand_empty_value_returns_empty_list() -> None:
    assert expand_clue_value("") == []
