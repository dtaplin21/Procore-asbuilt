"""Run document extraction when inspection evidence is uploaded."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from sqlalchemy.orm import Session

from ai.pipelines.document_extraction_orchestrator import run_document_extraction
from ai.pipelines.document_text_extraction import extract_document
from ai.pipelines.pdf_link_follower import LinkFollowResult, follow_pdf_links
from models.document_extraction import DocumentExtraction
from models.models import EvidenceRecord
from services.evidence_linking import replace_evidence_drawing_links
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
        content, base, link_result = extract_evidence_file_content_with_links(file_path)
    except Exception:
        logger.exception(
            "evidence_content_extraction_failed",
            extra={"evidence_id": evidence_id, "file_path": str(file_path)},
        )
        return None

    if not base and not link_result.supplemental_text.strip():
        logger.warning(
            "evidence_content_empty",
            extra={"evidence_id": evidence_id, "file_path": str(file_path)},
        )
        return None

    evidence: EvidenceRecord | None = None
    if persist_text_content:
        evidence = session.query(EvidenceRecord).filter(EvidenceRecord.id == evidence_id).first()
        if evidence is not None:
            setattr(evidence, "text_content", content)
            cross_raw = cast(list[Any] | None, evidence.cross_refs_json)
            existing_refs = list(cross_raw or [])
            existing_refs.extend(link_result.cross_refs)
            evidence.cross_refs_json = existing_refs  # type: ignore[assignment]
            meta_raw = cast(dict[str, Any] | None, evidence.meta)
            meta = dict(meta_raw or {})
            meta["pdfLinkFollow"] = {
                "followed": link_result.followed_count,
                "skipped": link_result.skipped_count,
                "errors": link_result.errors[:5],
            }
            evidence.meta = meta  # type: ignore[assignment]
            session.flush()
            try:
                replace_evidence_drawing_links(session, evidence, commit=False)
            except Exception:
                logger.exception(
                    "evidence_drawing_link_sync_failed",
                    extra={"evidence_id": evidence_id},
                )

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
