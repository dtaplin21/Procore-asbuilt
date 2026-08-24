"""Persist match-time PDF investigation results (linked drawings, clues, survey)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from sqlalchemy.orm import Session

from ai.agents.tools.pdf_investigation import EvidenceInvestigationPayload
from ai.pipelines.document_extraction_orchestrator import run_document_extraction
from ai.pipelines.evidence_kind_classifier import classify_and_persist_evidence_kind
from models.document_extraction import DocumentExtraction
from models.models import Drawing, EvidenceRecord, JobQueue
from services.drawing_index_jobs import JOB_TYPE as DRAWING_INDEX_JOB_TYPE, maybe_enqueue_drawing_index_job
from services.drawing_render_jobs import DRAWING_RENDER_JOB_TYPE, enqueue_drawing_render_job
from services.evidence_linking import replace_evidence_drawing_links
from services.evidence_survey_extraction import (
    extract_survey_points_from_evidence,
    persist_evidence_survey_meta,
)
from services.linked_drawing_registration import register_linked_pdfs_as_auxiliary_drawings
from services.master_drawing_index_readiness import get_master_drawing_index_readiness

logger = logging.getLogger(__name__)

_TEXT_CONTENT_PREVIEW_CHARS = 2000


@dataclass(frozen=True)
class EvidenceInvestigationPersistResult:
    linked_drawing_ids: list[int]
    extraction_id: int | None
    survey_point_count: int
    drawing_ids_needing_index: list[int]


def _text_content_for_evidence(
    payload: EvidenceInvestigationPayload,
    *,
    text_content_max_chars: int | None,
) -> str:
    text = payload.merged_text
    if text_content_max_chars is None:
        return text
    if len(text) <= text_content_max_chars:
        return text
    return text[:text_content_max_chars]


def _pending_job_exists(
    session: Session,
    *,
    project_id: int,
    drawing_id: int,
    job_type: str,
) -> bool:
    jobs = (
        session.query(JobQueue)
        .filter(
            JobQueue.project_id == project_id,
            JobQueue.job_type == job_type,
            JobQueue.status.in_(("pending", "processing")),
        )
        .all()
    )
    for job in jobs:
        input_data = cast(dict[str, Any] | None, job.input_data) or {}
        if int(input_data.get("drawing_id", -1)) == drawing_id:
            return True
    return False


def enqueue_linked_drawing_index_jobs(
    session: Session,
    *,
    project_id: int,
    linked_drawing_ids: list[int],
) -> list[int]:
    """Enqueue render/index jobs for linked auxiliary drawings not yet match-ready."""
    needing_index: list[int] = []
    for drawing_id in linked_drawing_ids:
        readiness = get_master_drawing_index_readiness(session, drawing_id)
        if readiness.is_ready_for_matching:
            continue

        needing_index.append(drawing_id)
        drawing = session.get(Drawing, drawing_id)
        if drawing is None:
            continue

        processing_status = str(getattr(drawing, "processing_status", "pending") or "pending")
        if processing_status != "ready":
            if _pending_job_exists(
                session,
                project_id=project_id,
                drawing_id=drawing_id,
                job_type=DRAWING_RENDER_JOB_TYPE,
            ):
                continue
            try:
                enqueue_drawing_render_job(session, project_id, drawing_id)
            except Exception:
                logger.exception(
                    "linked_drawing_render_enqueue_failed",
                    extra={"project_id": project_id, "drawing_id": drawing_id},
                )
            continue

        index_status = str(getattr(drawing, "index_status", "pending") or "pending")
        if index_status in ("ready", "processing"):
            continue
        if _pending_job_exists(
            session,
            project_id=project_id,
            drawing_id=drawing_id,
            job_type=DRAWING_INDEX_JOB_TYPE,
        ):
            continue
        maybe_enqueue_drawing_index_job(session, project_id, drawing_id)

    return needing_index


def persist_evidence_investigation(
    session: Session,
    *,
    evidence_id: int,
    file_path: str | Path,
    project_id: int,
    payload: EvidenceInvestigationPayload,
    persist_text_content: bool = True,
    text_content_max_chars: int | None = _TEXT_CONTENT_PREVIEW_CHARS,
) -> EvidenceInvestigationPersistResult:
    """Apply DB side effects for a completed PDF investigation payload."""
    link_result = payload.link_result
    linked_drawing_ids: list[int] = []
    survey_point_count = 0

    evidence = session.query(EvidenceRecord).filter(EvidenceRecord.id == evidence_id).first()
    if evidence is None:
        logger.warning(
            "evidence_investigation_persist_missing_evidence",
            extra={"evidence_id": evidence_id},
        )
        return EvidenceInvestigationPersistResult(
            linked_drawing_ids=[],
            extraction_id=None,
            survey_point_count=0,
            drawing_ids_needing_index=[],
        )

    if persist_text_content and payload.merged_text:
        setattr(
            evidence,
            "text_content",
            _text_content_for_evidence(payload, text_content_max_chars=text_content_max_chars),
        )

    cross_raw = cast(list[Any] | None, evidence.cross_refs_json)
    existing_refs = list(cross_raw or [])
    existing_refs.extend(link_result.cross_refs)
    evidence.cross_refs_json = existing_refs  # type: ignore[assignment]

    meta_raw = cast(dict[str, Any] | None, evidence.meta)
    meta = dict(meta_raw or {})

    try:
        linked_drawing_ids = register_linked_pdfs_as_auxiliary_drawings(
            session,
            project_id=project_id,
            link_result=link_result,
            evidence_id=evidence_id,
        )
    except Exception:
        logger.exception(
            "linked_drawing_registration_failed",
            extra={"evidence_id": evidence_id},
        )

    drawing_ids_needing_index: list[int] = []
    if linked_drawing_ids:
        try:
            drawing_ids_needing_index = enqueue_linked_drawing_index_jobs(
                session,
                project_id=project_id,
                linked_drawing_ids=linked_drawing_ids,
            )
        except Exception:
            logger.exception(
                "linked_drawing_index_enqueue_failed",
                extra={"evidence_id": evidence_id, "linked_drawing_ids": linked_drawing_ids},
            )

    try:
        replace_evidence_drawing_links(session, evidence, commit=False)
    except Exception:
        logger.exception(
            "evidence_drawing_link_sync_failed",
            extra={"evidence_id": evidence_id},
        )

    try:
        survey_points, scale_json = extract_survey_points_from_evidence(
            session,
            evidence,
            file_path,
        )
        persist_evidence_survey_meta(evidence, survey_points, scale_json)
        survey_point_count = len(survey_points)
    except Exception:
        logger.exception(
            "evidence_survey_point_extraction_failed",
            extra={"evidence_id": evidence_id, "file_path": str(file_path)},
        )

    meta["matchInvestigation"] = {
        "followed": link_result.followed_count,
        "skipped": link_result.skipped_count,
        "errors": link_result.errors[:5],
        "linked_drawing_ids": linked_drawing_ids,
        "drawing_ids_needing_index": drawing_ids_needing_index,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    evidence.meta = meta  # type: ignore[assignment]
    session.flush()

    extraction: DocumentExtraction | None = None
    try:
        extraction = run_document_extraction(
            session,
            file_id=str(evidence_id),
            content=payload.merged_text,
            classification_content=payload.base_text or None,
        )
    except Exception:
        logger.exception(
            "document_extraction_orchestrator_failed",
            extra={"evidence_id": evidence_id},
        )
        session.rollback()
        return EvidenceInvestigationPersistResult(
            linked_drawing_ids=linked_drawing_ids,
            extraction_id=None,
            survey_point_count=survey_point_count,
            drawing_ids_needing_index=drawing_ids_needing_index,
        )

    if extraction is not None:
        try:
            classify_and_persist_evidence_kind(
                session,
                evidence,
                document_type=str(extraction.document_type),
                file_path=file_path,
            )
            session.flush()
        except Exception:
            logger.exception(
                "evidence_kind_classification_failed",
                extra={"evidence_id": evidence_id, "file_path": str(file_path)},
            )

    extraction_id = cast(int | None, extraction.id) if extraction is not None else None
    return EvidenceInvestigationPersistResult(
        linked_drawing_ids=linked_drawing_ids,
        extraction_id=extraction_id,
        survey_point_count=survey_point_count,
        drawing_ids_needing_index=drawing_ids_needing_index,
    )
