"""Unit tests for PDF hyperlink extraction and internal link following."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from ai.pipelines.pdf_link_follower import (
    MAX_SUPPLEMENTAL_TEXT_CHARS,
    PdfLinkKind,
    LinkFollowResult,
    _append_supplemental_text,
    _truncate_section_to_fit,
    _extract_hyperlinks,
    follow_pdf_links,
)


def _pdf_with_internal_link(tmp_path: Path) -> Path:
    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    p0 = doc[0]
    p1 = doc[1]
    p0.insert_text((72, 72), "See detail on page 2")
    p1.insert_text((72, 72), "Location: COLO")
    p0.insert_link(
        {
            "kind": fitz.LINK_GOTO,
            "page": 1,
            "from": fitz.Rect(72, 60, 300, 90),
            "to": fitz.Point(72, 72),
        }
    )
    path = tmp_path / "linked.pdf"
    doc.save(path)
    doc.close()
    return path


def test_extract_hyperlinks_finds_internal_link(tmp_path: Path) -> None:
    pdf_path = _pdf_with_internal_link(tmp_path)

    links = _extract_hyperlinks(pdf_path)

    assert len(links) == 1
    link = links[0]
    assert link.kind == PdfLinkKind.INTERNAL_PAGE
    assert link.page_index == 0
    assert link.target_page == 1
    assert link.uri is None


def test_follow_pdf_links_supplemental_text_contains_target_page_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ai.pipelines.pdf_link_follower.settings.pdf_link_follow_enabled",
        True,
    )
    pdf_path = _pdf_with_internal_link(tmp_path)

    result = follow_pdf_links(pdf_path)

    assert "COLO" in result.supplemental_text
    assert result.followed_count == 1
    assert any(ref.get("kind") == "pdf_internal_link" for ref in result.cross_refs)


def test_append_supplemental_text_truncates_oversized_section() -> None:
    result = LinkFollowResult()
    header = "\n\n--- Linked content (https://example.com/plan.pdf) ---\n"
    body = "Utility MR " * 250_000  # ~2.75M chars — exceeds 2M cap
    section = header + body

    assert _append_supplemental_text(result, section, links_remaining=1) is True
    assert len(result.supplemental_text) <= MAX_SUPPLEMENTAL_TEXT_CHARS
    assert result.supplemental_text.startswith(header)
    assert "...[linked content truncated]" in result.supplemental_text
    assert any("truncated by" in err for err in result.errors)


def test_append_supplemental_text_fits_second_link_after_truncated_first() -> None:
    result = LinkFollowResult()
    first = "\n\n--- Linked content (https://example.com/big.pdf) ---\n" + ("x" * 3_000_000)
    second = "\n\n--- Linked content (https://example.com/small.pdf) ---\nNPC-5 C4.20"

    assert _append_supplemental_text(result, first, links_remaining=2) is True
    assert _append_supplemental_text(result, second, links_remaining=1) is True
    assert len(result.supplemental_text) <= MAX_SUPPLEMENTAL_TEXT_CHARS
    assert "NPC-5 C4.20" in result.supplemental_text
    assert len(result.supplemental_text) > len(second)


def test_follow_pdf_links_prioritizes_install_drawing_over_submittal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """External links merge by relevance, not fetch order."""
    from ai.pipelines.document_text_extraction import ExtractedDocument, PositionedWord, SourceFormat
    from services.safe_url_fetch import UrlAttachmentFetch

    monkeypatch.setattr(
        "ai.pipelines.pdf_link_follower.settings.pdf_link_follow_enabled",
        True,
    )
    monkeypatch.setattr(
        "ai.pipelines.pdf_link_follower.settings.pdf_link_follow_max_external",
        10,
    )

    doc = fitz.open()
    page = doc.new_page()
    page.insert_link(
        {
            "kind": fitz.LINK_URI,
            "uri": "https://storage.procore.com/submittal.pdf",
            "from": fitz.Rect(72, 60, 300, 90),
        }
    )
    page.insert_link(
        {
            "kind": fitz.LINK_URI,
            "uri": "https://storage.procore.com/install.pdf",
            "from": fitz.Rect(72, 100, 300, 130),
        }
    )
    pdf_path = tmp_path / "report.pdf"
    doc.save(pdf_path)
    doc.close()

    submittal_words = " ".join(["submittal"] * 22008)
    install_words = " ".join(["STA", "10+05.00", "manhole"] * 200)

    def fake_fetch(url: str) -> UrlAttachmentFetch:
        if "submittal" in url:
            return UrlAttachmentFetch(
                text=submittal_words,
                error=None,
                filename="UMR Sanitary Sewer PD_Approved submittal.pdf",
                pages=78,
            )
        return UrlAttachmentFetch(
            text=install_words,
            error=None,
            filename="7.20 Sanitary Sewer Install.pdf",
            pages=2,
        )

    monkeypatch.setattr(
        "ai.pipelines.pdf_link_follower.fetch_url_attachment_with_error",
        fake_fetch,
    )
    monkeypatch.setattr(
        "ai.pipelines.pdf_link_follower.is_allowed_external_url",
        lambda _url: True,
    )

    result = follow_pdf_links(pdf_path)

    assert result.followed_count == 2
    assert "STA 10+05.00" in result.supplemental_text
    assert result.supplemental_text.index("install.pdf") < result.supplemental_text.index(
        "submittal"
    )


def test_truncate_section_to_fit_preserves_header() -> None:
    section = "\n\n--- Linked content (page 2) ---\n" + ("word " * 500)
    truncated = _truncate_section_to_fit(section, 200)

    assert truncated is not None
    assert truncated.startswith("\n\n--- Linked content (page 2) ---\n")
    assert truncated.endswith("...[linked content truncated]")
    assert len(truncated) <= 200
