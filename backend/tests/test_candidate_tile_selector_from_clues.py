"""Tests for clue-based candidate tile selection."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

from ai.pipelines.candidate_tile_selector import (
    CandidateTile,
    find_candidate_tiles_from_clues,
)
from ai.schemas.document_extraction_schemas import Clue


def _mock_session() -> Session:
    return cast(Session, MagicMock())


def _clue(value: str, confidence: float = 0.8) -> Clue:
    return Clue(
        type="location_text",
        value=value,
        source="inspection_report",
        confidence=confidence,
        location_relevant=True,
    )


def _tile(text: str, confidence: float = 0.75) -> CandidateTile:
    return CandidateTile(
        drawing_id="10",
        page=1,
        text=text,
        confidence=confidence,
        bbox_normalized=(0.1, 0.2, 0.3, 0.4),
        region_id=1,
    )


@patch("ai.pipelines.candidate_tile_selector._load_candidate_tiles")
def test_location_relevant_clues_match_colo_sewer_region(mock_load):
    mock_load.return_value = [
        _tile("COLO PARKING LOT SANITARY SEWER"),
        _tile("ROOF DRAINAGE PLAN"),
    ]
    clues = [
        _clue("COLO", confidence=0.90),
        _clue("Sanitary Sewerage", confidence=0.85),
        _clue("Colo parking lot", confidence=0.75),
    ]

    results = find_candidate_tiles_from_clues(
        session=_mock_session(),
        drawing_id="10",
        page=1,
        clues=clues,
    )

    assert len(results) == 1
    assert "COLO" in results[0].text
    assert "sanitary sewer" in results[0].text.lower()


@patch("ai.pipelines.candidate_tile_selector._load_candidate_tiles")
def test_non_location_clues_are_ignored(mock_load):
    mock_load.return_value = [_tile("COLO PARKING LOT")]

    clues = [
        Clue(
            type="contractor",
            value="ABC Construction",
            source="inspection_report",
            confidence=0.60,
            location_relevant=False,
        )
    ]

    results = find_candidate_tiles_from_clues(
        session=_mock_session(),
        drawing_id="10",
        page=1,
        clues=clues,
    )

    assert results == []
    mock_load.assert_not_called()


@patch("ai.pipelines.candidate_tile_selector._load_candidate_tiles")
def test_document_clue_rows_are_supported(mock_load):
    mock_load.return_value = [
        _tile("Underground Sanitary Sewer near COLO"),
        _tile("ELECTRICAL ROOM"),
    ]
    clues = [
        SimpleNamespace(
            clue_value="Underground Sanitary Sewer",
            clue_type="inspection_name",
            confidence=0.80,
            location_relevant=True,
        ),
        SimpleNamespace(
            clue_value="COLO",
            clue_type="location_text",
            confidence=0.90,
            location_relevant=True,
        ),
    ]

    results = find_candidate_tiles_from_clues(
        session=_mock_session(),
        drawing_id="10",
        page=1,
        clues=clues,
    )

    assert len(results) == 1
    assert results[0].text.startswith("Underground Sanitary Sewer")


@patch("ai.pipelines.candidate_tile_selector._load_candidate_tiles")
def test_sanitary_sewerage_expansion_matches_ss_abbreviation(mock_load):
    mock_load.return_value = [
        _tile("AREA SS-3 NEAR COLO"),
        _tile("ROOF DRAINAGE PLAN"),
    ]
    clues = [_clue("33-Sanitary Sewerage", confidence=0.85)]

    results = find_candidate_tiles_from_clues(
        session=_mock_session(),
        drawing_id="10",
        page=1,
        clues=clues,
    )

    assert len(results) == 1
    assert "SS" in results[0].text


@patch("ai.pipelines.candidate_tile_selector._load_candidate_tiles")
def test_field_photo_clues_match_master_drawing_text_not_pixels(mock_load):
    from ai.pipelines.clue_extractor import build_clues
    from ai.schemas.document_extraction_schemas import DocumentType, FieldPhotoFields, UniversalFields

    mock_load.return_value = [
        _tile("COLO PARKING LOT SS SANITARY SEWER MH"),
        _tile("ROOF DRAINAGE PLAN"),
    ]
    photo_clues = build_clues(
        DocumentType.FIELD_PHOTO,
        UniversalFields(),
        FieldPhotoFields(
            visible_objects=["trench", "pipe", "parking lot"],
            utility_type="sanitary sewer",
            possible_location_clues=["parking lot area", "utility trench"],
            environment="outdoor parking lot construction area",
        ),
    )

    results = find_candidate_tiles_from_clues(
        session=_mock_session(),
        drawing_id="10",
        page=1,
        clues=photo_clues,
    )

    assert len(results) == 1
    assert "PARKING LOT" in results[0].text
    assert "SS" in results[0].text


@patch("ai.pipelines.candidate_tile_selector._load_candidate_tiles")
def test_no_text_match_returns_empty_list(mock_load):
    mock_load.return_value = [_tile("ROOF DRAINAGE PLAN")]
    clues = [_clue("COLO"), _clue("sanitary sewer")]

    results = find_candidate_tiles_from_clues(
        session=_mock_session(),
        drawing_id="10",
        page=1,
        clues=clues,
    )

    assert results == []
