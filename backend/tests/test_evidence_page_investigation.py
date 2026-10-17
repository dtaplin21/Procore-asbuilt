"""Tests for per-page OCR + vision during link investigation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import fitz

from ai.pipelines.evidence_page_investigation import (
    PageInvestigationResult,
    investigate_pdf_all_pages,
    investigate_pdf_page,
)


def _two_page_pdf(tmp_path: Path) -> Path:
    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    doc[0].insert_text((72, 72), "Page one STA 10+00")
    doc[1].insert_text((72, 72), "Page two STA 10+90")
    path = tmp_path / "two.pdf"
    doc.save(path)
    doc.close()
    return path


@patch("ai.pipelines.evidence_page_investigation._vision_text_for_pdf_page")
@patch("ai.pipelines.evidence_page_investigation.extract_drawing_document_for_inspection")
def test_investigate_pdf_all_pages_runs_vision_per_page(
    mock_ocr: MagicMock,
    mock_vision: MagicMock,
    tmp_path: Path,
) -> None:
    from ai.pipelines.document_text_extraction import (
        BoundingBox,
        ExtractedDocument,
        PositionedWord,
        SourceFormat,
    )

    pdf_path = _two_page_pdf(tmp_path)
    bbox = BoundingBox(x=0, y=0, width=10, height=10, page_width=100, page_height=100)
    mock_ocr.return_value = ExtractedDocument(
        source_format=SourceFormat.SCANNED_PDF,
        page_count=2,
        words=[
            PositionedWord(text="Page", bbox=bbox, page_index=0),
            PositionedWord(text="one", bbox=bbox, page_index=0),
            PositionedWord(text="STA", bbox=bbox, page_index=0),
            PositionedWord(text="10+00", bbox=bbox, page_index=0),
            PositionedWord(text="Page", bbox=bbox, page_index=1),
            PositionedWord(text="two", bbox=bbox, page_index=1),
            PositionedWord(text="STA", bbox=bbox, page_index=1),
            PositionedWord(text="10+90", bbox=bbox, page_index=1),
        ],
    )
    mock_vision.side_effect = ["vision-one", "vision-two"]

    results, document = investigate_pdf_all_pages(pdf_path)

    assert document.page_count == 2
    assert len(results) == 2
    assert mock_vision.call_count == 2
    assert "vision-one" in results[0].combined_text
    assert "10+90" in results[1].combined_text


@patch("ai.pipelines.evidence_page_investigation._vision_text_for_pdf_page", return_value="")
@patch("ai.pipelines.evidence_page_investigation.extract_drawing_document_for_inspection")
def test_investigate_pdf_page_single(
    mock_ocr: MagicMock,
    _mock_vision: MagicMock,
    tmp_path: Path,
) -> None:
    from ai.pipelines.document_text_extraction import (
        BoundingBox,
        ExtractedDocument,
        PositionedWord,
        SourceFormat,
    )

    pdf_path = _two_page_pdf(tmp_path)
    bbox = BoundingBox(x=0, y=0, width=10, height=10, page_width=100, page_height=100)
    mock_ocr.return_value = ExtractedDocument(
        source_format=SourceFormat.SCANNED_PDF,
        page_count=2,
        words=[
            PositionedWord(text="Page", bbox=bbox, page_index=1),
            PositionedWord(text="two", bbox=bbox, page_index=1),
            PositionedWord(text="STA", bbox=bbox, page_index=1),
            PositionedWord(text="10+90", bbox=bbox, page_index=1),
        ],
    )

    result = investigate_pdf_page(pdf_path, page=2)

    assert isinstance(result, PageInvestigationResult)
    assert result.page == 2
    assert "10+90" in result.combined_text
