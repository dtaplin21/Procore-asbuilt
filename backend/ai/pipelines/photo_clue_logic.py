"""Convert field photo extractions into master-drawing text search clues.

Field photos are not matched as image crops against the master plan. They are
converted into construction clues that the candidate tile selector matches
against drawing region labels and tags (OCR/text index).
"""

from __future__ import annotations

from dataclasses import dataclass

from ai.pipelines.clue_expander import expand_clue_value
from ai.schemas.document_extraction_schemas import FieldPhotoFields

UTILITY_CONTEXT_OBJECTS = frozenset(
    {"trench", "pipe", "gravel bedding", "gravel", "bedding", "utility trench"}
)
DERIVED_UTILITY_TERMS = ("utility line", "utility")


@dataclass(frozen=True)
class PhotoClueCandidate:
    clue_type: str
    value: str
    confidence: float
    location_relevant: bool = True


def build_field_photo_clue_candidates(
    type_specific: FieldPhotoFields,
) -> list[PhotoClueCandidate]:
    """Build location-relevant search clues from a field photo extraction."""
    candidates: list[PhotoClueCandidate] = []
    seen: set[tuple[str, str]] = set()

    def add(
        clue_type: str,
        value: str,
        confidence: float,
        *,
        location_relevant: bool = True,
    ) -> None:
        text = value.strip()
        if not text:
            return
        key = (clue_type, text.lower())
        if key in seen:
            return
        seen.add(key)
        candidates.append(
            PhotoClueCandidate(
                clue_type=clue_type,
                value=text,
                confidence=confidence,
                location_relevant=location_relevant,
            )
        )

    def add_with_expansions(
        clue_type: str,
        value: str,
        confidence: float,
        *,
        expansion_type: str | None = None,
        expansion_confidence: float = 0.55,
    ) -> None:
        add(clue_type, value, confidence)
        expansion_kind = expansion_type or f"{clue_type}_expansion"
        for term in expand_clue_value(value):
            if term.lower() == value.lower():
                continue
            add(expansion_kind, term, expansion_confidence)

    if type_specific.utility_type:
        add_with_expansions("utility_type", type_specific.utility_type, 0.70)

    for obj in type_specific.visible_objects:
        add_with_expansions("visible_object", obj, 0.55)

    for text in type_specific.visible_text:
        add_with_expansions("visible_text", text, 0.60)

    for hint in type_specific.possible_location_clues:
        add_with_expansions("location_hint", hint, 0.60)

    if type_specific.environment:
        add_with_expansions("environment", type_specific.environment, 0.65)

    if type_specific.camera_perspective:
        add(
            "camera_perspective",
            type_specific.camera_perspective,
            0.50,
            location_relevant=False,
        )

    objects_lower = {obj.strip().lower() for obj in type_specific.visible_objects if obj.strip()}
    hints_lower = " ".join(type_specific.possible_location_clues).lower()
    has_utility_context = (
        bool(objects_lower & UTILITY_CONTEXT_OBJECTS)
        or "trench" in hints_lower
        or "pipe" in hints_lower
    )
    if has_utility_context:
        for term in DERIVED_UTILITY_TERMS:
            add("derived_search_term", term, 0.55)

    return candidates
