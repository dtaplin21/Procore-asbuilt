"""Unit tests for PDF hyperlink extraction and internal link following."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from ai.pipelines.pdf_link_follower import (
    PdfLinkKind,
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
