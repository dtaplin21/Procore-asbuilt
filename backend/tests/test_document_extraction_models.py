"""Tests for document_extractions and document_clues persistence."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import cast

import pytest
from sqlalchemy.orm import Session

from database import SessionLocal
from models.document_clue import DocumentClue
from models.document_extraction import DocumentExtraction


def _unique_file_id() -> str:
    return f"evidence-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def test_persist_document_extraction_and_clues(db: Session) -> None:
    file_id = _unique_file_id()

    extraction = DocumentExtraction(
        file_id=file_id,
        document_type="inspection_report",
        classification_confidence=0.88,
        universal_fields_json={
            "project_name": "UCSF Benioff Oakland",
            "location_text": "COLO",
            "trade": "33-Sanitary Sewerage",
        },
        type_specific_fields_json={
            "inspection_name": "Underground Sanitary Sewer #1",
            "inspection_notes": [
                "Sanitary sewer inspection prior to backfill in the Colo parking lot"
            ],
        },
    )
    extraction.clues = [
        DocumentClue(
            clue_type="location_text",
            clue_value="COLO",
            source="inspection_report",
            confidence=0.90,
            location_relevant=True,
        ),
        DocumentClue(
            clue_type="trade",
            clue_value="33-Sanitary Sewerage",
            source="inspection_report",
            confidence=0.85,
            location_relevant=True,
        ),
    ]

    db.add(extraction)
    db.commit()
    db.refresh(extraction)

    assert extraction.id is not None
    assert cast(str, extraction.file_id) == file_id
    assert cast(float | None, extraction.classification_confidence) == 0.88

    stored = db.query(DocumentExtraction).filter_by(id=cast(int, extraction.id)).one()
    clues = db.query(DocumentClue).filter_by(
        document_extraction_id=cast(int, stored.id)
    ).all()

    assert len(clues) == 2
    values = {cast(str, clue.clue_value) for clue in clues}
    assert "COLO" in values
    assert "33-Sanitary Sewerage" in values
    assert all(cast(float, clue.confidence) > 0 for clue in clues)


def test_document_clues_cascade_delete_with_extraction(db: Session) -> None:
    extraction = DocumentExtraction(
        file_id=_unique_file_id(),
        document_type="unknown",
        classification_confidence=0.0,
    )
    extraction.clues = [
        DocumentClue(
            clue_type="location_text",
            clue_value="COLO",
            source="unknown",
            confidence=0.5,
            location_relevant=True,
        )
    ]
    db.add(extraction)
    db.commit()

    extraction_id = cast(int, extraction.id)
    db.delete(extraction)
    db.commit()

    remaining = db.query(DocumentClue).filter_by(document_extraction_id=extraction_id).all()
    assert remaining == []
