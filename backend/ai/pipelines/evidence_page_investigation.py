"""Per-page text extraction for evidence link investigation (master-index aligned)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import fitz

from ai.pipelines.document_text_extraction import ExtractedDocument
from ai.pipelines.master_drawing_indexer import extract_drawing_document_for_inspection
from ai.pipelines.survey_point_extractor import (
    extract_stations_from_text,
    extract_survey_points_from_plain_text,
)
from config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PageInvestigationResult:
    page: int  # 1-based
    ocr_text: str
    vision_text: str
    combined_text: str
    ocr_word_count: int
    vision_word_count: int


def link_follow_ocr_max_pages() -> int | None:
    """Deprecated: inspection extraction uses ``drawing_index_ocr_max_pages`` via master indexer."""
    from ai.pipelines.master_drawing_indexer import drawing_index_max_pages

    return drawing_index_max_pages()


def page_vision_enabled() -> bool:
    return bool(getattr(settings, "pdf_link_follow_page_vision_enabled", True))


def _vision_text_for_pdf_page(pdf_path: Path, *, page_1based: int) -> str:
    if not page_vision_enabled():
        return ""
    png_path: Path | None = None
    try:
        png_path = _render_page_png(pdf_path, page_1based=page_1based)
        from ai.pipelines.openai_vision import extract_plain_text_from_image

        return extract_plain_text_from_image(file_path=png_path).strip()
    except Exception:
        logger.exception(
            "evidence_page_vision_failed",
            extra={"pdf_path": str(pdf_path), "page": page_1based},
        )
        return ""
    finally:
        if png_path is not None:
            png_path.unlink(missing_ok=True)


def _render_page_png(pdf_path: Path, *, page_1based: int, dpi: int = 200) -> Path:
    import tempfile

    doc = fitz.open(str(pdf_path))
    try:
        page_index = max(page_1based - 1, 0)
        if page_index >= doc.page_count:
            page_index = doc.page_count - 1
        pdf_page = doc.load_page(page_index)
        pixmap = pdf_page.get_pixmap(dpi=dpi, alpha=False)
        temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        temp_file.write(pixmap.tobytes("png"))
        temp_file.close()
        return Path(temp_file.name)
    finally:
        doc.close()


def _combine_page_text(*, ocr_text: str, vision_text: str) -> str:
    parts: list[str] = []
    if ocr_text.strip():
        parts.append(ocr_text.strip())
    if vision_text.strip():
        if ocr_text.strip() and vision_text.strip() not in ocr_text:
            parts.append(vision_text.strip())
        elif not ocr_text.strip():
            parts.append(vision_text.strip())
    return "\n".join(parts).strip()


def _page_result_from_ocr_and_vision(
    *,
    page_1based: int,
    ocr_text: str,
    vision_text: str,
) -> PageInvestigationResult:
    combined = _combine_page_text(ocr_text=ocr_text, vision_text=vision_text)
    return PageInvestigationResult(
        page=page_1based,
        ocr_text=ocr_text,
        vision_text=vision_text,
        combined_text=combined,
        ocr_word_count=len(ocr_text.split()),
        vision_word_count=len(vision_text.split()),
    )


def extract_inspection_document(
    pdf_path: Path,
    *,
    drawing_id: int | None = None,
) -> ExtractedDocument:
    """Run the master drawing extraction stack on an inspection PDF (every page)."""
    return extract_drawing_document_for_inspection(pdf_path, drawing_id=drawing_id)


def investigate_pdf_page(
    pdf_path: Path,
    *,
    page: int = 1,
    document: ExtractedDocument | None = None,
) -> PageInvestigationResult:
    page_1based = max(int(page), 1)
    page_index_0 = page_1based - 1
    extracted = document if document is not None else extract_inspection_document(pdf_path)
    ocr_text = ""
    if 0 <= page_index_0 < extracted.page_count:
        ocr_text = extracted.page_text(page_index_0).strip()
    vision_text = _vision_text_for_pdf_page(pdf_path, page_1based=page_1based)
    return _page_result_from_ocr_and_vision(
        page_1based=page_1based,
        ocr_text=ocr_text,
        vision_text=vision_text,
    )


def investigate_pdf_all_pages(
    pdf_path: Path,
    *,
    drawing_id: int | None = None,
) -> tuple[tuple[PageInvestigationResult, ...], ExtractedDocument]:
    document = extract_inspection_document(pdf_path, drawing_id=drawing_id)
    results: list[PageInvestigationResult] = []
    from services.inspection_run_progress import get_inspection_progress

    progress = get_inspection_progress()
    for page_index in range(document.page_count):
        page_1based = page_index + 1
        if progress is not None:
            progress.set_reading_page(page_1based, document.page_count)
        ocr_text = document.page_text(page_index).strip()
        vision_text = _vision_text_for_pdf_page(pdf_path, page_1based=page_1based)
        results.append(
            _page_result_from_ocr_and_vision(
                page_1based=page_1based,
                ocr_text=ocr_text,
                vision_text=vision_text,
            )
        )
    return tuple(results), document


def survey_hints_from_text(text: str, *, page: int) -> dict[str, object]:
    stations = extract_stations_from_text(text)
    survey_points = extract_survey_points_from_plain_text(
        text,
        page=page,
        scale_source="page_investigation",
    )
    coordinate_pairs = [
        {
            "northing": point.northing,
            "easting": point.easting,
            "station": point.station,
        }
        for point in survey_points
    ]
    return {
        "stations": sorted(set(stations)),
        "coordinate_pairs": coordinate_pairs,
    }


def page_investigation_to_meta(result: PageInvestigationResult, *, source: str) -> dict[str, object]:
    return {
        "source": source,
        "page": result.page,
        "ocr_word_count": result.ocr_word_count,
        "vision_word_count": result.vision_word_count,
        "combined_word_count": len(result.combined_text.split()),
        "pipeline": "master_index" if settings.inspection_index_align_with_master else "ocr_only",
    }
