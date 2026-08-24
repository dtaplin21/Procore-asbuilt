"""Tests for PDF investigation agent tools."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import fitz
import pytest

from ai.agents.tools.pdf_investigation import (
    extract_page_clues,
    follow_and_capture_links,
    investigate_pdf_links,
    list_pdf_hyperlinks,
    render_pdf_page,
    run_pdf_investigation,
)
from ai.pipelines.pdf_link_follower import (
    FetchedLinkedPdf,
    LinkFollowResult,
    PdfLinkKind,
)


def _pdf_with_internal_link(tmp_path: Path) -> Path:
    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    p0 = doc[0]
    p1 = doc[1]
    p0.insert_text((72, 72), "See detail on page 2")
    p1.insert_text((72, 72), "Location: COLO STA 10+50")
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


def test_list_pdf_hyperlinks_finds_internal_link(tmp_path: Path) -> None:
    pdf_path = _pdf_with_internal_link(tmp_path)

    links = list_pdf_hyperlinks(pdf_path)

    assert len(links) == 1
    assert links[0].kind == PdfLinkKind.INTERNAL_PAGE
    assert links[0].target_page == 1


def test_render_pdf_page_writes_png(tmp_path: Path) -> None:
    pdf_path = _pdf_with_internal_link(tmp_path)

    rendered = render_pdf_page(pdf_path, page=2)

    assert rendered.page == 2
    assert rendered.png_path.exists()
    assert rendered.png_path.suffix == ".png"
    assert rendered.width_pt is not None
    rendered.png_path.unlink(missing_ok=True)


@patch("ai.agents.tools.pdf_investigation.extract_document")
def test_extract_page_clues_returns_counts(mock_extract: MagicMock, tmp_path: Path) -> None:
    from ai.pipelines.document_text_extraction import (
        BoundingBox,
        ExtractedDocument,
        PositionedWord,
        SourceFormat,
    )

    bbox = BoundingBox(x=0, y=0, width=100, height=100, page_width=100, page_height=100)
    words = [
        PositionedWord(text="Location:", bbox=bbox, page_index=0),
        PositionedWord(text="COLO", bbox=bbox, page_index=0),
        PositionedWord(text="STA", bbox=bbox, page_index=0),
        PositionedWord(text="10+50", bbox=bbox, page_index=0),
    ]
    mock_extract.return_value = ExtractedDocument(
        source_format=SourceFormat.NATIVE_PDF,
        page_count=1,
        words=words,
    )

    clues = extract_page_clues(tmp_path / "dummy.pdf", page=1)

    assert clues["word_count"] == 4
    assert clues["positioned_term_count"] >= 0
    assert "COLO" in clues["text"]
    assert "10+50" in clues["survey_hints"]["stations"]


@patch("ai.agents.tools.pdf_investigation.follow_and_capture_links")
@patch("ai.agents.tools.pdf_investigation.extract_page_clues")
def test_investigate_pdf_links_external_and_internal(
    mock_extract_clues: MagicMock,
    mock_follow: MagicMock,
    tmp_path: Path,
) -> None:
    pdf_path = _pdf_with_internal_link(tmp_path)
    mock_follow.return_value = LinkFollowResult(
        fetched_pdfs=[
            FetchedLinkedPdf(
                url="https://example.com/install.pdf",
                filename="install.pdf",
                body=b"%PDF-1.4 mock",
                pages=1,
                content_type="application/pdf",
                text="Sanitary sewer install",
            )
        ],
        followed_count=2,
    )
    mock_extract_clues.return_value = {
        "text": "Location: COLO",
        "word_count": 2,
        "positioned_term_count": 1,
        "survey_hints": {"stations": [], "coordinate_pairs": []},
    }

    summaries = investigate_pdf_links(pdf_path, max_links=10)

    assert mock_follow.called
    assert mock_extract_clues.call_count >= 2
    urls = {item.url for item in summaries}
    assert "https://example.com/install.pdf" in urls
    assert "internal:page-2" in urls
    assert all(item.text_preview for item in summaries)
    assert all(item.drawing_id is None for item in summaries)


def test_follow_and_capture_links_delegates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "ai.pipelines.pdf_link_follower.settings.pdf_link_follow_enabled",
        True,
    )
    pdf_path = _pdf_with_internal_link(tmp_path)

    result = follow_and_capture_links(pdf_path)

    assert isinstance(result, LinkFollowResult)
    assert "COLO" in result.supplemental_text


@patch("ai.agents.tools.pdf_investigation.extract_document")
@patch("ai.agents.tools.pdf_investigation.follow_and_capture_links")
def test_run_pdf_investigation_returns_link_result_and_merged_text(
    mock_follow: MagicMock,
    mock_extract: MagicMock,
    tmp_path: Path,
) -> None:
    from ai.pipelines.document_text_extraction import ExtractedDocument, SourceFormat

    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    mock_extract.return_value = ExtractedDocument(
        source_format=SourceFormat.NATIVE_PDF,
        page_count=1,
        words=[],
    )
    mock_follow.return_value = LinkFollowResult(
        supplemental_text="Linked install sheet",
        followed_count=1,
    )

    payload = run_pdf_investigation(pdf_path, max_links=0)

    assert payload.link_result is mock_follow.return_value
    assert payload.base_text == ""
    assert payload.merged_text == "Linked install sheet"
    assert payload.links_followed == 1
