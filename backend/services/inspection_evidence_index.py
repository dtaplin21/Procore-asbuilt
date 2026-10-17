"""Index the inspection evidence PDF with the same pipeline as master drawings."""

from __future__ import annotations

import logging
from typing import Any, cast

import fitz
from sqlalchemy.orm import Session

from models.models import Drawing, EvidenceRecord
from services.drawing_index_jobs import (
    INSPECTION_INDEXABLE_SOURCES,
    index_inspection_attachment_drawing_sync,
)
from services.storage import StorageService, open_storage_path

logger = logging.getLogger(__name__)

INSPECTION_EVIDENCE_SOURCE = "inspection_evidence"
_META_DRAWING_ID_KEY = "inspection_source_drawing_id"


def _page_count_for_storage_key(storage_key: str) -> int | None:
    path = open_storage_path(storage_key)
    if not path.exists() or path.suffix.lower() != ".pdf":
        return None
    doc = fitz.open(str(path))
    try:
        return int(doc.page_count)
    finally:
        doc.close()


def ensure_inspection_evidence_drawing_indexed(
    session: Session,
    *,
    evidence: EvidenceRecord,
    project_id: int,
    force: bool = False,
) -> int | None:
    """Create (if needed) an auxiliary drawing for the evidence PDF and run master index."""
    meta = dict(cast(dict[str, Any] | None, evidence.meta) or {})
    existing_id = meta.get(_META_DRAWING_ID_KEY)
    if existing_id is not None:
        try:
            drawing_id = int(existing_id)
        except (TypeError, ValueError):
            drawing_id = 0
        if drawing_id > 0 and session.get(Drawing, drawing_id) is not None:
            index_inspection_attachment_drawing_sync(session, drawing_id, force=force)
            return drawing_id

    storage_key = cast(str | None, evidence.storage_key)
    if not storage_key:
        return None

    path = open_storage_path(storage_key)
    if not path.exists():
        logger.warning(
            "inspection_evidence_index_missing_file",
            extra={"evidence_id": evidence.id, "storage_key": storage_key},
        )
        return None

    page_count = _page_count_for_storage_key(storage_key)
    storage = StorageService(session)
    title = str(evidence.title or f"Evidence {evidence.id}")
    drawing = storage.create_auxiliary_drawing(
        project_id=project_id,
        source=INSPECTION_EVIDENCE_SOURCE,
        name=title,
        storage_key=storage_key,
        content_type=str(evidence.content_type or "application/pdf"),
        original_filename=f"evidence-{evidence.id}.pdf",
        page_count=page_count,
    )
    drawing.processing_status = "ready"  # type: ignore[assignment]
    session.flush()

    drawing_id = cast(int, drawing.id)
    meta[_META_DRAWING_ID_KEY] = drawing_id
    evidence.meta = meta  # type: ignore[assignment]
    session.flush()

    index_inspection_attachment_drawing_sync(session, drawing_id, force=force)
    logger.info(
        "inspection_evidence_drawing_indexed",
        extra={
            "evidence_id": evidence.id,
            "drawing_id": drawing_id,
            "page_count": page_count,
        },
    )
    return drawing_id
