"""PDF investigation tools — open links and view pages within PDFs."""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fitz

from ai.agents.evidence_dossier import LinkedAttachmentSummary
from ai.pipelines.document_text_extraction import extract_document
from ai.pipelines.pdf_link_follower import (
    FetchedLinkedPdf,
    LinkFollowResult,
    PdfHyperlink,
    PdfLinkKind,
    extract_pdf_hyperlinks,
    follow_pdf_links,
)
from ai.pipelines.positioned_term_extractor import extract_positioned_terms
from ai.pipelines.survey_point_extractor import (
    extract_stations_from_text,
    extract_survey_points_from_plain_text,
)

logger = logging.getLogger(__name__)

_TEXT_PREVIEW_CHARS = 500
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


def _merge_evidence_text(base_text: str, link_result: LinkFollowResult) -> str:
    """Linked supplemental content first, then base — same order as upload merge."""
    base = base_text.strip()
    if link_result.supplemental_text.strip():
        return f"{link_result.supplemental_text}\n{base}".strip()
    return base


@dataclass(frozen=True)
class EvidenceInvestigationPayload:
    link_result: LinkFollowResult
    merged_text: str
    base_text: str
    summaries: tuple[LinkedAttachmentSummary, ...]
    links_followed: int
    pages_rendered: int
    ocr_word_counts: dict[str, int]
    errors: tuple[str, ...]


# Backward-compatible alias for callers that only need investigation summaries.
PdfInvestigationResult = EvidenceInvestigationPayload


@dataclass(frozen=True)
class RenderedPdfPage:
    page: int  # 1-based
    png_path: Path
    width_pt: float | None
    height_pt: float | None


def list_pdf_hyperlinks(file_path: Path) -> list[PdfHyperlink]:
    """List deduplicated hyperlinks embedded in a PDF."""
    return extract_pdf_hyperlinks(file_path)


def follow_and_capture_links(file_path: Path) -> LinkFollowResult:
    """Follow hyperlinks and capture supplemental text + fetched PDF bodies."""
    return follow_pdf_links(file_path)


def render_pdf_page(pdf_path: Path, *, page: int = 1, dpi: int = 200) -> RenderedPdfPage:
    """Render one PDF page (or pass-through image files) to a temporary PNG."""
    suffix = pdf_path.suffix.lower()
    if suffix in _IMAGE_SUFFIXES:
        return RenderedPdfPage(
            page=page,
            png_path=pdf_path,
            width_pt=None,
            height_pt=None,
        )

    doc = fitz.open(str(pdf_path))
    try:
        page_index = max(page - 1, 0)
        if page_index >= doc.page_count:
            page_index = 0
        pdf_page = doc.load_page(page_index)
        pixmap = pdf_page.get_pixmap(dpi=dpi, alpha=False)
        temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        temp_file.write(pixmap.tobytes("png"))
        temp_file.close()
        return RenderedPdfPage(
            page=page_index + 1,
            png_path=Path(temp_file.name),
            width_pt=float(pdf_page.rect.width),
            height_pt=float(pdf_page.rect.height),
        )
    finally:
        doc.close()


def extract_page_clues(pdf_path: Path, *, page: int = 1) -> dict[str, Any]:
    """Extract text and location hints from one page of a PDF or image."""
    document = extract_document(pdf_path)
    page_index = max(page - 1, 0)
    if page_index >= document.page_count:
        page_index = 0

    page_words = [word for word in document.words if word.page_index == page_index]
    page_text = document.page_text(page_index)
    positioned_terms = extract_positioned_terms(document)
    page_terms = [term for term in positioned_terms if term.page_index == page_index]

    survey_points = extract_survey_points_from_plain_text(
        page_text,
        page=page_index + 1,
        scale_source="pdf_investigation",
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
        "text": page_text,
        "word_count": len(page_words),
        "positioned_term_count": len(page_terms),
        "survey_hints": {
            "stations": extract_stations_from_text(page_text),
            "coordinate_pairs": coordinate_pairs,
        },
    }


def _text_preview(text: str) -> str:
    stripped = text.strip()
    if len(stripped) <= _TEXT_PREVIEW_CHARS:
        return stripped
    return stripped[:_TEXT_PREVIEW_CHARS]


def _summary_from_fetched(
    fetched: FetchedLinkedPdf,
) -> tuple[LinkedAttachmentSummary, int]:
    preview = _text_preview(fetched.text)
    word_count = len(fetched.text.split())
    if fetched.body:
        temp_path = _write_pdf_bytes(fetched.body, filename_hint=fetched.filename)
        try:
            clues = extract_page_clues(temp_path, page=1)
            page_text = str(clues.get("text", "") or "")
            word_count = int(clues.get("word_count", word_count))
            if page_text.strip():
                preview = _text_preview(page_text)
        except Exception:
            logger.exception(
                "pdf_investigation_fetched_clue_extract_failed",
                extra={"url": fetched.url, "filename": fetched.filename},
            )
        finally:
            temp_path.unlink(missing_ok=True)

    summary = LinkedAttachmentSummary(
        url=fetched.url,
        filename=fetched.filename,
        page_count=fetched.pages,
        text_preview=preview,
        drawing_id=None,
    )
    return summary, word_count


def _summary_from_internal_page(
    file_path: Path,
    *,
    target_page: int,
) -> tuple[LinkedAttachmentSummary, int]:
    page_num = target_page + 1
    clues = extract_page_clues(file_path, page=page_num)
    word_count = int(clues.get("word_count", 0))
    summary = LinkedAttachmentSummary(
        url=f"internal:page-{page_num}",
        filename=f"{file_path.stem}-page-{page_num}.pdf",
        page_count=1,
        text_preview=_text_preview(str(clues.get("text", ""))),
        drawing_id=None,
    )
    return summary, word_count


def _write_pdf_bytes(body: bytes, *, filename_hint: str) -> Path:
    suffix = Path(filename_hint).suffix.lower() or ".pdf"
    temp_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    temp_file.write(body)
    temp_file.close()
    return Path(temp_file.name)


def run_pdf_investigation(
    file_path: Path,
    *,
    max_links: int = 10,
) -> EvidenceInvestigationPayload:
    """Follow PDF links, render pages, extract clues, and return investigation payload."""
    if file_path.suffix.lower() != ".pdf":
        base_text = extract_document(file_path).full_text().strip()
        return EvidenceInvestigationPayload(
            link_result=LinkFollowResult(),
            merged_text=base_text,
            base_text=base_text,
            summaries=(),
            links_followed=0,
            pages_rendered=0,
            ocr_word_counts={},
            errors=(),
        )

    summaries: list[LinkedAttachmentSummary] = []
    ocr_word_counts: dict[str, int] = {}
    errors: list[str] = []
    pages_rendered = 0
    seen_keys: set[str] = set()

    def _append(summary: LinkedAttachmentSummary, word_count: int) -> None:
        nonlocal pages_rendered
        if len(summaries) >= max_links:
            return
        key = summary.url or summary.filename
        if key in seen_keys:
            return
        seen_keys.add(key)
        summaries.append(summary)
        ocr_word_counts[key] = word_count
        pages_rendered += 1

    link_result = follow_and_capture_links(file_path)
    errors.extend(link_result.errors)
    base_text = extract_document(file_path).full_text().strip()
    merged_text = _merge_evidence_text(base_text, link_result)

    for fetched in link_result.fetched_pdfs:
        if len(summaries) >= max_links:
            break
        summary, word_count = _summary_from_fetched(fetched)
        _append(summary, word_count)

    hyperlinks = list_pdf_hyperlinks(file_path)
    internal_targets: list[int] = []
    seen_pages: set[int] = set()
    for link in hyperlinks:
        if link.kind != PdfLinkKind.INTERNAL_PAGE or link.target_page is None:
            continue
        target = int(link.target_page)
        if target in seen_pages:
            continue
        seen_pages.add(target)
        internal_targets.append(target)

    for target_page in internal_targets:
        if len(summaries) >= max_links:
            break
        try:
            summary, word_count = _summary_from_internal_page(
                file_path,
                target_page=target_page,
            )
            _append(summary, word_count)
        except Exception:
            logger.exception(
                "pdf_investigation_internal_page_failed",
                extra={"file_path": str(file_path), "target_page": target_page + 1},
            )
            errors.append(f"internal page {target_page + 1} investigation failed")

    return EvidenceInvestigationPayload(
        link_result=link_result,
        merged_text=merged_text,
        base_text=base_text,
        summaries=tuple(summaries),
        links_followed=link_result.followed_count,
        pages_rendered=pages_rendered,
        ocr_word_counts=ocr_word_counts,
        errors=tuple(errors),
    )


def investigate_pdf_links(
    file_path: Path,
    *,
    max_links: int = 10,
) -> list[LinkedAttachmentSummary]:
    """Autonomously follow PDF links, render pages, and extract clue summaries.

    Sheet numbers in filenames are for listing only — never used for master placement.
    """
    return list(run_pdf_investigation(file_path, max_links=max_links).summaries)
