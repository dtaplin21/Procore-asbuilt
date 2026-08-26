"""Persist match-time PDF investigation results (linked drawings, clues, survey)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from sqlalchemy.orm import Session, object_session

from ai.agents.tools.pdf_investigation import EvidenceInvestigationPayload
from ai.pipelines.document_extraction_orchestrator import run_document_extraction
from ai.pipelines.evidence_kind_classifier import classify_and_persist_evidence_kind
from ai.pipelines.registration_from_survey import (
    compute_registration_for_linked_drawings,
    registration_transform_to_meta,
)
from ai.pipelines.station_range_extractor import (
    StationRangeResult,
    extract_station_range_for_drawings,
)
from models.document_clue import DocumentClue
from models.document_extraction import DocumentExtraction
from models.inspection_run import InspectionRun
from models.models import Drawing, EvidenceRecord, JobQueue, Project
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


def _apply_station_range_to_evidence(
    evidence: EvidenceRecord,
    station_range: StationRangeResult,
) -> None:
    if not station_range.station_from or not station_range.station_to:
        return

    meta = dict(cast(dict[str, Any] | None, evidence.meta) or {})
    meta["station_from"] = station_range.station_from
    meta["station_to"] = station_range.station_to
    if station_range.station_from_bbox_json is not None:
        meta["station_from_bbox_json"] = station_range.station_from_bbox_json
    if station_range.station_to_bbox_json is not None:
        meta["station_to_bbox_json"] = station_range.station_to_bbox_json
    if station_range.source_drawing_id is not None:
        meta["station_range_source_drawing_id"] = station_range.source_drawing_id
    evidence.meta = meta  # type: ignore[assignment]


def _persist_station_range_clues(
    session: Session,
    *,
    extraction_id: int,
    station_range: StationRangeResult,
) -> None:
    if not station_range.station_from or not station_range.station_to:
        return

    session.query(DocumentClue).filter(
        DocumentClue.document_extraction_id == extraction_id,
        DocumentClue.clue_type.in_(("station_from", "station_to")),
        DocumentClue.source == "aux_station_ocr",
    ).delete(synchronize_session=False)

    for clue_type, value in (
        ("station_from", station_range.station_from),
        ("station_to", station_range.station_to),
    ):
        session.add(
            DocumentClue(
                document_extraction_id=extraction_id,
                clue_type=clue_type,
                clue_value=value,
                source="aux_station_ocr",
                confidence=0.85,
            )
        )


def _resolve_master_drawing_id(
    session: Session,
    *,
    evidence: EvidenceRecord,
) -> int | None:
    run = (
        session.query(InspectionRun)
        .filter(InspectionRun.evidence_id == evidence.id)
        .order_by(InspectionRun.id.desc())
        .first()
    )
    if run is not None and run.master_drawing_id is not None:
        return int(run.master_drawing_id)

    project = session.get(Project, evidence.project_id)
    if project is not None and project.master_drawing_id is not None:
        return int(project.master_drawing_id)
    return None


def _apply_registration_transform_to_evidence(
    evidence: EvidenceRecord,
    *,
    linked_drawing_ids: list[int],
    master_drawing_id: int,
    session: Session,
) -> None:
    transform, control_point_count, aux_drawing_id = compute_registration_for_linked_drawings(
        session,
        linked_drawing_ids=linked_drawing_ids,
        master_drawing_id=master_drawing_id,
    )
    if transform is None:
        return

    meta = dict(cast(dict[str, Any] | None, evidence.meta) or {})
    meta["registration_transform"] = registration_transform_to_meta(
        transform,
        control_point_count=control_point_count,
        aux_drawing_id=aux_drawing_id,
    )
    evidence.meta = meta  # type: ignore[assignment]


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

    station_range = StationRangeResult(station_from=None, station_to=None)
    if linked_drawing_ids:
        try:
            station_range = extract_station_range_for_drawings(
                session,
                linked_drawing_ids,
            )
            _apply_station_range_to_evidence(evidence, station_range)
            session.flush()
        except Exception:
            logger.exception(
                "aux_station_range_extraction_failed",
                extra={
                    "evidence_id": evidence_id,
                    "linked_drawing_ids": linked_drawing_ids,
                },
            )

    master_drawing_id = _resolve_master_drawing_id(session, evidence=evidence)
    if linked_drawing_ids and master_drawing_id is not None:
        try:
            _apply_registration_transform_to_evidence(
                evidence,
                linked_drawing_ids=linked_drawing_ids,
                master_drawing_id=master_drawing_id,
                session=session,
            )
            session.flush()
        except Exception:
            logger.exception(
                "registration_transform_compute_failed",
                extra={
                    "evidence_id": evidence_id,
                    "master_drawing_id": master_drawing_id,
                    "linked_drawing_ids": linked_drawing_ids,
                },
            )

    meta = dict(cast(dict[str, Any] | None, evidence.meta) or {})
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

        if (
            station_range.station_from
            and station_range.station_to
            and object_session(extraction) is session
        ):
            try:
                _persist_station_range_clues(
                    session,
                    extraction_id=cast(int, extraction.id),
                    station_range=station_range,
                )
                session.flush()
            except Exception:
                logger.exception(
                    "aux_station_range_clue_persist_failed",
                    extra={"evidence_id": evidence_id, "extraction_id": extraction.id},
                )

    extraction_id = cast(int | None, extraction.id) if extraction is not None else None
    return EvidenceInvestigationPersistResult(
        linked_drawing_ids=linked_drawing_ids,
        extraction_id=extraction_id,
        survey_point_count=survey_point_count,
        drawing_ids_needing_index=drawing_ids_needing_index,
    )
