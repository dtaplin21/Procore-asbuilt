#!/usr/bin/env python3
"""Audit PDF vector linework density and line-source gate for a stored drawing.

Usage (from ``backend/``)::

    ./venv/bin/python scripts/audit_pdf_vector_lines.py --drawing-id 1691
    ./venv/bin/python scripts/audit_pdf_vector_lines.py --pdf /path/to/Master.pdf
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))
os.chdir(_BACKEND_ROOT)

import fitz  # noqa: E402

from ai.pipelines.pdf_line_source_gate import (  # noqa: E402
    classify_pdf_line_source,
)
from database import SessionLocal  # noqa: E402
from models.models import Drawing  # noqa: E402
from services.file_storage import resolve_stored_file_path  # noqa: E402


def _stroke_width_histogram(
    pdf_path: Path,
    *,
    page: int = 1,
) -> dict[str, Any]:
    doc = fitz.open(str(pdf_path))
    try:
        page_obj = doc.load_page(page - 1)
        drawings = page_obj.get_drawings()
    finally:
        doc.close()

    widths: Counter[float] = Counter()
    segment_counts: list[int] = []
    for path in drawings:
        if path.get("type") != "s":
            continue
        items = path.get("items") or []
        line_items = [item for item in items if item and item[0] == "l"]
        if not line_items:
            continue
        width = round(float(path.get("width") or 0.0), 3)
        widths[width] += 1
        segment_counts.append(len(line_items))

    multi_segment = sum(1 for n in segment_counts if n >= 8)
    return {
        "stroked_paths_with_lines": len(segment_counts),
        "multi_segment_paths_ge_8": multi_segment,
        "top_stroke_widths": widths.most_common(10),
        "max_segments_in_one_path": max(segment_counts) if segment_counts else 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit PDF vector line content")
    parser.add_argument("--drawing-id", type=int, default=None)
    parser.add_argument("--pdf", type=str, default=None)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument(
        "--histogram-width",
        action="store_true",
        help="Print stroke-width histogram and multi-segment path stats",
    )
    args = parser.parse_args()

    pdf_path: Path | None = None
    if args.pdf:
        pdf_path = Path(args.pdf).expanduser().resolve()
    elif args.drawing_id is not None:
        session = SessionLocal()
        try:
            drawing = session.get(Drawing, int(args.drawing_id))
            if drawing is None:
                print(f"Drawing {args.drawing_id} not found", file=sys.stderr)
                sys.exit(1)
            storage_key = str(drawing.storage_key or "")
            if not storage_key.strip():
                print(f"Drawing {args.drawing_id} has no storage_key", file=sys.stderr)
                sys.exit(1)
            pdf_path = resolve_stored_file_path(storage_key)
        finally:
            session.close()
    else:
        parser.error("Provide --drawing-id or --pdf")

    if pdf_path is None or not pdf_path.is_file():
        print(f"PDF not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    source, stats = classify_pdf_line_source(pdf_path, page=int(args.page))
    payload: dict[str, Any] = {
        "pdf": str(pdf_path),
        "page": int(args.page),
        "pdf_line_source": source.value,
        "stats": {
            "path_count": stats.path_count,
            "line_op_count": stats.line_op_count,
            "stroked_path_count": stats.stroked_path_count,
        },
    }
    if args.histogram_width:
        payload["histogram"] = _stroke_width_histogram(pdf_path, page=int(args.page))

    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
