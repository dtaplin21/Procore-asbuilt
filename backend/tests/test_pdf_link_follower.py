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

    def fake_fetch(url: str, **kwargs: object) -> UrlAttachmentFetch:
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


def test_follow_pdf_links_respects_max_external_param(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.safe_url_fetch import UrlAttachmentFetch

    monkeypatch.setattr(
        "ai.pipelines.pdf_link_follower.settings.pdf_link_follow_enabled",
        True,
    )
    monkeypatch.setattr(
        "ai.pipelines.pdf_link_follower.is_allowed_external_url",
        lambda _url: True,
    )

    doc = fitz.open()
    page = doc.new_page()
    for index in range(3):
        page.insert_link(
            {
                "kind": fitz.LINK_URI,
                "uri": f"https://storage.procore.com/plan-{index}.pdf",
                "from": fitz.Rect(72, 60 + index * 30, 300, 80 + index * 30),
            }
        )
    pdf_path = tmp_path / "report.pdf"
    doc.save(pdf_path)
    doc.close()

    def fake_fetch(url: str, **kwargs: object) -> UrlAttachmentFetch:
        return UrlAttachmentFetch(
            text=f"install detail {url}",
            error=None,
            filename=url.rsplit("/", 1)[-1],
            pages=1,
            body=b"%PDF-1.4",
            content_type="application/pdf",
        )

    monkeypatch.setattr(
        "ai.pipelines.pdf_link_follower.fetch_url_attachment_with_error",
        fake_fetch,
    )

    result = follow_pdf_links(pdf_path, max_external=1, max_depth=1)

    assert result.followed_count == 1
    assert len(result.fetched_pdfs) == 1
    assert result.skipped_count >= 2


def test_fetch_attachment_with_retry_retries_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai.pipelines.pdf_link_follower import _fetch_attachment_with_retry
    from services.safe_url_fetch import UrlAttachmentFetch

    calls = {"count": 0}

    def fake_fetch(url: str, **kwargs: object) -> UrlAttachmentFetch:
        calls["count"] += 1
        if calls["count"] == 1:
            return UrlAttachmentFetch(
                text="",
                error="request timed out",
                filename="plan.pdf",
                pages=0,
            )
        return UrlAttachmentFetch(
            text="Location: COLO",
            error=None,
            filename="plan.pdf",
            pages=1,
        )

    monkeypatch.setattr(
        "ai.pipelines.pdf_link_follower.fetch_url_attachment_with_error",
        fake_fetch,
    )

    fetched = _fetch_attachment_with_retry("https://storage.procore.com/plan.pdf")

    assert calls["count"] == 2
    assert fetched.error is None
    assert "COLO" in fetched.text


def test_follow_pdf_links_follows_nested_pdf_when_depth_allows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.safe_url_fetch import UrlAttachmentFetch

    monkeypatch.setattr(
        "ai.pipelines.pdf_link_follower.settings.pdf_link_follow_enabled",
        True,
    )
    monkeypatch.setattr(
        "ai.pipelines.pdf_link_follower.is_allowed_external_url",
        lambda _url: True,
    )

    nested_doc = fitz.open()
    nested_page = nested_doc.new_page()
    nested_page.insert_text((72, 72), "Nested install STA 10+05.00")
    nested_bytes = nested_doc.tobytes()
    nested_doc.close()

    nested_with_link = fitz.open()
    nested_link_page = nested_with_link.new_page()
    nested_link_page.insert_link(
        {
            "kind": fitz.LINK_URI,
            "uri": "https://storage.procore.com/deep.pdf",
            "from": fitz.Rect(72, 60, 300, 90),
        }
    )
    nested_link_bytes = nested_with_link.tobytes()
    nested_with_link.close()

    doc = fitz.open()
    page = doc.new_page()
    page.insert_link(
        {
            "kind": fitz.LINK_URI,
            "uri": "https://storage.procore.com/outer.pdf",
            "from": fitz.Rect(72, 60, 300, 90),
        }
    )
    pdf_path = tmp_path / "report.pdf"
    doc.save(pdf_path)
    doc.close()

    def fake_fetch(url: str, **kwargs: object) -> UrlAttachmentFetch:
        if url.endswith("outer.pdf"):
            return UrlAttachmentFetch(
                text="Outer sheet",
                error=None,
                filename="outer.pdf",
                pages=1,
                body=nested_link_bytes,
                content_type="application/pdf",
            )
        if url.endswith("deep.pdf"):
            return UrlAttachmentFetch(
                text="Nested install STA 10+05.00",
                error=None,
                filename="deep.pdf",
                pages=1,
                body=nested_bytes,
                content_type="application/pdf",
            )
        return UrlAttachmentFetch(text="", error="unexpected url", filename="", pages=0)

    monkeypatch.setattr(
        "ai.pipelines.pdf_link_follower.fetch_url_attachment_with_error",
        fake_fetch,
    )

    shallow = follow_pdf_links(pdf_path, max_external=5, max_depth=1)
    deep = follow_pdf_links(pdf_path, max_external=5, max_depth=2)

    assert len(shallow.fetched_pdfs) == 1
    assert len(deep.fetched_pdfs) == 2
    assert "Nested install STA 10+05.00" in deep.supplemental_text
