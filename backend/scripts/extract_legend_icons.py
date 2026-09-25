#!/usr/bin/env python3
"""Extract legend icon reference PNGs for a master drawing.

Uses indexed OCR/Document AI tokens when available; falls back to Tesseract
on the legend crop.

Usage (from ``backend/``)::

    ./venv/bin/python scripts/extract_legend_icons.py \\
        --drawing-id 1691 --project-id 688 \\
        --legend-bbox 0.70,0.02,0.98,0.135 \\
        --output-dir /tmp/legend_icons_1691

    ./venv/bin/python scripts/extract_legend_icons.py \\
        --pdf-path /path/to/Master.pdf \\
        --legend-bbox 0.70,0.02,0.98,0.135 \\
        --source tesseract
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import cast

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))
os.chdir(_BACKEND_ROOT)

from sqlalchemy.orm import Session  # noqa: E402

from ai.pipelines.legend_icon_extraction import (  # noqa: E402
    extract_legend_icons,
    extract_legend_icons_from_indexed_tokens,
    extract_legend_icons_tesseract_crop,
    parse_legend_bbox_arg,
    write_legend_icon_manifest,
)
from database import SessionLocal  # noqa: E402
from models.drawing_text_element import DrawingTextElement  # noqa: E402
from models.models import Drawing  # noqa: E402
from services.file_storage import resolve_stored_file_path  # noqa: E402


def _resolve_pdf_path(session: Session, drawing_id: int) -> Path | None:
    drawing = session.get(Drawing, int(drawing_id))
    if drawing is None:
        return None
    storage_key = cast(str | None, drawing.storage_key)
    if not storage_key or not str(storage_key).strip():
        return None
    resolved = resolve_stored_file_path(storage_key)
    if resolved is None or not resolved.is_file():
        return None
    return resolved


def _load_elements(
    session: Session,
    *,
    drawing_id: int,
    page: int,
) -> list[DrawingTextElement]:
    return (
        session.query(DrawingTextElement)
        .filter(
            DrawingTextElement.master_drawing_id == int(drawing_id),
            DrawingTextElement.page == int(page),
        )
        .order_by(DrawingTextElement.id.asc())
        .all()
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract legend icon PNG crops.")
    parser.add_argument("--project-id", type=int, default=688)
    parser.add_argument("--drawing-id", type=int, default=0)
    parser.add_argument("--pdf-path", type=str, default="")
    parser.add_argument(
        "--legend-bbox",
        type=str,
        required=True,
        help="Fractional x0,y0,x1,y1 of legend block on page",
    )
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--output-dir", type=str, default="legend_icons_out")
    parser.add_argument(
        "--source",
        choices=("auto", "indexed", "tesseract"),
        default="auto",
        help="auto=indexed rows then Tesseract crop fallback",
    )
    parser.add_argument("--zoom", type=float, default=2.0)
    args = parser.parse_args()

    legend_bbox = parse_legend_bbox_arg(args.legend_bbox)
    output_dir = Path(args.output_dir)

    session = SessionLocal()
    try:
        pdf_path: Path | None = None
        elements: list[DrawingTextElement] = []

        if args.pdf_path:
            pdf_path = Path(args.pdf_path)
        elif args.drawing_id:
            drawing = session.get(Drawing, int(args.drawing_id))
            if drawing is None:
                print(f"Drawing {args.drawing_id} not found.", file=sys.stderr)
                return 1
            if cast(int, drawing.project_id) != int(args.project_id):
                print(
                    f"Warning: drawing project_id={drawing.project_id} != {args.project_id}",
                    file=sys.stderr,
                )
            pdf_path = _resolve_pdf_path(session, int(args.drawing_id))
            elements = _load_elements(session, drawing_id=int(args.drawing_id), page=int(args.page))
        else:
            print("Provide --drawing-id or --pdf-path.", file=sys.stderr)
            return 1

        if pdf_path is None or not pdf_path.is_file():
            print("Master PDF not found on disk.", file=sys.stderr)
            return 1

        if args.source == "indexed":
            entries = extract_legend_icons_from_indexed_tokens(
                pdf_path,
                elements,
                page=int(args.page),
                legend_bbox_fractional=legend_bbox,
                output_dir=output_dir,
                zoom=float(args.zoom),
            )
        elif args.source == "tesseract":
            entries = extract_legend_icons_tesseract_crop(
                pdf_path,
                page=int(args.page),
                legend_bbox_fractional=legend_bbox,
                output_dir=output_dir,
                zoom=float(args.zoom),
            )
        else:
            entries = extract_legend_icons(
                pdf_path,
                page=int(args.page),
                legend_bbox_fractional=legend_bbox,
                output_dir=output_dir,
                elements=elements,
                prefer_indexed=True,
                zoom=float(args.zoom),
            )

        manifest_path = write_legend_icon_manifest(entries, output_dir)
        print(f"legend_rows={len(entries)} output_dir={output_dir.resolve()}")
        for entry in entries:
            print(f"  [{entry.row_id}] {entry.label_text!r} ({entry.source}) -> {entry.icon_crop_path}")
        print(f"manifest: {manifest_path.resolve()}", file=sys.stderr)
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
