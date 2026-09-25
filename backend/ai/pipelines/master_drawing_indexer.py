"""Master drawing OCR index pipeline.

Phase 2: extract positioned words from the drawing file and persist
``DrawingTextElement`` rows. Scale parsing and region building follow in
later phases.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import fitz  # PyMuPDF
from sqlalchemy.orm import Session

from ai.pipelines.document_ai_batch import extract_document_via_document_ai
from ai.pipelines.document_text_extraction import (
    ExtractedDocument,
    PositionedWord,
    SourceFormat,
    extract_document,
    extract_document_via_ocr,
)
from ai.pipelines.hybrid_text_merge import (
    OCR_SOURCE_DOCUMENT_AI,
    merge_native_and_ocr_words,
    merge_native_ocr_and_document_ai_words,
)
from ai.pipelines.drawing_scale_parser import page_size_inches_from_points, parse_scale_from_words
from ai.pipelines.landmark_extractor import LandmarkRecord, extract_landmarks_from_page
from ai.pipelines.master_drawing_region_builder import build_auto_regions_from_text_elements
from ai.pipelines.sheet_orientation_detector import (
    detect_sheet_orientation,
    enrich_page_meta_with_orientation,
)
from ai.pipelines.survey_point_extractor import extract_survey_points_from_elements
from config import document_ai_configured, settings
from models.drawing_text_element import DrawingTextElement
from models.models import Drawing, DrawingRendition
from services.landmark_storage import persist_landmarks
from services.master_drawing_legend_tagger import enrich_text_elements_with_legend
from services.storage import open_storage_path
from services.survey_point_storage import persist_survey_points

_WHITESPACE_RE = re.compile(r"\s+")
_READABLE_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+\-'.]{1,}$")
_LINKED_DRAWING_SOURCE = "linked_evidence"
_GARBLED_NATIVE_MIN_TOKENS = 20
_GARBLED_NATIVE_MAX_READABLE_RATIO = 0.35

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IndexResult:
    pages: int = 0
    text_elements: int = 0
    regions: int = 0
    survey_points: int = 0
    landmarks: int = 0
    scale_found: bool = False
    scale_json: dict[str, Any] | None = None
    page_meta_json: list[dict[str, Any]] | None = None
    document_ai_stats: dict[str, Any] | None = None

    def to_stats_json(self) -> dict[str, Any]:
        stats: dict[str, Any] = {
            "pages": self.pages,
            "text_elements": self.text_elements,
            "regions": self.regions,
            "survey_points": self.survey_points,
            "landmarks": self.landmarks,
            "scale_found": self.scale_found,
        }
        if self.document_ai_stats:
            stats["document_ai"] = self.document_ai_stats
            pages_processed = self.document_ai_stats.get("document_ai_pages_processed")
            if pages_processed is not None:
                stats["document_ai_pages_processed"] = pages_processed
        return stats


def normalize_token_text(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text.strip()).lower()


def word_bbox_json(word: PositionedWord) -> dict[str, float]:
    x0, y0, x1, y1 = word.bbox.to_fractional()
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}


def element_source(source_format: SourceFormat) -> str:
    if source_format == SourceFormat.NATIVE_PDF:
        return "native_pdf"
    if source_format == SourceFormat.HYBRID_PDF:
        return "hybrid_pdf"
    backend = settings.ocr_backend
    if backend == "openai_vision":
        return "openai_vision"
    return "tesseract"


def _ocr_token_source() -> str:
    if settings.document_ai_enabled and document_ai_configured():
        return OCR_SOURCE_DOCUMENT_AI
    backend = settings.ocr_backend
    if backend == "openai_vision":
        return "openai_vision"
    return "tesseract"


def _index_max_pages() -> int | None:
    cap = int(settings.drawing_index_ocr_max_pages)
    return cap if cap > 0 else None


def _limit_extracted_document(
    document: ExtractedDocument,
    max_pages: int | None,
) -> ExtractedDocument:
    if max_pages is None or max_pages <= 0 or document.page_count <= max_pages:
        return document
    filtered_words = [word for word in document.words if word.page_index < max_pages]
    return ExtractedDocument(
        source_format=document.source_format,
        page_count=max_pages,
        words=filtered_words,
    )


def _native_text_looks_garbled(document: ExtractedDocument) -> bool:
    """True when a native PDF text layer is mostly unreadable (common CAD exports)."""
    if document.source_format != SourceFormat.NATIVE_PDF:
        return False
    tokens = [word.text.strip() for word in document.words if word.text.strip()]
    if len(tokens) < _GARBLED_NATIVE_MIN_TOKENS:
        return False
    readable = sum(1 for token in tokens if _READABLE_TOKEN_RE.match(token))
    return (readable / len(tokens)) < _GARBLED_NATIVE_MAX_READABLE_RATIO


def _merge_native_and_ocr_documents(
    native: ExtractedDocument,
    ocr: ExtractedDocument,
) -> ExtractedDocument:
    page_count = max(native.page_count, ocr.page_count)
    merged_words = merge_native_and_ocr_words(
        native.words,
        ocr.words,
        ocr_source=_ocr_token_source(),
    )
    return ExtractedDocument(
        source_format=SourceFormat.HYBRID_PDF,
        page_count=page_count,
        words=merged_words,
    )


def _merge_native_document_ai_and_tesseract(
    native: ExtractedDocument,
    document_ai: ExtractedDocument,
    tesseract: ExtractedDocument,
) -> ExtractedDocument:
    page_count = max(
        native.page_count,
        document_ai.page_count,
        tesseract.page_count,
    )
    merged_words = merge_native_ocr_and_document_ai_words(
        native.words,
        document_ai.words,
        tesseract.words if tesseract.words else None,
    )
    return ExtractedDocument(
        source_format=SourceFormat.HYBRID_PDF,
        page_count=page_count,
        words=merged_words,
    )


def _use_document_ai_for_master_index() -> bool:
    if not settings.document_ai_enabled:
        return False
    if not document_ai_configured():
        logger.warning(
            "master_drawing_index_document_ai_enabled_but_not_configured",
            extra={"path": "extract_drawing_document"},
        )
        return False
    return True


def extract_drawing_document(
    file_path: Path,
    *,
    force_ocr: bool = False,
    document_ai_stats: dict[str, Any] | None = None,
    drawing_id: int | None = None,
    on_document_ai_batch_started: Any | None = None,
) -> ExtractedDocument:
    max_pages = _index_max_pages()
    if force_ocr:
        return _limit_extracted_document(
            extract_document_via_ocr(file_path, max_pages=max_pages),
            max_pages,
        )

    native = _limit_extracted_document(extract_document(file_path), max_pages)

    if _use_document_ai_for_master_index():
        document_ai = _limit_extracted_document(
            extract_document_via_document_ai(
                file_path,
                max_pages=max_pages,
                document_ai_stats=document_ai_stats,
                drawing_id=drawing_id,
                on_batch_started=on_document_ai_batch_started,
            ),
            max_pages,
        )
        tesseract = ExtractedDocument(
            source_format=SourceFormat.SCANNED_PDF,
            page_count=0,
            words=[],
        )
        if settings.document_ai_parallel_tesseract:
            tesseract = _limit_extracted_document(
                extract_document_via_ocr(file_path, max_pages=max_pages),
                max_pages,
            )
        if _native_text_looks_garbled(native):
            logger.info(
                "master_drawing_index_native_text_garbled_diagnostic",
                extra={
                    "path": str(file_path),
                    "native_tokens": len(native.words),
                    "document_ai_tokens": len(document_ai.words),
                    "tesseract_tokens": len(tesseract.words),
                },
            )
        return _merge_native_document_ai_and_tesseract(native, document_ai, tesseract)

    ocr = _limit_extracted_document(
        extract_document_via_ocr(file_path, max_pages=max_pages),
        max_pages,
    )
    if _native_text_looks_garbled(native):
        logger.info(
            "master_drawing_index_native_text_garbled_diagnostic",
            extra={
                "path": str(file_path),
                "native_tokens": len(native.words),
                "ocr_tokens": len(ocr.words),
            },
        )
    return _merge_native_and_ocr_documents(native, ocr)


def build_page_meta_json(
    session: Session,
    drawing_id: int,
    file_path: Path,
    *,
    page_count: int,
) -> list[dict[str, Any]]:
    renditions = (
        session.query(DrawingRendition)
        .filter(DrawingRendition.drawing_id == drawing_id)
        .order_by(DrawingRendition.page_number.asc())
        .all()
    )
    rendition_by_page = {
        cast(int, rendition.page_number): rendition for rendition in renditions
    }

    if file_path.suffix.lower() == ".pdf":
        doc = fitz.open(str(file_path))
        try:
            total_pages = min(doc.page_count, page_count)
            page_meta: list[dict[str, Any]] = []
            for page_index in range(total_pages):
                page = doc.load_page(page_index)
                page_number = page_index + 1
                rendition = rendition_by_page.get(page_number)
                width_pt = float(page.rect.width)
                height_pt = float(page.rect.height)
                page_width_in, page_height_in = page_size_inches_from_points(width_pt, height_pt)
                page_meta.append(
                    {
                        "page": page_number,
                        "width_pt": width_pt,
                        "height_pt": height_pt,
                        "page_width_in": page_width_in,
                        "page_height_in": page_height_in,
                        "width_px": cast(int | None, rendition.width_px if rendition else None),
                        "height_px": cast(int | None, rendition.height_px if rendition else None),
                        "rotation": int(page.rotation),
                    }
                )
            return page_meta
        finally:
            doc.close()

    rendition = rendition_by_page.get(1)
    return [
        {
            "page": 1,
            "width_pt": None,
            "height_pt": None,
            "width_px": cast(int | None, rendition.width_px if rendition else None),
            "height_px": cast(int | None, rendition.height_px if rendition else None),
            "rotation": 0,
        }
    ]


def enrich_page_meta_json_with_orientation(
    session: Session,
    drawing_id: int,
    page_meta_json: list[dict[str, Any]],
    text_elements: list[DrawingTextElement],
) -> list[dict[str, Any]]:
    renditions = (
        session.query(DrawingRendition)
        .filter(DrawingRendition.drawing_id == drawing_id)
        .order_by(DrawingRendition.page_number.asc())
        .all()
    )
    rendition_by_page = {
        cast(int, rendition.page_number): rendition for rendition in renditions
    }

    enriched_pages: list[dict[str, Any]] = []
    for page_meta in page_meta_json:
        page_number = int(page_meta["page"])
        rendition = rendition_by_page.get(page_number)
        rendition_path: Path | None = None
        if rendition is not None:
            storage_key = cast(str | None, rendition.image_storage_key)
            if storage_key:
                candidate = open_storage_path(storage_key)
                if candidate.exists():
                    rendition_path = candidate

        orientation = detect_sheet_orientation(
            page=page_number,
            page_meta=page_meta,
            text_elements=text_elements,
            rendition_png_path=rendition_path,
        )
        enriched_pages.append(enrich_page_meta_with_orientation(page_meta, orientation))

    return enriched_pages


def extract_landmarks_from_drawing_renditions(
    session: Session,
    drawing_id: int,
    page_meta_json: list[dict[str, Any]],
) -> list[LandmarkRecord]:
    renditions = (
        session.query(DrawingRendition)
        .filter(DrawingRendition.drawing_id == drawing_id)
        .order_by(DrawingRendition.page_number.asc())
        .all()
    )
    rendition_by_page = {
        cast(int, rendition.page_number): rendition for rendition in renditions
    }

    records: list[LandmarkRecord] = []
    for page_meta in page_meta_json:
        page_number = int(page_meta["page"])
        rendition = rendition_by_page.get(page_number)
        if rendition is None:
            continue
        storage_key = cast(str | None, rendition.image_storage_key)
        if not storage_key:
            continue
        png_path = open_storage_path(storage_key)
        if not png_path.exists():
            continue
        records.extend(
            extract_landmarks_from_page(
                png_path,
                page_meta,
                page=page_number,
            )
        )
    return records


def persist_text_elements(
    session: Session,
    drawing_id: int,
    words: list[PositionedWord],
    source_format: SourceFormat,
) -> int:
    default_source = element_source(source_format)
    rows: list[DrawingTextElement] = []
    for word in words:
        text = word.text.strip()
        if not text:
            continue
        source = word.token_source or default_source
        rows.append(
            DrawingTextElement(
                master_drawing_id=drawing_id,
                page=word.page_index + 1,
                text=text,
                text_normalized=normalize_token_text(text),
                bbox_json=word_bbox_json(word),
                ocr_confidence=float(word.ocr_confidence),
                source=source,
            )
        )

    if rows:
        session.add_all(rows)
        session.flush()
    return len(rows)


def index_master_drawing(drawing_id: int, session: Session) -> IndexResult:
    """Extract positioned OCR/text-layer words and persist drawing index rows."""
    drawing = session.get(Drawing, drawing_id)
    if drawing is None:
        raise ValueError(f"Drawing {drawing_id} not found")

    storage_key = cast(str | None, drawing.storage_key)
    if not storage_key:
        raise ValueError(f"Drawing {drawing_id} has no storage_key")

    source_path = open_storage_path(storage_key)
    if not source_path.exists():
        raise FileNotFoundError(f"Drawing source file not found: {source_path}")

    is_linked_evidence = cast(str | None, drawing.source) == _LINKED_DRAWING_SOURCE
    document_ai_stats: dict[str, Any] = {}
    drawing_id = cast(int, drawing.id)

    def _on_document_ai_batch_started(pending: dict[str, Any]) -> None:
        if not _use_document_ai_for_master_index():
            return
        from services.drawing_index_jobs import set_document_ai_pending

        set_document_ai_pending(session, drawing, pending)

    extracted = extract_drawing_document(
        source_path,
        force_ocr=is_linked_evidence,
        document_ai_stats=document_ai_stats,
        drawing_id=drawing_id if not is_linked_evidence else None,
        on_document_ai_batch_started=_on_document_ai_batch_started,
    )
    page_meta_json = build_page_meta_json(
        session,
        drawing_id,
        source_path,
        page_count=extracted.page_count,
    )
    text_elements = persist_text_elements(
        session,
        drawing_id,
        extracted.words,
        extracted.source_format,
    )

    enrich_text_elements_with_legend(
        session,
        drawing_id,
        cast(int, drawing.project_id),
    )

    regions = build_auto_regions_from_text_elements(session, drawing_id)

    first_page_meta = page_meta_json[0] if page_meta_json else None
    scale_json = parse_scale_from_words(
        extracted.words,
        page=1,
        page_meta=first_page_meta,
    )

    indexed_text_elements = (
        session.query(DrawingTextElement)
        .filter(DrawingTextElement.master_drawing_id == drawing_id)
        .all()
    )
    page_meta_json = enrich_page_meta_json_with_orientation(
        session,
        drawing_id,
        page_meta_json,
        indexed_text_elements,
    )
    survey_point_records = extract_survey_points_from_elements(
        indexed_text_elements,
        scale_json=scale_json,
        page_meta_json=page_meta_json,
        scale_source="master_index",
    )
    survey_points = persist_survey_points(
        session,
        drawing_id,
        survey_point_records,
        source="auto_index",
    )

    landmark_records = extract_landmarks_from_drawing_renditions(
        session,
        drawing_id,
        page_meta_json,
    )
    landmarks = persist_landmarks(
        session,
        drawing_id,
        landmark_records,
        source="auto_index",
    )

    return IndexResult(
        pages=extracted.page_count,
        text_elements=text_elements,
        regions=regions,
        survey_points=survey_points,
        landmarks=landmarks,
        scale_found=scale_json is not None,
        scale_json=scale_json,
        page_meta_json=page_meta_json,
        document_ai_stats=document_ai_stats or None,
    )
