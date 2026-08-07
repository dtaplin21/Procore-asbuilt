"""Master drawing OCR index pipeline.

Phase 2: extract positioned words from the drawing file and persist
``DrawingTextElement`` rows. Scale parsing and region building follow in
later phases.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import fitz  # PyMuPDF
from sqlalchemy.orm import Session

from ai.pipelines.document_text_extraction import (
    ExtractedDocument,
    PositionedWord,
    SourceFormat,
    extract_document,
)
from ai.pipelines.drawing_scale_parser import page_size_inches_from_points, parse_scale_from_words
from ai.pipelines.landmark_extractor import LandmarkRecord, extract_landmarks_from_page
from ai.pipelines.master_drawing_region_builder import build_auto_regions_from_text_elements
from ai.pipelines.sheet_orientation_detector import (
    detect_sheet_orientation,
    enrich_page_meta_with_orientation,
)
from ai.pipelines.survey_point_extractor import extract_survey_points_from_elements
from config import settings
from models.drawing_text_element import DrawingTextElement
from models.models import Drawing, DrawingRendition
from services.landmark_storage import persist_landmarks
from services.master_drawing_legend_tagger import enrich_text_elements_with_legend
from services.storage import open_storage_path
from services.survey_point_storage import persist_survey_points

_WHITESPACE_RE = re.compile(r"\s+")


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

    def to_stats_json(self) -> dict[str, Any]:
        return {
            "pages": self.pages,
            "text_elements": self.text_elements,
            "regions": self.regions,
            "survey_points": self.survey_points,
            "landmarks": self.landmarks,
            "scale_found": self.scale_found,
        }


def normalize_token_text(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text.strip()).lower()


def word_bbox_json(word: PositionedWord) -> dict[str, float]:
    x0, y0, x1, y1 = word.bbox.to_fractional()
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}


def element_source(source_format: SourceFormat) -> str:
    if source_format == SourceFormat.NATIVE_PDF:
        return "native_pdf"
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


def extract_drawing_document(file_path: Path) -> ExtractedDocument:
    document = extract_document(file_path)
    return _limit_extracted_document(document, _index_max_pages())


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
    source = element_source(source_format)
    rows: list[DrawingTextElement] = []
    for word in words:
        text = word.text.strip()
        if not text:
            continue
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

    extracted = extract_drawing_document(source_path)
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
    )
