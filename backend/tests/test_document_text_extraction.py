"""Tests for document text extraction orchestration and data types."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from ai.pipelines.document_text_extraction import (
    BoundingBox,
    ExtractedDocument,
    PositionedWord,
    SourceFormat,
    detect_source_format,
    extract_document,
)


def _bbox(
    x: float = 10.0,
    y: float = 20.0,
    width: float = 40.0,
    height: float = 12.0,
    page_width: float = 612.0,
    page_height: float = 792.0,
) -> BoundingBox:
    return BoundingBox(
        x=x,
        y=y,
        width=width,
        height=height,
        page_width=page_width,
        page_height=page_height,
    )


def _word(text: str, page_index: int = 0, y: float = 20.0) -> PositionedWord:
    return PositionedWord(text=text, bbox=_bbox(y=y), page_index=page_index)


# ---------------------------------------------------------------------------
# Deterministic fake backends (referenced by module docstring)
# ---------------------------------------------------------------------------

def fake_pdf_has_text_layer(file_path: str | Path) -> bool:
    return "native" in Path(file_path).stem.lower()


def fake_pdf_text_layer(file_path: str | Path) -> ExtractedDocument:
    return ExtractedDocument(
        source_format=SourceFormat.NATIVE_PDF,
        page_count=1,
        words=[
            _word("Hydrostatic", y=100.0),
            _word("Test", y=100.0),
            _word("Passed", y=120.0),
        ],
    )


def fake_ocr_image(
    file_path: str | Path,
    page_index: int = 0,
) -> tuple[list[PositionedWord], float, float]:
    stem = Path(file_path).stem.lower()
    if "page1" in stem:
        words = [_word("Sheet", page_index=page_index, y=50.0), _word("U1.C4.31", page_index=page_index, y=50.0)]
    elif "page2" in stem:
        words = [_word("Approved", page_index=page_index, y=60.0)]
    else:
        words = [_word("Rough-In", page_index=page_index, y=30.0)]
    return words, 612.0, 792.0


def fake_rasterize_pdf_pages(file_path: str | Path) -> list[Path]:
    return [Path("/tmp/scanned-page1.png"), Path("/tmp/scanned-page2.png")]


@pytest.fixture(autouse=True)
def fake_backends(request: pytest.FixtureRequest) -> Iterator[None]:
    if request.node.name == "test_real_backends_raise_not_implemented_without_patches":
        yield
        return
    with (
        patch(
            "ai.pipelines.document_text_extraction._pdf_has_text_layer",
            side_effect=fake_pdf_has_text_layer,
        ),
        patch(
            "ai.pipelines.document_text_extraction._pdf_text_layer",
            side_effect=fake_pdf_text_layer,
        ),
        patch(
            "ai.pipelines.document_text_extraction._ocr_image",
            side_effect=fake_ocr_image,
        ),
        patch(
            "ai.pipelines.document_text_extraction._rasterize_pdf_pages",
            side_effect=fake_rasterize_pdf_pages,
        ),
    ):
        yield


def test_bounding_box_to_fractional() -> None:
    box = _bbox(x=61.2, y=79.2, width=122.4, height=39.6)
    assert box.to_fractional() == pytest.approx((0.1, 0.1, 0.3, 0.15))


def test_bounding_box_to_dict_uses_camel_case_page_dims() -> None:
    payload = _bbox().to_dict()
    assert payload["pageWidth"] == 612.0
    assert payload["pageHeight"] == 792.0


def test_extracted_document_page_text_sorts_by_reading_order() -> None:
    doc = ExtractedDocument(
        source_format=SourceFormat.NATIVE_PDF,
        page_count=1,
        words=[
            _word("second", y=120.0),
            _word("first", y=100.0),
        ],
    )
    assert doc.page_text(0) == "first second"


def test_extracted_document_full_text_joins_pages() -> None:
    doc = ExtractedDocument(
        source_format=SourceFormat.SCANNED_PDF,
        page_count=2,
        words=[
            _word("page-one", page_index=0),
            _word("page-two", page_index=1),
        ],
    )
    assert doc.full_text() == "page-one\npage-two"


def test_detect_source_format_native_pdf() -> None:
    assert detect_source_format("/evidence/native-report.pdf") == SourceFormat.NATIVE_PDF


def test_detect_source_format_scanned_pdf() -> None:
    assert detect_source_format("/evidence/scanned-report.pdf") == SourceFormat.SCANNED_PDF


def test_detect_source_format_image() -> None:
    assert detect_source_format("/evidence/site-photo.JPG") == SourceFormat.IMAGE


def test_detect_source_format_skips_probe_when_hint_provided() -> None:
    with patch(
        "ai.pipelines.document_text_extraction._pdf_has_text_layer"
    ) as probe:
        assert detect_source_format("/evidence/file.pdf", has_text_layer=False) == SourceFormat.SCANNED_PDF
        probe.assert_not_called()


def test_detect_source_format_rejects_unknown_suffix() -> None:
    with pytest.raises(ValueError, match="Unsupported evidence file type"):
        detect_source_format("/evidence/report.docx")


def test_extract_document_native_pdf() -> None:
    doc = extract_document("/evidence/native-report.pdf")
    assert doc.source_format == SourceFormat.NATIVE_PDF
    assert doc.page_count == 1
    assert doc.full_text() == "Hydrostatic Test Passed"


def test_extract_document_image() -> None:
    doc = extract_document("/evidence/field-photo.png")
    assert doc.source_format == SourceFormat.IMAGE
    assert doc.page_count == 1
    assert doc.full_text() == "Rough-In"


def test_extract_document_scanned_pdf() -> None:
    doc = extract_document("/evidence/scanned-report.pdf")
    assert doc.source_format == SourceFormat.SCANNED_PDF
    assert doc.page_count == 2
    assert "Sheet U1.C4.31" in doc.page_text(0)
    assert doc.page_text(1) == "Approved"


def test_real_backends_raise_not_implemented_without_patches() -> None:
    from ai.pipelines import document_text_extraction as module

    with pytest.raises(NotImplementedError):
        module._pdf_has_text_layer("/tmp/file.pdf")
