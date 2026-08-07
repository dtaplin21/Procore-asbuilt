"""Classify evidence into coarse kinds for location-match routing."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, cast

from sqlalchemy.orm import Session

from ai.pipelines.document_text_extraction import ExtractedDocument, SourceFormat, extract_document
from ai.schemas.document_extraction_schemas import DocumentType
from models.models import EvidenceRecord
from services.evidence_survey_extraction import load_linked_drawings

MIN_NATIVE_PAGE1_WORDS = 50


class EvidenceKind(str, Enum):
    DRAWING_SCAN = "drawing_scan"
    PHOTO = "photo"
    FORM = "form"


_DOCUMENT_TYPE_TO_KIND: dict[str, EvidenceKind] = {
    DocumentType.FIELD_PHOTO.value: EvidenceKind.PHOTO,
    DocumentType.MASTER_DRAWING.value: EvidenceKind.DRAWING_SCAN,
    DocumentType.INSPECTION_REPORT.value: EvidenceKind.FORM,
    DocumentType.UNKNOWN.value: EvidenceKind.FORM,
}


def native_page1_word_count(document: ExtractedDocument) -> int:
    """Count positioned words on page 1 from a native PDF text layer."""
    if document.source_format != SourceFormat.NATIVE_PDF:
        return 0
    return sum(
        1 for word in document.words if word.page_index == 0 and word.text.strip()
    )


def count_native_page1_words(file_path: str | Path) -> int:
    return native_page1_word_count(extract_document(file_path))


def has_linked_install_sheet(session: Session, evidence_id: int) -> bool:
    return bool(load_linked_drawings(session, evidence_id))


def classify_evidence_kind(
    document_type: str,
    *,
    has_linked_sheet: bool = False,
    native_page1_words: int = 0,
) -> EvidenceKind:
    """Map document type to evidence kind, with drawing-scan overrides."""
    base_kind = _DOCUMENT_TYPE_TO_KIND.get(document_type.lower(), EvidenceKind.FORM)
    if has_linked_sheet or native_page1_words >= MIN_NATIVE_PAGE1_WORDS:
        return EvidenceKind.DRAWING_SCAN
    return base_kind


def contour_matching_enabled(kind: EvidenceKind) -> bool:
    """Contour fallback runs only for drawing scans."""
    return kind == EvidenceKind.DRAWING_SCAN


def persist_evidence_kind_meta(evidence: EvidenceRecord, kind: EvidenceKind) -> None:
    meta = dict(cast(dict[str, Any] | None, evidence.meta) or {})
    meta["evidence_kind"] = kind.value
    evidence.meta = meta  # type: ignore[assignment]


def classify_and_persist_evidence_kind(
    session: Session,
    evidence: EvidenceRecord,
    *,
    document_type: str,
    file_path: str | Path,
) -> EvidenceKind:
    kind = classify_evidence_kind(
        document_type,
        has_linked_sheet=has_linked_install_sheet(session, cast(int, evidence.id)),
        native_page1_words=count_native_page1_words(file_path),
    )
    persist_evidence_kind_meta(evidence, kind)
    return kind
