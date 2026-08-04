"""Convert extracted fields into searchable matching clues.

These clues feed the existing candidate selector and match storage (see
drawing_location_resolver.py and inspection_mapping.py). They replace the
legacy regex-only inspection query builder approach.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, List

from ai.pipelines.photo_clue_logic import build_field_photo_clue_candidates
from ai.schemas.document_extraction_schemas import (
    Clue,
    DocumentType,
    FieldPhotoFields,
    InspectionReportFields,
    MasterDrawingFields,
    UniversalFields,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


_LOCATION_LABEL_RE = re.compile(
    r"\bLocation\s*:?\s*([A-Za-z0-9][A-Za-z0-9\-_/]{0,40})\b",
    re.IGNORECASE,
)


def supplement_location_clues_from_content(content: str, clues: List[Clue]) -> List[Clue]:
    """Add short location codes parsed from raw text (e.g. Procore ``Location COLO``).

    Universal field extraction often returns a full address for ``location_text``.
    This keeps compact site codes that appear on master drawing region tags.
    """
    existing = {
        clue.value.strip().lower()
        for clue in clues
        if clue.location_relevant and clue.value.strip()
    }
    supplemental: List[Clue] = []

    for match in _LOCATION_LABEL_RE.finditer(content):
        value = match.group(1).strip()
        if not value or len(value) > 40:
            continue
        if any(ch in value for ch in ",;") or value.count(" ") > 3:
            continue
        normalized = value.lower()
        if normalized in existing:
            continue
        supplemental.append(
            Clue(
                type="location_code",
                value=value,
                source="document_text",
                confidence=0.92,
                location_relevant=True,
            )
        )
        existing.add(normalized)

    return clues + supplemental


def _append_legend_abbreviation_clues(
    clues: List[Clue],
    session: Session,
    project_id: int | None = None,
) -> List[Clue]:
    from services.legend_lookup import find_codes_for_term

    expanded_clues: List[Clue] = []
    existing_values = {clue.value.strip().lower() for clue in clues if clue.value.strip()}

    for clue in clues:
        codes = find_codes_for_term(session, clue.value, project_id)
        for code in codes:
            if code.strip().lower() in existing_values:
                continue
            expanded_clues.append(
                Clue(
                    type=f"{clue.type}_abbreviation",
                    value=code,
                    source=clue.source,
                    confidence=clue.confidence * 0.9,
                    location_relevant=clue.location_relevant,
                )
            )
            existing_values.add(code.strip().lower())

    return clues + expanded_clues


def build_clues(
    document_type: DocumentType,
    universal: UniversalFields,
    type_specific,
    session: Session | None = None,
    project_id: int | None = None,
) -> List[Clue]:
    clues: List[Clue] = []

    if universal.location_text:
        clues.append(
            Clue(
                type="location_text",
                value=universal.location_text,
                source=document_type.value,
                confidence=0.90,
                location_relevant=True,
            )
        )

    if universal.trade:
        clues.append(
            Clue(
                type="trade",
                value=universal.trade,
                source=document_type.value,
                confidence=0.85,
                location_relevant=True,
            )
        )

    if universal.contractor:
        clues.append(
            Clue(
                type="contractor",
                value=universal.contractor,
                source=document_type.value,
                confidence=0.60,
                location_relevant=False,
            )
        )

    if universal.document_title:
        clues.append(
            Clue(
                type="document_title",
                value=universal.document_title,
                source=document_type.value,
                confidence=0.65,
                location_relevant=True,
            )
        )

    if isinstance(type_specific, InspectionReportFields):
        if type_specific.inspection_name:
            clues.append(
                Clue(
                    type="inspection_name",
                    value=type_specific.inspection_name,
                    source="inspection_report",
                    confidence=0.80,
                    location_relevant=True,
                )
            )

        for note in type_specific.inspection_notes:
            clues.append(
                Clue(
                    type="inspection_note",
                    value=note,
                    source="inspection_report",
                    confidence=0.75,
                    location_relevant=True,
                )
            )

        for item in type_specific.items_inspected:
            clues.append(
                Clue(
                    type="item_inspected",
                    value=item,
                    source="inspection_report",
                    confidence=0.75,
                    location_relevant=True,
                )
            )

    elif isinstance(type_specific, FieldPhotoFields):
        for entry in build_field_photo_clue_candidates(type_specific):
            clues.append(
                Clue(
                    type=entry.clue_type,
                    value=entry.value,
                    source="field_photo",
                    confidence=entry.confidence,
                    location_relevant=entry.location_relevant,
                )
            )

    elif isinstance(type_specific, MasterDrawingFields):
        for label in type_specific.drawing_labels:
            clues.append(
                Clue(
                    type="drawing_label",
                    value=label,
                    source="master_drawing",
                    confidence=0.80,
                    location_relevant=False,
                )
            )

        for symbol in type_specific.utility_symbols:
            clues.append(
                Clue(
                    type="utility_symbol",
                    value=symbol,
                    source="master_drawing",
                    confidence=0.70,
                    location_relevant=False,
                )
            )

        for zone in type_specific.areas_or_zones:
            clues.append(
                Clue(
                    type="area_or_zone",
                    value=zone,
                    source="master_drawing",
                    confidence=0.80,
                    location_relevant=True,
                )
            )

    if session is not None:
        clues = _append_legend_abbreviation_clues(clues, session, project_id)

    return clues
