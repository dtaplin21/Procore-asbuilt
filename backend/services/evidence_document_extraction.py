"""Run document extraction when inspection evidence is uploaded."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from ai.pipelines.document_extraction_orchestrator import run_document_extraction
from ai.pipelines.document_text_extraction import extract_document
from models.document_extraction import DocumentExtraction
from models.models import EvidenceRecord
from services.inspection_matching_jobs import maybe_enqueue_inspection_match_job

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InspectionMatchEnqueueContext:
    project_id: int
    master_drawing_id: int | str
    page: int = 1
    inspection_run_id: int | None = None


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
    match_context: InspectionMatchEnqueueContext | None = None,
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
        extraction = run_document_extraction(
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

    if extraction is not None and match_context is not None:
        maybe_enqueue_inspection_match_job(
            session,
            project_id=match_context.project_id,
            inspection_id=str(evidence_id),
            master_drawing_id=match_context.master_drawing_id,
            page=match_context.page,
            inspection_run_id=match_context.inspection_run_id,
        )

    return extraction
