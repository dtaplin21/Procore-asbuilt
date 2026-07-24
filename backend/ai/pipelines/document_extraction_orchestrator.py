"""Document extraction orchestrator.

Runs:
classification -> universal extraction -> type-specific extraction -> clue generation -> DB persistence
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from ai.pipelines.clue_extractor import build_clues, supplement_location_clues_from_content
from ai.pipelines.document_classifier import classify_document
from ai.pipelines.type_specific_extractor import extract_type_specific_fields
from ai.pipelines.universal_field_extractor import extract_universal_fields
from ai.schemas.document_extraction_schemas import DocumentType
from models.document_clue import DocumentClue
from models.document_extraction import DocumentExtraction
from services.review_queue import add_to_review_queue


def _model_dump(model: BaseModel | None) -> dict[str, Any] | None:
    if model is None:
        return None
    return model.model_dump()


def run_document_extraction(
    session: Session,
    file_id: str,
    content: str,
) -> DocumentExtraction:
    classification = classify_document(content)

    if classification.document_type == DocumentType.UNKNOWN:
        add_to_review_queue(
            session,
            file_id=file_id,
            reason="low_confidence_classification",
            document_type_guess=classification.document_type.value,
            confidence=classification.confidence,
            commit=False,
        )

    universal = extract_universal_fields(content)

    type_specific = None
    if classification.document_type != DocumentType.UNKNOWN:
        type_specific = extract_type_specific_fields(
            document_type=classification.document_type,
            content=content,
            session=session,
            file_id=file_id,
        )

    extraction = DocumentExtraction(
        file_id=file_id,
        document_type=classification.document_type.value,
        classification_confidence=classification.confidence,
        universal_fields_json=_model_dump(universal),
        type_specific_fields_json=_model_dump(type_specific),
    )

    session.add(extraction)
    session.flush()

    clues = build_clues(
        document_type=classification.document_type,
        universal=universal,
        type_specific=type_specific,
    )
    clues = supplement_location_clues_from_content(content, clues)

    for clue in clues:
        session.add(
            DocumentClue(
                document_extraction_id=extraction.id,
                clue_type=clue.type,
                clue_value=clue.value,
                source=clue.source,
                confidence=clue.confidence,
                location_relevant=clue.location_relevant,
            )
        )

    session.commit()
    session.refresh(extraction)
    return extraction
