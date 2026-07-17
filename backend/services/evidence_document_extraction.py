"""Run document extraction when inspection evidence is uploaded."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from ai.pipelines.document_extraction_orchestrator import run_document_extraction
from ai.pipelines.document_text_extraction import extract_document
from models.document_extraction import DocumentExtraction
from models.models import EvidenceRecord

logger = logging.getLogger(__name__)


def extract_evidence_file_content(file_path: str | Path) -> str:
    """Extract plain text (or OCR text) from an evidence file."""
    document = extract_document(file_path)
    return document.full_text()


def ingest_evidence_document_extraction(
    session: Session,
    *,
    evidence_id: int,
    file_path: str | Path,
    persist_text_content: bool = True,
) -> DocumentExtraction | None:
    """Run clue-based document extraction for an uploaded evidence file."""
    try:
        content = extract_evidence_file_content(file_path).strip()
    except Exception:
        logger.exception(
            "evidence_content_extraction_failed",
            extra={"evidence_id": evidence_id, "file_path": str(file_path)},
        )
        return None

    if not content:
        logger.warning(
            "evidence_content_empty",
            extra={"evidence_id": evidence_id, "file_path": str(file_path)},
        )
        return None

    if persist_text_content:
        evidence = session.query(EvidenceRecord).filter(EvidenceRecord.id == evidence_id).first()
        if evidence is not None:
            setattr(evidence, "text_content", content)
            session.flush()

    try:
        return run_document_extraction(
            session,
            file_id=str(evidence_id),
            content=content,
        )
    except Exception:
        logger.exception(
            "document_extraction_orchestrator_failed",
            extra={"evidence_id": evidence_id},
        )
        session.rollback()
        return None
