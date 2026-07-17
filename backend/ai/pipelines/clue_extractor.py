"""Convert extracted fields into searchable matching clues.

These clues feed the existing candidate selector and match storage (see
drawing_location_resolver.py and inspection_mapping.py). They replace the
legacy regex-only inspection query builder approach.
"""

from __future__ import annotations

from typing import List

from ai.pipelines.photo_clue_logic import build_field_photo_clue_candidates
from ai.schemas.document_extraction_schemas import (
    Clue,
    DocumentType,
    FieldPhotoFields,
    InspectionReportFields,
    MasterDrawingFields,
    UniversalFields,
)


def build_clues(
    document_type: DocumentType,
    universal: UniversalFields,
    type_specific,
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

    return clues
