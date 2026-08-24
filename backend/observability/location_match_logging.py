"""Structured logs for inspection location-match debugging."""

from __future__ import annotations

import logging
import os
from typing import Any, Sequence

logger = logging.getLogger("qcqa.location_match")


def location_match_debug_enabled() -> bool:
    """When true, emit extra DEBUG detail alongside standard match trace INFO logs."""
    raw = os.getenv("LOCATION_MATCH_DEBUG", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _round_bbox(
    bbox: tuple[float, float, float, float] | None,
) -> list[float] | None:
    if bbox is None:
        return None
    return [round(float(v), 4) for v in bbox]


def serialize_method_candidate(candidate: Any) -> dict[str, Any]:
    """JSON-safe summary of a MethodCandidate (or compatible object)."""
    method = getattr(candidate, "method", None)
    method_value = method.value if method is not None and hasattr(method, "value") else str(method)
    bbox = getattr(candidate, "bbox_fractional", None)
    return {
        "method": method_value,
        "confidence": round(float(getattr(candidate, "confidence", 0.0)), 4),
        "bbox": _round_bbox(bbox),
        "page": int(getattr(candidate, "page", 1)),
        "region_id": getattr(candidate, "region_id", None),
        "source_drawing_id": getattr(candidate, "source_drawing_id", None),
        "notes": str(getattr(candidate, "notes", "") or ""),
    }


def serialize_location_result(result: Any) -> dict[str, Any]:
    """JSON-safe summary of a LocationMatchResult."""
    method = getattr(result, "method", None)
    method_value = method.value if method is not None and hasattr(method, "value") else str(method)
    return {
        "method": method_value,
        "confidence": round(float(getattr(result, "confidence", 0.0)), 4),
        "bbox": _round_bbox(getattr(result, "bbox_fractional", None)),
        "page": int(getattr(result, "page", 1)),
        "region_id": getattr(result, "region_id", None),
        "notes": str(getattr(result, "notes", "") or ""),
    }


def log_inspection_match_started(
    *,
    evidence_id: int,
    master_drawing_id: int,
    page: int,
    inspection_run_id: int | None = None,
    project_id: int | None = None,
    job_id: int | None = None,
) -> None:
    logger.info(
        "inspection_match_started",
        extra={
            "evidence_id": evidence_id,
            "inspection_id": str(evidence_id),
            "master_drawing_id": master_drawing_id,
            "drawing_id": master_drawing_id,
            "page": page,
            "inspection_run_id": inspection_run_id,
            "project_id": project_id,
            "job_id": job_id,
        },
    )


def log_inspection_match_candidates(
    *,
    evidence_id: int,
    master_drawing_id: int,
    candidates: Sequence[Any],
    match_detail: dict[str, Any],
    inspection_run_id: int | None = None,
) -> None:
    serialized = [serialize_method_candidate(c) for c in candidates]
    extra: dict[str, Any] = {
        "evidence_id": evidence_id,
        "inspection_id": str(evidence_id),
        "master_drawing_id": master_drawing_id,
        "drawing_id": master_drawing_id,
        "inspection_run_id": inspection_run_id,
        "candidate_count": len(serialized),
        "candidates": serialized,
        "match_detail": match_detail,
    }
    logger.info("inspection_match_candidates", extra=extra)
    if location_match_debug_enabled():
        logger.debug("inspection_match_candidates_detail", extra=extra)


def log_inspection_match_result(
    *,
    evidence_id: int,
    master_drawing_id: int,
    result: Any,
    match_status: str,
    inspection_run_id: int | None = None,
) -> None:
    payload = serialize_location_result(result)
    logger.info(
        "inspection_match_result",
        extra={
            "evidence_id": evidence_id,
            "inspection_id": str(evidence_id),
            "master_drawing_id": master_drawing_id,
            "drawing_id": master_drawing_id,
            "inspection_run_id": inspection_run_id,
            "match_status": match_status,
            "match_method": payload["method"],
            "confidence": payload["confidence"],
            "bbox": payload["bbox"],
            "page": payload["page"],
            "region_id": payload.get("region_id"),
            "notes": payload.get("notes"),
            "match_detail": payload,
        },
    )


def log_inspection_match_persisted(
    *,
    evidence_id: int,
    master_drawing_id: int,
    match_status: str,
    overlay_id: int | None,
    bbox: tuple[float, float, float, float] | None,
    page: int,
    inspection_run_id: int | None = None,
    region_id: int | None = None,
) -> None:
    logger.info(
        "inspection_match_persisted",
        extra={
            "evidence_id": evidence_id,
            "inspection_id": str(evidence_id),
            "master_drawing_id": master_drawing_id,
            "drawing_id": master_drawing_id,
            "inspection_run_id": inspection_run_id,
            "match_status": match_status,
            "overlay_id": overlay_id,
            "bbox": _round_bbox(bbox),
            "page": page,
            "region_id": region_id,
        },
    )


def log_inspection_investigation_complete(
    *,
    evidence_id: int,
    master_drawing_id: int,
    investigation_meta: dict[str, Any] | None,
    inspection_run_id: int | None = None,
) -> None:
    raw = investigation_meta if isinstance(investigation_meta, dict) else {}
    match_investigation = raw.get("matchInvestigation")
    if not isinstance(match_investigation, dict):
        match_investigation = {}
    logger.info(
        "inspection_investigation_complete",
        extra={
            "evidence_id": evidence_id,
            "inspection_id": str(evidence_id),
            "master_drawing_id": master_drawing_id,
            "drawing_id": master_drawing_id,
            "inspection_run_id": inspection_run_id,
            "links_followed": raw.get("links_followed", match_investigation.get("followed")),
            "pages_rendered": raw.get("pages_rendered"),
            "linked_drawing_ids": match_investigation.get("linked_drawing_ids"),
            "investigated_at": match_investigation.get("at"),
            "match_investigation": match_investigation,
        },
    )


def log_inspection_upload_match_summary(
    *,
    evidence_id: int,
    project_id: int,
    master_drawing_id: int,
    inspection_run_id: int,
    master_index_ready: bool,
    master_index_status: str | None,
    match_job_id: int | None = None,
    match_deferred: bool = False,
    index_status: str | None = None,
    region_count: int | None = None,
) -> None:
    logger.info(
        "inspection_upload_match_summary",
        extra={
            "evidence_id": evidence_id,
            "inspection_id": str(evidence_id),
            "project_id": project_id,
            "master_drawing_id": master_drawing_id,
            "drawing_id": master_drawing_id,
            "inspection_run_id": inspection_run_id,
            "master_index_ready": master_index_ready,
            "master_index_status": master_index_status,
            "match_job_id": match_job_id,
            "match_deferred": match_deferred,
            "index_status": index_status,
            "region_count": region_count,
        },
    )
