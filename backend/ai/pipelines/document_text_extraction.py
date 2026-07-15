"""
Normalizes any imported evidence file (native PDF, scanned PDF, photo,
scanned drawing sheet) into one common representation: a flat list of
PositionedWord — text + its bounding box on the page it came from.

This is the layer that sits BEFORE term extraction. Whatever format the
file arrives in, everything downstream (positioned_term_extractor.py,
drawing_location_resolver.py) only ever deals with PositionedWord lists,
so the vocabulary-matching and location-resolution logic doesn't need to
know or care whether the original file was a PDF or a phone photo.

Source-format handling
-----------------------
- Native PDF (has a real text layer): extract words + boxes directly from
  the PDF's text layer. No OCR needed, highest position accuracy.
- Scanned PDF (text layer empty/garbage) or image/photo: rasterize (PDF
  case) or load directly (image case), then run OCR to get words + boxes.
- The same OCR backend handles "scanned PDF page" and "phone photo of a
  printed sheet" identically once rasterized to an image — per your
  answer, the correlating language is present either way, just without a
  text layer to read off directly.

This module defines the interfaces and orchestration; the actual OCR and
PDF-text-layer calls are wrapped behind small adapter functions
(_ocr_image, _pdf_text_layer) so the real OCR engine (e.g. Tesseract,
a cloud OCR API, or an in-house model) can be swapped in without touching
calling code. The adapters here are stubbed with a clearly-marked
NotImplementedError boundary plus a deterministic test double used by the
test suite, since no OCR engine is wired into this environment.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import fitz  # PyMuPDF


class SourceFormat(str, Enum):
    NATIVE_PDF = "native_pdf"  # PDF with an extractable text layer
    SCANNED_PDF = "scanned_pdf"  # PDF that is just rasterized images
    IMAGE = "image"  # standalone photo / scanned page (jpg, png, etc.)


@dataclass(frozen=True)
class BoundingBox:
    """Bounding box in page-pixel (or PDF point) coordinates, top-left
    origin. page_width/page_height are included so downstream consumers
    can normalize to 0-1 fractional coordinates regardless of source DPI.
    """

    x: float
    y: float
    width: float
    height: float
    page_width: float
    page_height: float

    def to_fractional(self) -> tuple[float, float, float, float]:
        """(x0, y0, x1, y1) as fractions of page width/height — the
        common coordinate space used once we leave this module, since
        page pixel dimensions vary by scan DPI / photo resolution.
        """
        x0 = self.x / self.page_width
        y0 = self.y / self.page_height
        x1 = (self.x + self.width) / self.page_width
        y1 = (self.y + self.height) / self.page_height
        return (x0, y0, x1, y1)

    def to_dict(self) -> dict:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "pageWidth": self.page_width,
            "pageHeight": self.page_height,
        }


@dataclass(frozen=True)
class PositionedWord:
    """A single word/token plus where it sits on the page it came from.
    page_index is 0-based; multi-page PDFs produce one PositionedWord per
    word per page.
    """

    text: str
    bbox: BoundingBox
    page_index: int
    # OCR engines report a per-word confidence; native PDF text layers are
    # always presumed exact (1.0). This is the *recognition* confidence
    # (did we read the right characters), independent of and upstream from
    # the *vocabulary match* confidence computed later in term_extractor.
    ocr_confidence: float = 1.0


@dataclass(frozen=True)
class ExtractedDocument:
    """The normalized output of this module: every word on every page,
    positioned, regardless of source format.
    """

    source_format: SourceFormat
    page_count: int
    words: list[PositionedWord]

    def page_text(self, page_index: int) -> str:
        """Reconstruct plain text for a page, in reading order, for
        feeding the plain-string extract_terms() path when only the text
        (not positions) is needed.
        """
        page_words = [w for w in self.words if w.page_index == page_index]
        # Words are expected to already be in reading order from the
        # extraction backend (PDF text layers and OCR engines both emit
        # reading-order tokens); re-sort defensively by y then x as a
        # fallback for engines that don't guarantee this.
        page_words.sort(key=lambda w: (round(w.bbox.y, 1), w.bbox.x))
        return " ".join(w.text for w in page_words)

    def full_text(self) -> str:
        return "\n".join(self.page_text(i) for i in range(self.page_count))


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

def detect_source_format(file_path: str | Path, has_text_layer: bool | None = None) -> SourceFormat:
    """Determine which extraction path a file needs.

    Args:
        file_path: path to the uploaded evidence file.
        has_text_layer: if the caller already knows whether a PDF has a
            usable text layer (e.g. from a prior pdfplumber/pypdf probe),
            pass it here to skip re-probing. Ignored for non-PDF files.
    """
    suffix = Path(file_path).suffix.lower()
    if suffix == ".pdf":
        if has_text_layer is None:
            has_text_layer = _pdf_has_text_layer(file_path)
        return SourceFormat.NATIVE_PDF if has_text_layer else SourceFormat.SCANNED_PDF
    if suffix in {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}:
        return SourceFormat.IMAGE
    raise ValueError(f"Unsupported evidence file type: {suffix!r}")


# ---------------------------------------------------------------------------
# Extraction backends (adapter boundary)
# ---------------------------------------------------------------------------
# These three functions are the seam where a real PDF library / OCR engine
# gets wired in. Swap the implementations; keep the signatures.

def _pdf_has_text_layer(file_path: str | Path) -> bool:
    """Probe whether a PDF has a real, extractable text layer vs. being
    just scanned images. Uses PyMuPDF to read page-0 text; >= 20 non-ws
    chars on the first page counts as native PDF (OCR not required).
    """
    doc = fitz.open(str(file_path))
    try:
        if doc.page_count == 0:
            return False
        text = doc.load_page(0).get_text("text") or ""
        return len(text.strip()) >= 20
    finally:
        doc.close()


def _pdf_text_layer(file_path: str | Path) -> ExtractedDocument:
    """Extract words + boxes directly from a native PDF's text layer."""
    doc = fitz.open(str(file_path))
    words: list[PositionedWord] = []
    try:
        for page_index in range(doc.page_count):
            page = doc.load_page(page_index)
            pw, ph = page.rect.width, page.rect.height
            for w in page.get_text("words"):  # x0,y0,x1,y1, word, block, line, word_no
                x0, y0, x1, y1, text, *_ = w
                if not str(text).strip():
                    continue
                words.append(
                    PositionedWord(
                        text=str(text),
                        bbox=BoundingBox(
                            x=float(x0),
                            y=float(y0),
                            width=float(x1 - x0),
                            height=float(y1 - y0),
                            page_width=float(pw),
                            page_height=float(ph),
                        ),
                        page_index=page_index,
                    )
                )
        return ExtractedDocument(
            source_format=SourceFormat.NATIVE_PDF,
            page_count=doc.page_count,
            words=words,
        )
    finally:
        doc.close()


def _ocr_image(file_path: str | Path, page_index: int = 0) -> tuple[list[PositionedWord], float, float]:
    """Run OCR on a single rasterized page / standalone image.
    Returns (words, page_width, page_height).
    Real implementation: Tesseract (pytesseract.image_to_data) or a cloud
    OCR API, mapped into PositionedWord with per-word confidence.
    """
    raise NotImplementedError(
        "Wire up an OCR backend (e.g. pytesseract.image_to_data) here."
    )


def _rasterize_pdf_pages(file_path: str | Path) -> list[Path]:
    """Render each page of a scanned PDF to an image for OCR.
    Real implementation: pdf2image.convert_from_path / poppler.
    """
    raise NotImplementedError(
        "Wire up PDF rasterization (e.g. pdf2image) here."
    )


# ---------------------------------------------------------------------------
# Public orchestration
# ---------------------------------------------------------------------------

def extract_document(file_path: str | Path) -> ExtractedDocument:
    """Main entry point: take any supported evidence file and return its
    normalized, positioned text — the single function inspection_mapping.py
    calls regardless of what kind of file came in.
    """
    fmt = detect_source_format(file_path)

    if fmt == SourceFormat.NATIVE_PDF:
        return _pdf_text_layer(file_path)

    if fmt == SourceFormat.IMAGE:
        words, page_w, page_h = _ocr_image(file_path, page_index=0)
        return ExtractedDocument(
            source_format=fmt, page_count=1, words=words
        )

    if fmt == SourceFormat.SCANNED_PDF:
        page_images = _rasterize_pdf_pages(file_path)
        all_words: list[PositionedWord] = []
        for page_index, page_image_path in enumerate(page_images):
            words, _, _ = _ocr_image(page_image_path, page_index=page_index)
            all_words.extend(words)
        return ExtractedDocument(
            source_format=fmt, page_count=len(page_images), words=all_words
        )

    raise AssertionError(f"unhandled format: {fmt}")  # exhaustiveness guard
