"""Tests for field photo to master-plan clue conversion."""

from ai.pipelines.clue_extractor import build_clues
from ai.pipelines.photo_clue_logic import build_field_photo_clue_candidates
from ai.schemas.document_extraction_schemas import DocumentType, FieldPhotoFields, UniversalFields


def test_field_photo_example_produces_construction_search_clues():
    type_specific = FieldPhotoFields(
        visible_objects=["trench", "pipe", "gravel bedding", "parking lot"],
        visible_text=[],
        environment="outdoor parking lot construction area",
        utility_type="sanitary sewer",
        possible_location_clues=[
            "underground pipe prior to backfill",
            "parking lot area",
            "utility trench",
        ],
        camera_perspective="ground-level field photo",
    )

    clues = build_clues(DocumentType.FIELD_PHOTO, UniversalFields(), type_specific)
    values = {clue.value.lower() for clue in clues if clue.location_relevant}

    assert "sanitary sewer" in values
    assert "ss" in values
    assert "san" in values
    assert "sewer lateral" in values
    assert "cleanout" in values
    assert "manhole" in values
    assert "parking lot" in values
    assert "utility line" in values
    assert "utility trench" in values

    camera = next(c for c in clues if c.type == "camera_perspective")
    assert camera.location_relevant is False


def test_field_photo_clue_candidates_deduplicate_expansions():
    type_specific = FieldPhotoFields(
        utility_type="sanitary sewer",
        visible_objects=["pipe"],
        possible_location_clues=["sanitary sewer trench"],
    )

    candidates = build_field_photo_clue_candidates(type_specific)
    pairs = [(c.clue_type, c.value.lower()) for c in candidates]

    assert pairs.count(("utility_type", "sanitary sewer")) == 1
    assert ("derived_search_term", "utility line") in pairs
