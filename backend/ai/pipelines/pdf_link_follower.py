"""Follow hyperlinks embedded in uploaded PDFs to gather supplemental text.

Phase 4: external URL fetch wired via services.safe_url_fetch.
See Notes/Cursor Implementation Plan (Phase 0) for v1 limits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import fitz

from services.procore_url_parser import build_procore_cross_ref, parse_procore_url
from services.safe_url_fetch import fetch_url_text, is_allowed_external_url

MAX_EXTERNAL_FETCHES_PER_UPLOAD = 5
MAX_SUPPLEMENTAL_TEXT_CHARS = 80_000


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
    path = Path(file_path)
    if path.suffix.lower() != ".pdf":
        return LinkFollowResult()

    links = _dedupe_links(_extract_hyperlinks(path))
    return _follow_links(path, links)


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

    internal_links = [
        link
        for link in links
        if link.kind == PdfLinkKind.INTERNAL_PAGE and link.target_page is not None
    ]
    if internal_links:
        doc = fitz.open(str(file_path))
        try:
            _follow_internal_links(doc, internal_links, result)
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
        if external_fetches >= MAX_EXTERNAL_FETCHES_PER_UPLOAD:
            result.skipped_count += 1
            continue
        try:
            text = fetch_url_text(uri)
            external_fetches += 1
            if text.strip():
                section = f"\n\n--- Linked content ({uri}) ---\n{text}"
                if not _append_supplemental_text(result, section):
                    result.skipped_count += 1
                    continue
                result.followed_count += 1
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

    return result


def _follow_internal_links(
    doc: fitz.Document,
    internal_links: list[PdfHyperlink],
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
        section = f"\n\n--- Linked content (page {page_index + 1}) ---\n{text}"
        _append_supplemental_text(result, section)

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
        result.followed_count += 1


def _append_supplemental_text(result: LinkFollowResult, section: str) -> bool:
    if len(result.supplemental_text) + len(section) > MAX_SUPPLEMENTAL_TEXT_CHARS:
        result.errors.append(
            f"supplemental text would exceed {MAX_SUPPLEMENTAL_TEXT_CHARS} character cap"
        )
        return False
    result.supplemental_text += section
    return True
