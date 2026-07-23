"""Tests for document text extraction orchestration and data types."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

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


def fake_ocr_scanned_pdf(file_path: str | Path) -> ExtractedDocument:
    page0 = [
        _word("Sheet", page_index=0, y=50.0),
        _word("U1.C4.31", page_index=0, y=50.0),
    ]
    page1 = [_word("Approved", page_index=1, y=60.0)]
    return ExtractedDocument(
        source_format=SourceFormat.SCANNED_PDF,
        page_count=2,
        words=page0 + page1,
    )


@pytest.fixture(autouse=True)
def fake_backends(request: pytest.FixtureRequest) -> Iterator[None]:
    if request.node.name in {
        "test_real_backends_require_ocr_backend_without_patches",
        "test_pdf_has_text_layer_native_pdf",
        "test_pdf_has_text_layer_scanned_pdf",
        "test_pdf_text_layer_extracts_words_with_boxes",
        "test_ocr_scanned_pdf_rasterizes_each_page_in_memory",
    }:
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
            "ai.pipelines.document_text_extraction._ocr_scanned_pdf",
            side_effect=fake_ocr_scanned_pdf,
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


@patch("ai.pipelines.ocr_engine._openai_vision_is_available", return_value=False)
@patch("ai.pipelines.ocr_engine.tesseract_is_available", return_value=False)
def test_real_backends_require_ocr_backend_without_patches(
    _mock_tesseract: MagicMock,
    _mock_openai: MagicMock,
) -> None:
    from ai.pipelines import document_text_extraction as module

    with pytest.raises(RuntimeError, match="No OCR backend available"):
        module._ocr_image("/tmp/file.png")


def test_pdf_has_text_layer_native_pdf(tmp_path: Path) -> None:
    import fitz

    from ai.pipelines.document_text_extraction import _pdf_has_text_layer

    native_path = tmp_path / "native.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Underground Fire Water Rough In — Utility MR")
    doc.save(str(native_path))
    doc.close()

    assert _pdf_has_text_layer(native_path) is True


def test_pdf_has_text_layer_scanned_pdf(tmp_path: Path) -> None:
    import fitz

    from ai.pipelines.document_text_extraction import _pdf_has_text_layer

    scanned_path = tmp_path / "scanned.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(str(scanned_path))
    doc.close()

    assert _pdf_has_text_layer(scanned_path) is False


def test_pdf_text_layer_extracts_words_with_boxes(tmp_path: Path) -> None:
    import fitz

    from ai.pipelines.document_text_extraction import (
        SourceFormat,
        _pdf_text_layer,
    )

    pdf_path = tmp_path / "report.pdf"
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 100), "Hydrostatic Test Passed")
    doc.save(str(pdf_path))
    doc.close()

    extracted = _pdf_text_layer(pdf_path)
    assert extracted.source_format == SourceFormat.NATIVE_PDF
    assert extracted.page_count == 1
    assert extracted.words
    assert all(w.page_index == 0 for w in extracted.words)
    assert all(w.bbox.page_width == 612.0 for w in extracted.words)
    assert all(w.bbox.page_height == 792.0 for w in extracted.words)
    assert "Hydrostatic" in extracted.full_text()
    assert "Passed" in extracted.full_text()


def test_ocr_scanned_pdf_rasterizes_each_page_in_memory(tmp_path: Path) -> None:
    """Real PyMuPDF PDF; OCR is mocked — verifies in-memory per-page raster path."""
    import fitz

    from ai.pipelines.document_text_extraction import (
        SourceFormat,
        _ocr_scanned_pdf,
    )

    pdf_path = tmp_path / "scanned-two-page.pdf"
    doc = fitz.open()
    doc.new_page(width=612, height=792)
    doc.new_page(width=612, height=792)
    doc.save(str(pdf_path))
    doc.close()

    page_indices: list[int] = []

    def fake_ocr_page(
        file_path: str | Path,
        page_index: int = 0,
        **kwargs: object,
    ) -> tuple[list[PositionedWord], float, float]:
        page_indices.append(page_index)
        return (
            [
                PositionedWord(
                    text=f"page-{page_index + 1}",
                    bbox=_bbox(y=40.0, page_width=1700.0, page_height=2200.0),
                    page_index=page_index,
                )
            ],
            1700.0,
            2200.0,
        )

    with patch(
        "ai.pipelines.ocr_engine.ocr_pdf_page_in_memory",
        side_effect=fake_ocr_page,
    ):
        extracted = _ocr_scanned_pdf(pdf_path)

    assert page_indices == [0, 1]
    assert extracted.source_format == SourceFormat.SCANNED_PDF
    assert extracted.page_count == 2
    assert extracted.page_text(0) == "page-1"
    assert extracted.page_text(1) == "page-2"
    assert all(w.bbox.page_width == 1700.0 for w in extracted.words)
