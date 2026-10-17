"""PDF investigation tools — open links and view pages within PDFs."""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import fitz

from config import settings
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
from services.safe_url_fetch import ProcoreFetchContext

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_TEXT_PREVIEW_CHARS = 2000
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
    page_investigations: tuple[dict[str, Any], ...] = ()


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


def follow_and_capture_links(
    file_path: Path,
    *,
    max_external: int | None = None,
    max_depth: int | None = None,
    merge_word_budget: int | None = None,
    procore_context: ProcoreFetchContext | None = None,
) -> LinkFollowResult:
    """Follow hyperlinks and capture supplemental text + fetched PDF bodies."""
    return follow_pdf_links(
        file_path,
        max_external=max_external,
        max_depth=max_depth,
        merge_word_budget=merge_word_budget,
        procore_context=procore_context,
    )


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
    """Extract OCR + vision text and location hints from one page of a PDF or image."""
    from ai.pipelines.evidence_page_investigation import (
        investigate_pdf_page,
        survey_hints_from_text,
    )

    suffix = pdf_path.suffix.lower()
    page_index = max(page - 1, 0)
    if suffix in _IMAGE_SUFFIXES:
        document = extract_document(pdf_path)
        page_index = min(page_index, max(document.page_count - 1, 0))
        page_text = document.page_text(page_index)
        page_count = document.page_count
        word_count = len([word for word in document.words if word.page_index == page_index])
        positioned_terms = extract_positioned_terms(document)
        page_terms = [term for term in positioned_terms if term.page_index == page_index]
    else:
        investigated = investigate_pdf_page(pdf_path, page=page)
        page_text = investigated.combined_text
        word_count = len(page_text.split())
        doc = fitz.open(str(pdf_path))
        try:
            page_count = doc.page_count
        finally:
            doc.close()
        page_terms = []

    hints = survey_hints_from_text(page_text, page=max(page, 1))

    return {
        "text": page_text,
        "word_count": word_count,
        "page_count": page_count,
        "positioned_term_count": len(page_terms),
        "survey_hints": hints,
    }


def extract_attachment_clues(pdf_path: Path) -> dict[str, Any]:
    """Full multi-page OCR, vision, and clue extraction for a linked attachment PDF."""
    from ai.pipelines.document_text_extraction import extract_document_via_ocr
    from ai.pipelines.evidence_page_investigation import (
        investigate_pdf_all_pages,
        link_follow_ocr_max_pages,
        page_investigation_to_meta,
        survey_hints_from_text,
    )

    page_results, document = investigate_pdf_all_pages(pdf_path)
    page_blocks = [result.combined_text for result in page_results if result.combined_text.strip()]
    combined_text = "\n\n".join(page_blocks)

    positioned_terms = extract_positioned_terms(document)
    if not combined_text.strip():
        combined_text = document.full_text()

    all_stations: list[str] = []
    coordinate_pairs: list[dict[str, Any]] = []
    for result in page_results:
        if not result.combined_text.strip():
            continue
        hints = survey_hints_from_text(result.combined_text, page=result.page)
        all_stations.extend(cast(list[str], hints["stations"]))
        coordinate_pairs.extend(cast(list[dict[str, Any]], hints["coordinate_pairs"]))

    return {
        "text": combined_text,
        "word_count": len(combined_text.split()),
        "page_count": document.page_count,
        "positioned_term_count": len(positioned_terms),
        "survey_hints": {
            "stations": sorted(set(all_stations)),
            "coordinate_pairs": coordinate_pairs,
        },
        "page_investigations": [
            page_investigation_to_meta(result, source="linked_attachment")
            for result in page_results
        ],
    }


def _text_preview(text: str) -> str:
    stripped = text.strip()
    if len(stripped) <= _TEXT_PREVIEW_CHARS:
        return stripped
    return stripped[:_TEXT_PREVIEW_CHARS]


def _summary_from_fetched(
    fetched: FetchedLinkedPdf,
) -> tuple[LinkedAttachmentSummary, int, tuple[dict[str, Any], ...], str]:
    preview = _text_preview(fetched.text)
    word_count = len(fetched.text.split())
    page_count = fetched.pages or 1
    page_meta: tuple[dict[str, Any], ...] = ()
    enriched_text = ""
    if fetched.body:
        temp_path = _write_pdf_bytes(fetched.body, filename_hint=fetched.filename)
        try:
            from services.inspection_run_progress import get_inspection_progress

            progress = get_inspection_progress()
            if progress is not None:
                progress.set_file_name(fetched.filename)
                progress.set_phase("reading_pdf")
            clues = extract_attachment_clues(temp_path)
            page_text = str(clues.get("text", "") or "")
            word_count = int(clues.get("word_count", word_count))
            page_count = int(clues.get("page_count", page_count))
            raw_meta = clues.get("page_investigations")
            if isinstance(raw_meta, list):
                page_meta = tuple(dict(item) for item in raw_meta if isinstance(item, dict))
            if page_text.strip():
                enriched_text = page_text.strip()
                preview = _text_preview(page_text)
        except Exception:
            logger.exception(
                "pdf_investigation_fetched_clue_extract_failed",
                extra={"url": fetched.url, "attachment_filename": fetched.filename},
            )
        finally:
            temp_path.unlink(missing_ok=True)

    summary = LinkedAttachmentSummary(
        url=fetched.url,
        filename=fetched.filename,
        page_count=page_count,
        text_preview=preview,
        drawing_id=None,
    )
    return summary, word_count, page_meta, enriched_text


def _summary_from_internal_page(
    file_path: Path,
    *,
    target_page: int,
) -> tuple[LinkedAttachmentSummary, int, tuple[dict[str, Any], ...], str]:
    from ai.pipelines.evidence_page_investigation import (
        investigate_pdf_page,
        page_investigation_to_meta,
    )

    page_num = target_page + 1
    investigated = investigate_pdf_page(file_path, page=page_num)
    page_text = investigated.combined_text
    word_count = len(page_text.split())
    page_meta = (
        page_investigation_to_meta(investigated, source=f"internal:{page_num}"),
    )
    summary = LinkedAttachmentSummary(
        url=f"internal:page-{page_num}",
        filename=f"{file_path.stem}-page-{page_num}.pdf",
        page_count=1,
        text_preview=_text_preview(page_text),
        drawing_id=None,
    )
    return summary, word_count, page_meta, page_text


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
    session: Session | None = None,
    project_id: int | None = None,
) -> EvidenceInvestigationPayload:
    """Follow PDF links, render pages, extract clues, and return investigation payload."""
    from services.inspection_run_progress import get_inspection_progress

    progress = get_inspection_progress()
    if progress is not None:
        progress.set_phase("following_links")

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
            page_investigations=(),
        )

    summaries: list[LinkedAttachmentSummary] = []
    ocr_word_counts: dict[str, int] = {}
    errors: list[str] = []
    pages_rendered = 0
    seen_keys: set[str] = set()
    page_investigations: list[dict[str, Any]] = []

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
        pages_rendered += max(summary.page_count, 1)

    procore_context = (
        ProcoreFetchContext(db=session, project_id=project_id)
        if session is not None and project_id is not None
        else None
    )

    link_result = follow_and_capture_links(
        file_path,
        max_external=max_links,
        max_depth=settings.pdf_link_follow_max_depth,
        merge_word_budget=settings.pdf_link_merge_word_budget_match,
        procore_context=procore_context,
    )
    errors.extend(link_result.errors)
    try:
        from ai.pipelines.evidence_page_investigation import (
            extract_inspection_document,
            investigate_pdf_all_pages,
        )

        if progress is not None:
            progress.set_file_name(file_path.name)
            progress.set_phase("reading_pdf")
            _page_results, document = investigate_pdf_all_pages(file_path)
            base_text = document.full_text().strip()
        else:
            base_text = extract_inspection_document(file_path).full_text().strip()
    except Exception:
        logger.exception(
            "pdf_investigation_base_extract_failed",
            extra={"file_path": str(file_path)},
        )
        base_text = extract_document(file_path).full_text().strip()
    merged_text = _merge_evidence_text(base_text, link_result)
    enriched_sections: list[str] = []

    for fetched in link_result.fetched_pdfs:
        if len(summaries) >= max_links:
            break
        summary, word_count, page_meta, enriched = _summary_from_fetched(fetched)
        page_investigations.extend(page_meta)
        if enriched.strip():
            enriched_sections.append(
                f"--- Linked attachment {summary.filename} (OCR+vision) ---\n{enriched.strip()}"
            )
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
            summary, word_count, page_meta, enriched = _summary_from_internal_page(
                file_path,
                target_page=target_page,
            )
            page_investigations.extend(page_meta)
            if enriched.strip():
                enriched_sections.append(
                    f"--- Internal page {target_page + 1} (OCR+vision) ---\n{enriched.strip()}"
                )
            _append(summary, word_count)
        except Exception:
            logger.exception(
                "pdf_investigation_internal_page_failed",
                extra={"file_path": str(file_path), "target_page": target_page + 1},
            )
            errors.append(f"internal page {target_page + 1} investigation failed")

    if enriched_sections:
        merged_text = "\n\n".join(enriched_sections + [merged_text]).strip()

    return EvidenceInvestigationPayload(
        link_result=link_result,
        merged_text=merged_text,
        base_text=base_text,
        summaries=tuple(summaries),
        links_followed=link_result.followed_count,
        pages_rendered=pages_rendered,
        ocr_word_counts=ocr_word_counts,
        errors=tuple(errors),
        page_investigations=tuple(page_investigations),
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
