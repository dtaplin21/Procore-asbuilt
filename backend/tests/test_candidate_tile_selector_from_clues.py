"""Tests for clue-based candidate tile selection."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

from ai.pipelines.candidate_tile_selector import (
    CandidateTile,
    bbox_on_page,
    compute_tile_match_score,
    _bbox_overlap_ratio,
    _clue_matches_row,
    _load_candidate_tiles,
    _merge_candidate_tiles,
    find_candidate_tiles_from_clues,
)
from models.drawing_region import DrawingRegion
from models.drawing_text_element import DrawingTextElement
from services.storage import StorageService
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


def test_location_relevant_clues_are_used_for_matching() -> None:
    clue = SimpleNamespace(
        clue_value="COLO",
        clue_type="location_text",
        confidence=0.9,
        location_relevant=True,
    )

    assert clue.location_relevant is True
    assert clue.clue_value == "COLO"


def test_clue_matching_uses_literal_substrings_not_regex() -> None:
    """Clue values are matched literally, not via legacy regex search terms."""
    dot_clue = SimpleNamespace(clue_value=".", location_relevant=True, confidence=0.9)
    assert _clue_matches_row(dot_clue, "roof drainage plan") is False
    assert _clue_matches_row(dot_clue, "a.b") is True

    paren_clue = SimpleNamespace(clue_value="(ZONE-A)", location_relevant=True, confidence=0.9)
    assert _clue_matches_row(paren_clue, "zone-a parking lot") is False
    assert _clue_matches_row(paren_clue, "(zone-a) parking lot") is True


def _tile(
    text: str,
    confidence: float = 0.75,
    bbox: tuple[float, float, float, float] = (0.1, 0.2, 0.3, 0.4),
) -> CandidateTile:
    return CandidateTile(
        drawing_id="10",
        page=1,
        text=text,
        confidence=confidence,
        bbox_normalized=bbox,
        region_id=1,
    )


@patch("ai.pipelines.candidate_tile_selector._load_candidate_tiles")
def test_location_relevant_clues_match_colo_sewer_region(mock_load) -> None:
    """COLO sewer row ranks; roof drainage row is excluded (no regex search terms)."""
    sewer_row = _tile("COLO PARKING LOT SANITARY SEWER")
    roof_row = _tile("ROOF DRAINAGE PLAN")
    mock_load.return_value = [sewer_row, roof_row]
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
    assert results[0] is sewer_row
    assert roof_row not in results
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


@patch("ai.pipelines.clue_expander.EXPANSIONS", {})
@patch("ai.pipelines.candidate_tile_selector._load_candidate_tiles")
def test_sanitary_sewer_clue_matches_ss_only_labels_via_legend(
    mock_load,
    db_session,
) -> None:
    """Legend lookup widens 'sanitary sewer' to SS when the OCR index has codes only."""
    from scripts.seed_legend_reference import seed

    seed(db_session, project_id=None)
    mock_load.return_value = [
        _tile("U2.C4.00 SS-3"),
        _tile("ROOF DRAINAGE PLAN"),
    ]
    clues = [_clue("sanitary sewer", confidence=0.85)]

    results = find_candidate_tiles_from_clues(
        session=db_session,
        drawing_id="10",
        page=1,
        clues=clues,
    )

    assert len(results) == 1
    assert "SS" in results[0].text
    assert "ROOF" not in results[0].text


def test_bbox_overlap_ratio_detects_intersection() -> None:
    left = (0.0, 0.0, 0.5, 0.5)
    contained = (0.1, 0.1, 0.4, 0.4)
    assert _bbox_overlap_ratio(left, contained) > 0.5
    assert _bbox_overlap_ratio(left, (0.6, 0.6, 0.8, 0.8)) == 0.0


def test_merge_candidate_tiles_prefers_text_elements_over_overlapping_regions() -> None:
    text_tile = CandidateTile(
        drawing_id="10",
        page=1,
        text="SS-3",
        confidence=0.85,
        bbox_normalized=(0.1, 0.1, 0.2, 0.2),
        text_element_id=1,
    )
    region_tile = CandidateTile(
        drawing_id="10",
        page=1,
        text="SS cluster COLO",
        confidence=0.75,
        bbox_normalized=(0.12, 0.12, 0.25, 0.25),
        region_id=2,
    )
    separate_region = CandidateTile(
        drawing_id="10",
        page=1,
        text="ROOF DRAINAGE PLAN",
        confidence=0.75,
        bbox_normalized=(0.7, 0.7, 0.9, 0.9),
        region_id=3,
    )

    merged = _merge_candidate_tiles([text_tile], [region_tile, separate_region])

    assert len(merged) == 2
    assert text_tile in merged
    assert region_tile not in merged
    assert separate_region in merged


def test_candidate_selector_uses_text_elements(db_session, project) -> None:
    """Fine OCR tokens are loaded before coarse drawing regions."""
    storage = StorageService(db_session)
    drawing = storage.create_drawing(
        project_id=cast(int, project.id),
        source="upload",
        name="Master.pdf",
        storage_key="projects/2/drawings/master.pdf",
        content_type="application/pdf",
    )
    drawing_id = cast(int, drawing.id)

    db_session.add(
        DrawingTextElement(
            master_drawing_id=drawing_id,
            page=1,
            text="SS-3",
            text_normalized="ss-3",
            bbox_json={"x0": 0.10, "y0": 0.10, "x1": 0.14, "y1": 0.12},
            ocr_confidence=0.95,
            source="native_pdf",
        )
    )
    db_session.add(
        DrawingRegion(
            master_drawing_id=drawing_id,
            label="COLO sanitary sewer cluster",
            page=1,
            geometry={"type": "rect", "x": 0.5, "y": 0.5, "width": 0.2, "height": 0.2},
            location_tags=["COLO"],
        )
    )
    db_session.commit()

    tiles = _load_candidate_tiles(db_session, drawing_id, page=1)

    assert len(tiles) == 2
    text_tile = next(tile for tile in tiles if tile.text_element_id is not None)
    region_tile = next(tile for tile in tiles if tile.region_id is not None)
    assert "SS-3" in text_tile.text
    assert "COLO" in region_tile.text

    results = find_candidate_tiles_from_clues(
        session=db_session,
        drawing_id=drawing_id,
        page=1,
        clues=[_clue("SS-3", confidence=0.9)],
    )

    assert len(results) == 1
    assert results[0].text_element_id is not None
    assert "SS-3" in results[0].text


def test_overlapping_region_dropped_when_text_element_covers_same_bbox(
    db_session,
    project,
) -> None:
    storage = StorageService(db_session)
    drawing = storage.create_drawing(
        project_id=cast(int, project.id),
        source="upload",
        name="Master.pdf",
        storage_key="projects/2/drawings/master-overlap.pdf",
        content_type="application/pdf",
    )
    drawing_id = cast(int, drawing.id)

    db_session.add(
        DrawingTextElement(
            master_drawing_id=drawing_id,
            page=1,
            text="SS-3",
            text_normalized="ss-3",
            bbox_json={"x0": 0.10, "y0": 0.10, "x1": 0.20, "y1": 0.20},
            ocr_confidence=0.95,
            source="native_pdf",
        )
    )
    db_session.add(
        DrawingRegion(
            master_drawing_id=drawing_id,
            label="SS-3 cluster",
            page=1,
            geometry={"type": "rect", "x": 0.10, "y": 0.10, "width": 0.10, "height": 0.10},
            location_tags=["SS"],
        )
    )
    db_session.commit()

    tiles = _load_candidate_tiles(db_session, drawing_id, page=1)

    assert len(tiles) == 1
    assert tiles[0].text_element_id is not None
    assert tiles[0].region_id is None


def test_bbox_on_page_rejects_off_page_tiles() -> None:
    assert bbox_on_page((0.1, 0.2, 0.3, 0.4)) is True
    assert bbox_on_page((0.6, 1.15, 0.61, 1.19)) is False


@patch("ai.pipelines.candidate_tile_selector._load_candidate_tiles")
def test_off_page_utility_tiles_are_ignored(mock_load) -> None:
    mock_load.return_value = [
        _tile("UTILITY", bbox=(0.600, 1.150, 0.608, 1.193)),
        _tile("Utility MR Corridor", bbox=(0.50, 0.45, 0.58, 0.52)),
    ]
    clues = [
        _clue("Utility", confidence=0.90),
        _clue("Utility MR", confidence=0.85),
    ]

    results = find_candidate_tiles_from_clues(
        session=_mock_session(),
        drawing_id="10",
        page=1,
        clues=clues,
    )

    assert len(results) == 1
    assert results[0].text == "Utility MR Corridor"
    assert compute_tile_match_score(results[0], clues) > 0


@patch("ai.pipelines.candidate_tile_selector._load_candidate_tiles")
def test_generic_utility_clue_demoted_when_specific_clue_exists(mock_load) -> None:
    mock_load.return_value = [
        _tile("UTILITY", confidence=0.95),
        _tile("Utility MR", confidence=0.80),
    ]
    clues = [
        _clue("Utility", confidence=0.95),
        _clue("Utility MR", confidence=0.80),
    ]

    results = find_candidate_tiles_from_clues(
        session=_mock_session(),
        drawing_id="10",
        page=1,
        clues=clues,
    )

    assert results
    assert results[0].text == "Utility MR"
