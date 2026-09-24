"""Choose vector vs raster line extraction for a PDF page."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import fitz

# Below these counts → treat as raster-only (scanned or flattened) sheet.
_MIN_LINE_OPS_FOR_VECTOR = 500
_MIN_STROKED_PATHS_FOR_VECTOR = 100


class PdfLineSource(str, Enum):
    VECTOR = "vector"
    RASTER = "raster"


@dataclass(frozen=True)
class PdfLineSourceStats:
    path_count: int
    line_op_count: int
    stroked_path_count: int


def _count_drawing_ops(drawings: list[dict[str, Any]]) -> tuple[int, int, int]:
    path_count = len(drawings)
    line_ops = 0
    stroked = 0
    for path in drawings:
        items = path.get("items") or []
        has_line = any(item and item[0] == "l" for item in items)
        if has_line and path.get("type") == "s":
            stroked += 1
        for item in items:
            if item and item[0] == "l":
                line_ops += 1
    return path_count, line_ops, stroked


def classify_pdf_line_source(
    pdf_path: Path | str,
    *,
    page: int = 1,
) -> tuple[PdfLineSource, PdfLineSourceStats]:
    """Classify whether linework should be read from PDF vectors or raster CV."""
    doc = fitz.open(str(pdf_path))
    try:
        if page < 1 or page > doc.page_count:
            raise ValueError(f"page {page} out of range (1..{doc.page_count})")
        page_obj = doc.load_page(page - 1)
        drawings = page_obj.get_drawings()
    finally:
        doc.close()

    path_count, line_ops, stroked = _count_drawing_ops(drawings)
    stats = PdfLineSourceStats(path_count, line_ops, stroked)
    if line_ops >= _MIN_LINE_OPS_FOR_VECTOR and stroked >= _MIN_STROKED_PATHS_FOR_VECTOR:
        return PdfLineSource.VECTOR, stats
    return PdfLineSource.RASTER, stats
