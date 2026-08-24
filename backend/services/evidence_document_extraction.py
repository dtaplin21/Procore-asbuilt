"""Run document extraction when inspection evidence is uploaded."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from sqlalchemy.orm import Session

from ai.agents.tools.pdf_investigation import run_pdf_investigation
from ai.pipelines.document_text_extraction import extract_document
from ai.pipelines.pdf_link_follower import LinkFollowResult, follow_pdf_links
from models.document_extraction import DocumentExtraction
from models.models import EvidenceRecord
from services.evidence_investigation_persistence import persist_evidence_investigation
from services.inspection_matching_jobs import maybe_enqueue_inspection_match_after_extraction

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


def extract_evidence_file_content_with_links(
    file_path: str | Path,
) -> tuple[str, str, LinkFollowResult]:
    """Return ``(merged_text, base_text, link_result)``."""
    base = extract_evidence_file_content(file_path).strip()
    link_result = follow_pdf_links(file_path)
    if link_result.supplemental_text.strip():
        # Priority-ranked linked content first so classifiers/extractors see
        # install drawings and plans within their preview window.
        merged = f"{link_result.supplemental_text}\n{base}".strip()
    else:
        merged = base
    return merged, base, link_result


def ingest_evidence_upload_only(
    session: Session,
    *,
    evidence_id: int,
    file_path: str | Path,
    persist_text_content: bool = True,
    match_context: InspectionMatchEnqueueContext | None = None,
) -> bool:
    """Persist uploaded evidence file metadata only (no link follow or clue extraction).

    PDF hyperlink investigation, linked drawing registration, survey extraction, and
    document clue extraction run at location-match time via ``build_evidence_dossier``.
    """
    try:
        base = extract_evidence_file_content(file_path).strip()
    except Exception:
        logger.exception(
            "evidence_upload_only_content_failed",
            extra={"evidence_id": evidence_id, "file_path": str(file_path)},
        )
        return False

    if persist_text_content and base:
        evidence = session.query(EvidenceRecord).filter(EvidenceRecord.id == evidence_id).first()
        if evidence is not None:
            setattr(evidence, "text_content", base)
            session.flush()

    if match_context is not None:
        maybe_enqueue_inspection_match_after_extraction(
            session,
            evidence_id=evidence_id,
            project_id=match_context.project_id,
            inspection_id=str(evidence_id),
            master_drawing_id=match_context.master_drawing_id,
            page=match_context.page,
            inspection_run_id=match_context.inspection_run_id,
        )

    return True


def ingest_evidence_document_extraction(
    session: Session,
    *,
    evidence_id: int,
    file_path: str | Path,
    persist_text_content: bool = True,
    match_context: InspectionMatchEnqueueContext | None = None,
) -> DocumentExtraction | None:
    """Run clue-based document extraction for an uploaded evidence file.

    .. deprecated::
        Inspection run uploads use ``ingest_evidence_upload_only``; full extraction
        moves to location-match investigation (see Notes/location_match_investigation_plan.md).
    """
    try:
        payload = run_pdf_investigation(Path(file_path))
    except Exception:
        logger.exception(
            "evidence_content_extraction_failed",
            extra={"evidence_id": evidence_id, "file_path": str(file_path)},
        )
        return None

    if not payload.base_text and not payload.link_result.supplemental_text.strip():
        logger.warning(
            "evidence_content_empty",
            extra={"evidence_id": evidence_id, "file_path": str(file_path)},
        )
        return None

    evidence = session.query(EvidenceRecord).filter(EvidenceRecord.id == evidence_id).first()
    if evidence is None:
        logger.warning(
            "evidence_document_extraction_missing_evidence",
            extra={"evidence_id": evidence_id},
        )
        return None

    persist_result = persist_evidence_investigation(
        session,
        evidence_id=evidence_id,
        file_path=file_path,
        project_id=cast(int, evidence.project_id),
        payload=payload,
        persist_text_content=persist_text_content,
        text_content_max_chars=None,
    )

    if persist_result.extraction_id is None:
        return None

    extraction = session.get(DocumentExtraction, persist_result.extraction_id)

    if extraction is not None and match_context is not None:
        maybe_enqueue_inspection_match_after_extraction(
            session,
            evidence_id=evidence_id,
            project_id=match_context.project_id,
            inspection_id=str(evidence_id),
            master_drawing_id=match_context.master_drawing_id,
            page=match_context.page,
            inspection_run_id=match_context.inspection_run_id,
        )

    return extraction
