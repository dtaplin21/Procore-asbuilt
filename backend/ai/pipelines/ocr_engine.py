"""
OCR backends for scanned evidence: Tesseract (positioned words) and OpenAI
vision (plain text → synthetic word boxes). PDF pages are rasterized in-process
via PyMuPDF — no poppler/pdf2image dependency.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Literal

import fitz  # PyMuPDF

from ai.pipelines.document_text_extraction import BoundingBox, PositionedWord
from ai.pipelines.openai_vision import extract_plain_text_from_image

logger = logging.getLogger(__name__)

OcrBackend = Literal["auto", "tesseract", "openai_vision"]

_DEFAULT_DPI = 200
_SYNTHETIC_OCR_CONFIDENCE = 0.75


def tesseract_is_available() -> bool:
    """Return True when pytesseract is importable and the tesseract binary runs."""
    try:
        import pytesseract
    except ImportError:
        return False

    _configure_tesseract_cmd()

    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        pass

    try:
        from config import settings
    except ImportError:
        return shutil.which("tesseract") is not None

    cmd = settings.tesseract_cmd or "tesseract"
    return shutil.which(cmd) is not None


def _configure_tesseract_cmd() -> None:
    try:
        from config import settings
        import pytesseract
    except ImportError:
        return

    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd


def _resolve_backend(backend: OcrBackend | None) -> OcrBackend:
    if backend is not None:
        return backend
    try:
        from config import settings
    except ImportError:
        return "auto"
    return settings.ocr_backend  # type: ignore[return-value]


def _openai_vision_is_available() -> bool:
    try:
        from config import settings
    except ImportError:
        return False
    return bool(getattr(settings, "openai_api_key", None))


def _load_pil_image(
    *,
    file_path: str | Path | None = None,
    image_bytes: bytes | None = None,
):
    from PIL import Image

    if image_bytes is not None:
        return Image.open(BytesIO(image_bytes))
    if file_path is not None:
        return Image.open(file_path)
    raise ValueError("Provide file_path or image_bytes")


def _plain_text_to_positioned_words(
    text: str,
    *,
    page_index: int,
    page_width: float,
    page_height: float,
) -> list[PositionedWord]:
    """Lay out plain OCR text into synthetic left-to-right word boxes."""
    stripped = (text or "").strip()
    if not stripped:
        return []

    margin_x = page_width * 0.05
    margin_y = page_height * 0.05
    usable_width = max(page_width - (2 * margin_x), 1.0)
    line_height = max(12.0, page_height * 0.04)

    words: list[PositionedWord] = []
    lines = stripped.splitlines() or [stripped]
    for line_idx, line in enumerate(lines):
        tokens = line.split()
        if not tokens:
            continue
        y = margin_y + (line_idx * line_height)
        slot_width = usable_width / len(tokens)
        for token_idx, token in enumerate(tokens):
            x = margin_x + (token_idx * slot_width)
            width = max(len(token) * 8.0, slot_width * 0.85)
            words.append(
                PositionedWord(
                    text=token,
                    bbox=BoundingBox(
                        x=x,
                        y=y,
                        width=width,
                        height=line_height * 0.85,
                        page_width=page_width,
                        page_height=page_height,
                    ),
                    page_index=page_index,
                    ocr_confidence=_SYNTHETIC_OCR_CONFIDENCE,
                )
            )
    return words


def ocr_image_tesseract(
    *,
    file_path: str | Path | None = None,
    image_bytes: bytes | None = None,
    page_index: int = 0,
) -> tuple[list[PositionedWord], float, float]:
    """Run Tesseract ``image_to_data`` and map rows into ``PositionedWord`` list."""
    if not tesseract_is_available():
        raise RuntimeError("Tesseract is not available")

    import pytesseract

    _configure_tesseract_cmd()

    with _load_pil_image(file_path=file_path, image_bytes=image_bytes) as image:
        page_width, page_height = float(image.width), float(image.height)
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)

    words: list[PositionedWord] = []
    count = len(data.get("text", []))
    for i in range(count):
        text = str(data["text"][i]).strip()
        if not text:
            continue
        try:
            conf = int(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1
        if conf < 0:
            continue

        left = float(data["left"][i])
        top = float(data["top"][i])
        width = float(data["width"][i])
        height = float(data["height"][i])
        words.append(
            PositionedWord(
                text=text,
                bbox=BoundingBox(
                    x=left,
                    y=top,
                    width=max(width, 1.0),
                    height=max(height, 1.0),
                    page_width=page_width,
                    page_height=page_height,
                ),
                page_index=page_index,
                ocr_confidence=max(0.0, min(1.0, conf / 100.0)),
            )
        )

    return words, page_width, page_height


def ocr_image_openai_vision(
    *,
    file_path: str | Path | None = None,
    image_bytes: bytes | None = None,
    page_index: int = 0,
) -> tuple[list[PositionedWord], float, float]:
    """Use OpenAI vision OCR and synthesize approximate word positions."""
    with _load_pil_image(file_path=file_path, image_bytes=image_bytes) as image:
        page_width, page_height = float(image.width), float(image.height)

    plain_text = extract_plain_text_from_image(
        file_path=file_path,
        image_bytes=image_bytes,
    )
    words = _plain_text_to_positioned_words(
        plain_text,
        page_index=page_index,
        page_width=page_width,
        page_height=page_height,
    )
    return words, page_width, page_height


def ocr_image(
    file_path: str | Path | None = None,
    *,
    image_bytes: bytes | None = None,
    page_index: int = 0,
    backend: OcrBackend | None = None,
) -> tuple[list[PositionedWord], float, float]:
    """
    Dispatch OCR to the configured backend.

    ``auto`` tries Tesseract first, then falls back to OpenAI vision when
    Tesseract is missing or raises.
    """
    if file_path is None and image_bytes is None:
        raise ValueError("Provide file_path or image_bytes")

    mode = _resolve_backend(backend)

    if mode == "tesseract":
        return ocr_image_tesseract(
            file_path=file_path,
            image_bytes=image_bytes,
            page_index=page_index,
        )

    if mode == "openai_vision":
        if not _openai_vision_is_available():
            raise RuntimeError("OpenAI vision OCR requested but OPENAI_API_KEY is not set")
        return ocr_image_openai_vision(
            file_path=file_path,
            image_bytes=image_bytes,
            page_index=page_index,
        )

    # auto
    if tesseract_is_available():
        try:
            return ocr_image_tesseract(
                file_path=file_path,
                image_bytes=image_bytes,
                page_index=page_index,
            )
        except Exception as exc:
            logger.warning("tesseract_ocr_failed", extra={"error": str(exc)})

    if _openai_vision_is_available():
        return ocr_image_openai_vision(
            file_path=file_path,
            image_bytes=image_bytes,
            page_index=page_index,
        )

    raise RuntimeError(
        "No OCR backend available — install tesseract + pytesseract or set OPENAI_API_KEY"
    )


def _render_pdf_page_bytes(
    file_path: str | Path,
    page_index: int,
    *,
    dpi: int = _DEFAULT_DPI,
) -> tuple[bytes, float, float]:
    doc = fitz.open(str(file_path))
    try:
        if page_index < 0 or page_index >= doc.page_count:
            raise IndexError(f"page_index {page_index} out of range (pages={doc.page_count})")
        page = doc.load_page(page_index)
        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        return pixmap.tobytes("png"), float(pixmap.width), float(pixmap.height)
    finally:
        doc.close()


def rasterize_pdf_pages(
    file_path: str | Path,
    *,
    dpi: int = _DEFAULT_DPI,
    output_dir: str | Path | None = None,
) -> list[Path]:
    """Render each PDF page to PNG via PyMuPDF. Returns written file paths."""
    source = Path(file_path)
    doc = fitz.open(str(source))
    paths: list[Path] = []
    temp_dir: tempfile.TemporaryDirectory[str] | None = None

    try:
        if output_dir is None:
            temp_dir = tempfile.TemporaryDirectory(prefix="ocr_pages_")
            out_dir = Path(temp_dir.name)
        else:
            out_dir = Path(output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)

        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        stem = source.stem or "page"

        for page_index in range(doc.page_count):
            page = doc.load_page(page_index)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            out_path = out_dir / f"{stem}_page_{page_index:04d}.png"
            pixmap.save(str(out_path))
            paths.append(out_path)

        if temp_dir is not None:
            paths._tempdir = temp_dir  # type: ignore[attr-defined]
    finally:
        doc.close()

    return paths


def ocr_pdf_page_in_memory(
    file_path: str | Path,
    page_index: int = 0,
    *,
    dpi: int = _DEFAULT_DPI,
    backend: OcrBackend | None = None,
) -> tuple[list[PositionedWord], float, float]:
    """Rasterize one PDF page in memory and OCR without writing intermediate files."""
    png_bytes, page_width, page_height = _render_pdf_page_bytes(
        file_path,
        page_index,
        dpi=dpi,
    )
    words, _, _ = ocr_image(
        image_bytes=png_bytes,
        page_index=page_index,
        backend=backend,
    )
    # Re-attach dimensions from the rasterized pixmap (authoritative for PDF pages).
    fixed_words = [
        PositionedWord(
            text=w.text,
            bbox=BoundingBox(
                x=w.bbox.x,
                y=w.bbox.y,
                width=w.bbox.width,
                height=w.bbox.height,
                page_width=page_width,
                page_height=page_height,
            ),
            page_index=w.page_index,
            ocr_confidence=w.ocr_confidence,
        )
        for w in words
    ]
    return fixed_words, page_width, page_height
