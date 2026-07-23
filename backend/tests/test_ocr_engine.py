"""Tests for OCR engine dispatch, PDF rasterization, and synthetic vision layout."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import fitz
import pytest

from ai.pipelines.document_text_extraction import BoundingBox, PositionedWord
from ai.pipelines.ocr_engine import (
    _plain_text_to_positioned_words,
    _render_pdf_page_bytes,
    ocr_image,
    ocr_image_openai_vision,
    ocr_image_tesseract,
    ocr_pdf_page_in_memory,
    rasterize_pdf_pages,
    tesseract_is_available,
)

PNG_HEADER = b"\x89PNG\r\n\x1a\n"


def _tesseract_dict(*words: tuple[str, int, int, int, int, int]) -> dict[str, list]:
    """Build a minimal pytesseract image_to_data dict."""
    data: dict[str, list] = {
        "text": [],
        "conf": [],
        "left": [],
        "top": [],
        "width": [],
        "height": [],
    }
    for text, conf, left, top, width, height in words:
        data["text"].append(text)
        data["conf"].append(conf)
        data["left"].append(left)
        data["top"].append(top)
        data["width"].append(width)
        data["height"].append(height)
    return data


def test_tesseract_is_available_false_without_import() -> None:
    with patch.dict("sys.modules", {"pytesseract": None}):
        assert tesseract_is_available() is False


@patch("ai.pipelines.ocr_engine._configure_tesseract_cmd")
def test_tesseract_is_available_true_when_binary_runs(_mock_configure: MagicMock) -> None:
    mock_pytesseract = MagicMock()
    mock_pytesseract.get_tesseract_version.return_value = "5.3.0"
    with patch.dict("sys.modules", {"pytesseract": mock_pytesseract}):
        assert tesseract_is_available() is True


@patch("ai.pipelines.ocr_engine.tesseract_is_available", return_value=True)
@patch("ai.pipelines.ocr_engine._configure_tesseract_cmd")
@patch("ai.pipelines.ocr_engine._load_pil_image")
def test_ocr_image_tesseract_maps_image_to_data(
    mock_load: MagicMock,
    _mock_configure: MagicMock,
    _mock_tesseract_available: MagicMock,
) -> None:
    image = MagicMock()
    image.width = 800
    image.height = 600
    mock_load.return_value.__enter__.return_value = image

    mock_pytesseract = MagicMock()
    mock_pytesseract.image_to_data.return_value = _tesseract_dict(
        ("Hydrostatic", 92, 50, 100, 120, 18),
        ("", -1, 0, 0, 0, 0),
        ("Test", 88, 200, 100, 40, 18),
    )
    mock_pytesseract.Output.DICT = "dict"

    with patch.dict("sys.modules", {"pytesseract": mock_pytesseract}):
        words, page_w, page_h = ocr_image_tesseract(image_bytes=b"img")

    assert page_w == 800.0
    assert page_h == 600.0
    assert [w.text for w in words] == ["Hydrostatic", "Test"]
    assert words[0].ocr_confidence == pytest.approx(0.92)
    assert words[0].bbox.x == 50.0
    assert words[0].bbox.page_width == 800.0


def test_plain_text_to_positioned_words_builds_synthetic_boxes() -> None:
    words = _plain_text_to_positioned_words(
        "INSPECTION REPORT\nLine two",
        page_index=0,
        page_width=600.0,
        page_height=800.0,
    )

    assert [w.text for w in words] == ["INSPECTION", "REPORT", "Line", "two"]
    assert all(isinstance(w.bbox, BoundingBox) for w in words)
    assert all(w.page_index == 0 for w in words)
    assert words[0].bbox.page_width == 600.0


@patch("ai.pipelines.ocr_engine.extract_plain_text_from_image", return_value="Rough In Passed")
@patch("ai.pipelines.ocr_engine._load_pil_image")
def test_ocr_image_openai_vision_returns_synthetic_words(
    mock_load: MagicMock,
    mock_extract: MagicMock,
) -> None:
    image = MagicMock()
    image.width = 400
    image.height = 300
    mock_load.return_value.__enter__.return_value = image

    words, page_w, page_h = ocr_image_openai_vision(image_bytes=b"img")

    assert page_w == 400.0
    assert page_h == 300.0
    assert [w.text for w in words] == ["Rough", "In", "Passed"]
    mock_extract.assert_called_once_with(file_path=None, image_bytes=b"img")


@patch("ai.pipelines.ocr_engine.tesseract_is_available", return_value=True)
@patch("ai.pipelines.ocr_engine._openai_vision_is_available", return_value=True)
@patch("ai.pipelines.ocr_engine.ocr_image_tesseract")
@patch("ai.pipelines.ocr_engine.ocr_image_openai_vision")
def test_ocr_image_auto_prefers_tesseract(
    mock_openai: MagicMock,
    mock_tesseract: MagicMock,
    _mock_openai_available: MagicMock,
    _mock_tesseract_available: MagicMock,
) -> None:
    expected = ([PositionedWord(text="Local", bbox=BoundingBox(1, 2, 3, 4, 100, 100), page_index=0)], 100.0, 100.0)
    mock_tesseract.return_value = expected

    result = ocr_image(image_bytes=b"png", backend="auto")

    assert result == expected
    mock_tesseract.assert_called_once()
    mock_openai.assert_not_called()


@patch("ai.pipelines.ocr_engine.tesseract_is_available", return_value=False)
@patch("ai.pipelines.ocr_engine._openai_vision_is_available", return_value=True)
@patch("ai.pipelines.ocr_engine.ocr_image_openai_vision")
def test_ocr_image_auto_uses_openai_when_tesseract_missing(
    mock_openai: MagicMock,
    _mock_openai_available: MagicMock,
    _mock_tesseract: MagicMock,
) -> None:
    expected = ([PositionedWord(text="Hi", bbox=BoundingBox(1, 2, 3, 4, 100, 100), page_index=0)], 100.0, 100.0)
    mock_openai.return_value = expected

    result = ocr_image(image_bytes=b"png", backend="auto")

    assert result == expected
    mock_openai.assert_called_once()


@patch("ai.pipelines.ocr_engine.tesseract_is_available", return_value=True)
@patch("ai.pipelines.ocr_engine._openai_vision_is_available", return_value=True)
@patch("ai.pipelines.ocr_engine.ocr_image_tesseract", side_effect=RuntimeError("tesseract failed"))
@patch("ai.pipelines.ocr_engine.ocr_image_openai_vision")
def test_ocr_image_auto_falls_back_when_tesseract_raises(
    mock_openai: MagicMock,
    _mock_tesseract: MagicMock,
    _mock_openai_available: MagicMock,
    _mock_tesseract_available: MagicMock,
) -> None:
    expected = ([PositionedWord(text="Fallback", bbox=BoundingBox(1, 2, 3, 4, 100, 100), page_index=0)], 100.0, 100.0)
    mock_openai.return_value = expected

    result = ocr_image(image_bytes=b"png", backend="auto")

    assert result == expected
    mock_openai.assert_called_once()


@patch("ai.pipelines.ocr_engine.tesseract_is_available", return_value=False)
def test_ocr_image_tesseract_backend_raises_when_unavailable(
    _mock_available: MagicMock,
) -> None:
    with pytest.raises(RuntimeError, match="Tesseract is not available"):
        ocr_image(image_bytes=b"png", backend="tesseract")


@patch("ai.pipelines.ocr_engine._openai_vision_is_available", return_value=False)
def test_ocr_image_openai_backend_raises_without_api_key(_mock_openai: MagicMock) -> None:
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is not set"):
        ocr_image(image_bytes=b"png", backend="openai_vision")


def test_render_pdf_page_bytes_returns_valid_png(tmp_path: Path) -> None:
    pdf_path = tmp_path / "page.pdf"
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Rasterize me")
    doc.save(str(pdf_path))
    doc.close()

    png_bytes, page_w, page_h = _render_pdf_page_bytes(pdf_path, page_index=0, dpi=200)

    assert png_bytes.startswith(PNG_HEADER)
    assert page_w == pytest.approx(612 * 200 / 72, rel=0.01)
    assert page_h == pytest.approx(792 * 200 / 72, rel=0.01)


def test_rasterize_pdf_pages_writes_pngs(tmp_path: Path) -> None:
    pdf_path = tmp_path / "scan.pdf"
    doc = fitz.open()
    doc.new_page(width=300, height=400)
    doc.new_page(width=300, height=400)
    doc.save(str(pdf_path))
    doc.close()

    out_dir = tmp_path / "pages"
    paths = rasterize_pdf_pages(pdf_path, output_dir=out_dir)

    assert len(paths) == 2
    assert all(path.exists() for path in paths)
    assert all(path.suffix == ".png" for path in paths)
    assert all(path.read_bytes().startswith(PNG_HEADER) for path in paths)


@patch("ai.pipelines.ocr_engine.ocr_image")
def test_ocr_pdf_page_in_memory_rasterizes_real_pdf_then_ocrs(
    mock_ocr: MagicMock,
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "one-page.pdf"
    doc = fitz.open()
    doc.new_page(width=612, height=792)
    doc.save(str(pdf_path))
    doc.close()

    mock_ocr.return_value = (
        [
            PositionedWord(
                text="Test",
                bbox=BoundingBox(10, 20, 30, 10, 100, 100),
                page_index=0,
                ocr_confidence=0.9,
            )
        ],
        100.0,
        100.0,
    )

    words, page_w, page_h = ocr_pdf_page_in_memory(pdf_path, page_index=0)

    assert len(words) == 1
    assert words[0].text == "Test"
    assert words[0].bbox.page_width == page_w
    assert words[0].bbox.page_height == page_h
    assert page_w > 612
    assert page_h > 792
    mock_ocr.assert_called_once()
    png_bytes = mock_ocr.call_args.kwargs["image_bytes"]
    assert png_bytes.startswith(PNG_HEADER)


def test_ocr_image_requires_input() -> None:
    with pytest.raises(ValueError, match="Provide file_path or image_bytes"):
        ocr_image()
