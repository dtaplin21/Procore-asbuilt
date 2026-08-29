#!/usr/bin/env python3
"""Export one drawing PDF page to PNG for digitization fixtures / manual picking.

Usage (from ``backend/``)::

    ./venv/bin/python scripts/export_drawing_page_png.py \\
      --drawing-id 661 --page 1 \\
      --out tests/fixtures/digitization/master_661_page1.png

    ./venv/bin/python scripts/export_drawing_page_png.py \\
      --drawing-id 1501 --page 1 \\
      --out tests/fixtures/digitization/aux_c420_page1.png

Default DPI is 150 (digitization PRE-2 convention; ``ocr_engine`` default is 200).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import cast

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

import fitz  # noqa: E402
from database import SessionLocal  # noqa: E402
from models.models import Drawing  # noqa: E402
from services.file_storage import resolve_stored_file_path  # noqa: E402

DEFAULT_DPI = 150


def export_drawing_page_png(
    *,
    drawing_id: int,
    page: int,
    out_path: Path,
    dpi: int = DEFAULT_DPI,
) -> Path:
    """Rasterize ``page`` (1-based) of a stored drawing PDF to ``out_path``."""
    if page < 1:
        raise ValueError(f"page must be >= 1, got {page}")
    if dpi < 36:
        raise ValueError(f"dpi too low: {dpi}")

    db = SessionLocal()
    try:
        drawing = db.get(Drawing, drawing_id)
        if drawing is None:
            raise ValueError(f"Drawing {drawing_id} not found")
        storage_key = cast(str | None, drawing.storage_key)
        if not storage_key:
            raise ValueError(f"Drawing {drawing_id} has no storage_key")
        pdf_path = resolve_stored_file_path(storage_key)
        if pdf_path is None or not pdf_path.exists():
            raise FileNotFoundError(
                f"Drawing {drawing_id} PDF not on disk for key {storage_key!r}. "
                f"Expected under uploads/ (see tests/fixtures/digitization/README.md)."
            )
    finally:
        db.close()

    doc = fitz.open(str(pdf_path))
    try:
        page_index = page - 1
        if page_index >= doc.page_count:
            raise IndexError(
                f"page {page} out of range (drawing {drawing_id} has {doc.page_count} pages)"
            )
        pdf_page = doc.load_page(page_index)
        zoom = dpi / 72.0
        pixmap = pdf_page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        out_path = Path(out_path)
        if not out_path.is_absolute():
            out_path = Path(_BACKEND_ROOT) / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        pixmap.save(str(out_path))
    finally:
        doc.close()

    if not out_path.exists() or out_path.stat().st_size == 0:
        raise RuntimeError(f"Failed to write non-empty PNG at {out_path}")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drawing-id", type=int, required=True)
    parser.add_argument("--page", type=int, default=1, help="1-based page number")
    parser.add_argument("--out", type=Path, required=True, help="Output PNG path")
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    args = parser.parse_args()

    written = export_drawing_page_png(
        drawing_id=args.drawing_id,
        page=args.page,
        out_path=args.out,
        dpi=args.dpi,
    )
    size = written.stat().st_size
    print(f"Wrote {written} ({size} bytes, dpi={args.dpi}, page={args.page})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
