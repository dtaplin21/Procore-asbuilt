"""Follow hyperlinks embedded in uploaded PDFs to gather supplemental text.

Phase 4: external URL fetch wired via services.safe_url_fetch.
See Notes/Cursor Implementation Plan (Phase 0) for v1 limits.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import fitz

from ai.pipelines.linked_attachment_merge import (
    LinkedAttachment,
    merge_linked_attachments_within_budget,
)
from config import settings
from services.procore_url_parser import build_procore_cross_ref, parse_procore_url
from services.safe_url_fetch import (
    fetch_url_attachment_with_error,
    is_allowed_external_url,
)

MAX_SUPPLEMENTAL_TEXT_CHARS = 2_000_000
_TRUNCATION_SUFFIX = "\n...[linked content truncated]"

logger = logging.getLogger(__name__)


class PdfLinkKind(str, Enum):
    INTERNAL_PAGE = "internal_page"  # same PDF, goto page N
    EXTERNAL_URI = "external_uri"  # https://...
    NAMED_DEST = "named_dest"  # optional; handle in v2


@dataclass(frozen=True)
class PdfHyperlink:
    page_index: int  # 0-based page where link appears
    kind: PdfLinkKind
    uri: str | None  # external URL or None for internal
    target_page: int | None  # 0-based destination page (internal)
    anchor_text: str | None  # visible link label if available


@dataclass
class LinkFollowResult:
    supplemental_text: str = ""
    cross_refs: list[dict] = field(default_factory=list)
    followed_count: int = 0
    skipped_count: int = 0
    errors: list[str] = field(default_factory=list)


def follow_pdf_links(file_path: str | Path) -> LinkFollowResult:
    """Enumerate and follow hyperlinks in a PDF. Non-PDF files return empty result."""
    if not settings.pdf_link_follow_enabled:
        return LinkFollowResult()

    path = Path(file_path)
    if path.suffix.lower() != ".pdf":
        return LinkFollowResult()

    try:
        links = _dedupe_links(_extract_hyperlinks(path))
    except Exception:
        logger.exception(
            "pdf_hyperlink_extraction_failed",
            extra={"file_path": str(file_path)},
        )
        return LinkFollowResult(errors=["hyperlink extraction failed"])

    result = _follow_links(path, links)
    logger.info(
        "pdf_link_follow_complete",
        extra={
            "file_path": str(file_path),
            "links_found": len(links),
            "followed": result.followed_count,
            "skipped": result.skipped_count,
        },
    )
    return result


def _extract_hyperlinks(file_path: str | Path) -> list[PdfHyperlink]:
    doc = fitz.open(str(file_path))
    links: list[PdfHyperlink] = []
    try:
        for page_index in range(doc.page_count):
            page = doc.load_page(page_index)
            for raw in page.get_links():  # PyMuPDF link dicts
                link = _normalize_link_dict(page_index, raw)
                if link is not None:
                    links.append(link)
    finally:
        doc.close()
    return links


def _normalize_link_dict(page_index: int, raw: dict) -> PdfHyperlink | None:
    kind = raw.get("kind")
    if kind == fitz.LINK_URI:
        uri = raw.get("uri")
        if not uri:
            return None
        return PdfHyperlink(
            page_index=page_index,
            kind=PdfLinkKind.EXTERNAL_URI,
            uri=str(uri).strip(),
            target_page=None,
            anchor_text=None,
        )
    if kind == fitz.LINK_GOTO:
        target = raw.get("page")
        if target is None:
            return None
        return PdfHyperlink(
            page_index=page_index,
            kind=PdfLinkKind.INTERNAL_PAGE,
            uri=None,
            target_page=int(target),
            anchor_text=None,
        )
    return None  # ignore LINK_NAMED, LINK_LAUNCH in v1


def _dedupe_links(links: list[PdfHyperlink]) -> list[PdfHyperlink]:
    """Drop repeated links (e.g. footer URLs) before follow work."""
    seen: set[tuple[PdfLinkKind, str | None, int | None]] = set()
    deduped: list[PdfHyperlink] = []
    for link in links:
        key = (link.kind, link.uri, link.target_page)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(link)
    return deduped


def _text_from_page(doc: fitz.Document, page_index: int) -> str:
    if page_index < 0 or page_index >= doc.page_count:
        return ""
    return str(doc.load_page(page_index).get_text("text") or "")


def _follow_links(file_path: Path, links: list[PdfHyperlink]) -> LinkFollowResult:
    result = LinkFollowResult()
    attachments: list[LinkedAttachment] = []

    internal_links = [
        link
        for link in links
        if link.kind == PdfLinkKind.INTERNAL_PAGE and link.target_page is not None
    ]
    if internal_links:
        doc = fitz.open(str(file_path))
        try:
            _collect_internal_attachments(doc, internal_links, attachments, result)
        finally:
            doc.close()

    external_links = [
        link for link in links if link.kind == PdfLinkKind.EXTERNAL_URI and link.uri
    ]
    external_fetches = 0
    for link in external_links:
        uri = link.uri
        if not uri:
            continue
        if not is_allowed_external_url(uri):
            result.skipped_count += 1
            continue
        if external_fetches >= settings.pdf_link_follow_max_external:
            result.skipped_count += 1
            continue
        try:
            fetched = fetch_url_attachment_with_error(uri)
            external_fetches += 1
            if fetched.text.strip():
                word_count = len(fetched.text.split())
                attachments.append(
                    LinkedAttachment(
                        url=uri,
                        filename=fetched.filename,
                        text=fetched.text,
                        word_count=word_count,
                        pages=fetched.pages or 1,
                    )
                )
                logger.info(
                    "pdf_link_fetch_ocr_complete",
                    extra={
                        "pages": fetched.pages,
                        "words": word_count,
                        "filename": fetched.filename,
                    },
                )
                result.followed_count += 1
            elif fetched.error:
                result.errors.append(f"{uri}: {fetched.error}")
                result.skipped_count += 1
            parsed = parse_procore_url(uri)
            if parsed:
                result.cross_refs.append(
                    build_procore_cross_ref(
                        parsed,
                        source_page=link.page_index + 1,
                        anchor_text=link.anchor_text,
                    )
                )
        except Exception as exc:
            result.errors.append(str(exc))
            result.skipped_count += 1

    if attachments:
        merge_result = merge_linked_attachments_within_budget(attachments)
        result.supplemental_text = merge_result["merged_text"]
        logger.info(
            "pdf_link_merge_complete",
            extra={
                "included": merge_result["included"],
                "truncated": merge_result["truncated"],
                "dropped": merge_result["dropped"],
            },
        )
        if merge_result["dropped"]:
            logger.warning(
                "pdf_link_attachments_dropped",
                extra={
                    "dropped": merge_result["dropped"],
                    "reason": "word_budget_exhausted",
                },
            )
        if merge_result["truncated"]:
            for filename in merge_result["truncated"]:
                result.errors.append(f"linked attachment truncated in merge: {filename}")

    return result


def _collect_internal_attachments(
    doc: fitz.Document,
    internal_links: list[PdfHyperlink],
    attachments: list[LinkedAttachment],
    result: LinkFollowResult,
) -> None:
    unique_targets: list[int] = []
    seen_targets: set[int] = set()
    for link in internal_links:
        target = link.target_page
        if target is None:
            continue
        if target < 0 or target >= doc.page_count:
            result.skipped_count += 1
            result.errors.append(
                f"internal link target page {target + 1} out of range "
                f"(document has {doc.page_count} pages)"
            )
            continue
        if target not in seen_targets:
            seen_targets.add(target)
            unique_targets.append(target)

    for page_index in unique_targets:
        text = _text_from_page(doc, page_index)
        if not text.strip():
            continue
        page_label = f"page {page_index + 1}"
        attachments.append(
            LinkedAttachment(
                url=page_label,
                filename=f"{page_label}.pdf",
                text=text,
                word_count=len(text.split()),
                pages=1,
            )
        )
        result.followed_count += 1

    for link in internal_links:
        target = link.target_page
        if target is None:
            continue
        if target < 0 or target >= doc.page_count:
            continue
        result.cross_refs.append(
            {
                "kind": "pdf_internal_link",
                "source_page": link.page_index + 1,
                "target_page": target + 1,
                "anchor_text": link.anchor_text,
            }
        )


def _append_supplemental_text(
    result: LinkFollowResult,
    section: str,
    *,
    links_remaining: int = 1,
) -> bool:
    """Legacy char-budget append helper retained for unit tests."""
    remaining = MAX_SUPPLEMENTAL_TEXT_CHARS - len(result.supplemental_text)
    if remaining <= 0:
        result.errors.append(
            f"supplemental text at {MAX_SUPPLEMENTAL_TEXT_CHARS} character cap"
        )
        return False

    budget = remaining
    if links_remaining > 1:
        budget = min(remaining, remaining // links_remaining)

    if len(section) <= budget:
        result.supplemental_text += section
        return True

    truncated = _truncate_section_to_fit(section, budget)
    if truncated is None:
        result.errors.append(
            f"insufficient room to append linked content "
            f"({budget} chars budget of {MAX_SUPPLEMENTAL_TEXT_CHARS} cap)"
        )
        return False

    result.supplemental_text += truncated
    omitted = len(section) - len(truncated)
    if omitted > 0:
        result.errors.append(
            f"linked content truncated by {omitted} chars to fit "
            f"{budget} char budget ({links_remaining} link(s) remaining)"
        )
    return True


def _split_linked_section(section: str) -> tuple[str, str]:
    """Split ``--- Linked content ... ---`` header from body text."""
    marker = "--- Linked content"
    start = section.find(marker)
    if start == -1:
        return "", section
    header_end = section.find("\n", start)
    if header_end == -1:
        return section, ""
    return section[: header_end + 1], section[header_end + 1 :]


def _truncate_text(text: str, max_len: int) -> str:
    if max_len <= 0:
        return ""
    if len(text) <= max_len:
        return text
    head = text[:max_len]
    for sep in ("\n", " "):
        break_at = head.rfind(sep)
        if break_at > max_len // 2:
            return head[:break_at]
    return head


def _truncate_section_to_fit(section: str, max_len: int) -> str | None:
    """Fit ``section`` into ``max_len`` chars, preserving the link header when possible."""
    if max_len <= 0:
        return None
    if len(section) <= max_len:
        return section

    suffix = _TRUNCATION_SUFFIX
    if max_len <= len(suffix):
        return None

    header, body = _split_linked_section(section)
    if header and len(header) + len(suffix) < max_len:
        body_budget = max_len - len(header) - len(suffix)
        if body_budget <= 0:
            return None
        return header + _truncate_text(body, body_budget) + suffix

    budget = max_len - len(suffix)
    if budget <= 0:
        return None
    return _truncate_text(section, budget) + suffix
