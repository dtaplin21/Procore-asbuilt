"""Register linked install-sheet PDFs as auxiliary project drawings."""

from __future__ import annotations

import logging
from typing import cast

from sqlalchemy.orm import Session

from ai.pipelines.pdf_link_follower import FetchedLinkedPdf, LinkFollowResult
from observability.linked_drawing_logging import (
    log_linked_drawing_registered,
    log_linked_drawing_registration_attempt,
    log_linked_drawing_registration_complete,
    log_linked_drawing_skip,
)
from services.drawing_render_jobs import enqueue_drawing_render_job
from services.evidence_linking import extract_sheet_refs, find_project_drawings_for_refs
from services.file_storage import save_upload_from_bytes
from services.storage import StorageService

logger = logging.getLogger(__name__)

_LINKED_DRAWING_SOURCE = "linked_evidence"
_SHEET_REF_TEXT_PREVIEW_CHARS = 8_000


def _sheet_refs_for_linked_pdf(fetched: FetchedLinkedPdf) -> list[str]:
    refs = extract_sheet_refs(fetched.filename)
    if refs:
        return refs
    preview = fetched.text[:_SHEET_REF_TEXT_PREVIEW_CHARS] if fetched.text else ""
    return extract_sheet_refs(preview)


def register_linked_pdfs_as_auxiliary_drawings(
    session: Session,
    *,
    project_id: int,
    link_result: LinkFollowResult,
    evidence_id: int | None = None,
    commit: bool = False,
) -> list[int]:
    """Persist followed PDF attachments as auxiliary drawings and enqueue render/index."""
    log_linked_drawing_registration_attempt(
        evidence_id=evidence_id or 0,
        project_id=project_id,
        followed_count=link_result.followed_count,
        skipped_count=link_result.skipped_count,
        fetched_pdf_count=len(link_result.fetched_pdfs),
        supplemental_chars=len(link_result.supplemental_text),
        link_errors=link_result.errors,
    )

    if not link_result.fetched_pdfs:
        log_linked_drawing_skip(
            evidence_id=evidence_id,
            project_id=project_id,
            linked_filename="",
            skip_reason="empty_fetched_pdfs",
        )
        return []

    storage = StorageService(session)
    drawing_ids: list[int] = []
    registered_ids: list[int] = []
    deduped_ids: list[int] = []

    for fetched in link_result.fetched_pdfs:
        if not fetched.body:
            log_linked_drawing_skip(
                evidence_id=evidence_id,
                project_id=project_id,
                linked_filename=fetched.filename,
                skip_reason="empty_pdf_body",
            )
            continue

        refs = _sheet_refs_for_linked_pdf(fetched)
        if not refs:
            log_linked_drawing_skip(
                evidence_id=evidence_id,
                project_id=project_id,
                linked_filename=fetched.filename,
                skip_reason="no_sheet_ref",
            )
            continue

        existing = find_project_drawings_for_refs(session, project_id, refs)
        if existing:
            existing_id = int(existing[0]["drawing_id"])
            drawing_ids.append(existing_id)
            deduped_ids.append(existing_id)
            log_linked_drawing_skip(
                evidence_id=evidence_id,
                project_id=project_id,
                linked_filename=fetched.filename,
                skip_reason="existing_drawing",
                sheet_refs=refs,
                existing_drawing_id=existing_id,
            )
            continue

        storage_key = save_upload_from_bytes(
            fetched.body,
            project_id,
            category="linked_drawings",
            content_type=fetched.content_type or "application/pdf",
            original_name=fetched.filename,
        )
        drawing = storage.create_auxiliary_drawing(
            project_id=project_id,
            source=_LINKED_DRAWING_SOURCE,
            name=fetched.filename,
            storage_key=storage_key,
            content_type=fetched.content_type or "application/pdf",
            original_filename=fetched.filename,
            page_count=fetched.pages or None,
        )
        drawing_id = cast(int, drawing.id)
        drawing_ids.append(drawing_id)
        registered_ids.append(drawing_id)

        try:
            enqueue_drawing_render_job(session, project_id, drawing_id)
        except Exception:
            logger.exception(
                "linked_drawing_render_enqueue_failed",
                extra={"project_id": project_id, "drawing_id": drawing_id},
            )

        log_linked_drawing_registered(
            evidence_id=evidence_id,
            project_id=project_id,
            drawing_id=drawing_id,
            linked_filename=fetched.filename,
            sheet_refs=refs,
            storage_key=storage_key,
        )

    log_linked_drawing_registration_complete(
        evidence_id=evidence_id or 0,
        project_id=project_id,
        registered_drawing_ids=registered_ids,
        deduped_drawing_ids=deduped_ids,
    )

    if commit:
        session.commit()
    else:
        session.flush()

    return drawing_ids
