"""Structured logs for linked install-sheet drawing registration."""

from __future__ import annotations

import logging
from typing import Any

from observability.location_match_logging import location_match_debug_enabled

logger = logging.getLogger("qcqa.linked_drawing")


def log_linked_drawing_registration_attempt(
    *,
    evidence_id: int,
    project_id: int,
    followed_count: int,
    skipped_count: int,
    fetched_pdf_count: int,
    supplemental_chars: int,
    link_errors: list[str] | None = None,
) -> None:
    logger.info(
        "linked_drawing_registration_attempt",
        extra={
            "evidence_id": evidence_id,
            "project_id": project_id,
            "followed_count": followed_count,
            "skipped_count": skipped_count,
            "fetched_pdf_count": fetched_pdf_count,
            "supplemental_chars": supplemental_chars,
            "link_errors": (link_errors or [])[:5],
        },
    )


def log_linked_drawing_registration_complete(
    *,
    evidence_id: int,
    project_id: int,
    registered_drawing_ids: list[int],
    deduped_drawing_ids: list[int],
) -> None:
    logger.info(
        "linked_drawing_registration_complete",
        extra={
            "evidence_id": evidence_id,
            "project_id": project_id,
            "registered_drawing_ids": registered_drawing_ids,
            "deduped_drawing_ids": deduped_drawing_ids,
            "registered_count": len(registered_drawing_ids),
            "deduped_count": len(deduped_drawing_ids),
        },
    )


def log_linked_drawing_fetch_capture(
    *,
    url: str,
    linked_filename: str,
    body_bytes: int,
    text_words: int,
    pages: int,
    captured: bool,
    skip_reason: str | None = None,
) -> None:
    extra: dict[str, Any] = {
        "url": url,
        "linked_filename": linked_filename,
        "body_bytes": body_bytes,
        "text_words": text_words,
        "pages": pages,
        "captured": captured,
        "skip_reason": skip_reason,
    }
    if captured:
        logger.info("linked_drawing_fetch_capture", extra=extra)
    elif location_match_debug_enabled():
        logger.debug("linked_drawing_fetch_capture", extra=extra)
    else:
        logger.info(
            "linked_drawing_fetch_skipped",
            extra=extra,
        )


def log_linked_drawing_skip(
    *,
    evidence_id: int | None,
    project_id: int,
    linked_filename: str,
    skip_reason: str,
    sheet_refs: list[str] | None = None,
    existing_drawing_id: int | None = None,
) -> None:
    logger.info(
        "linked_drawing_skip",
        extra={
            "evidence_id": evidence_id,
            "project_id": project_id,
            "linked_filename": linked_filename,
            "skip_reason": skip_reason,
            "sheet_refs": sheet_refs or [],
            "existing_drawing_id": existing_drawing_id,
        },
    )


def log_linked_drawing_registered(
    *,
    evidence_id: int | None,
    project_id: int,
    drawing_id: int,
    linked_filename: str,
    sheet_refs: list[str],
    storage_key: str | None = None,
) -> None:
    logger.info(
        "linked_drawing_registered",
        extra={
            "evidence_id": evidence_id,
            "project_id": project_id,
            "drawing_id": drawing_id,
            "linked_filename": linked_filename,
            "sheet_refs": sheet_refs,
            "storage_key": storage_key,
        },
    )
