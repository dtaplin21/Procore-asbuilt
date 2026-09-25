#!/usr/bin/env python3
"""Audit legend line rows clustered from indexed drawing text (Step 2a).

Uses ``drawing_text_elements`` in the legend band — OCR/Document AI tokens
required for line-item labels on CAD exports.

Usage (from ``backend/``)::

    ./venv/bin/python scripts/audit_legend_line_rows.py --drawing-id 1691 --project-id 688
    ./venv/bin/python scripts/audit_legend_line_rows.py --drawing-id 1691 --export legend_manifest_1691.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import cast

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))
os.chdir(_BACKEND_ROOT)

from sqlalchemy.orm import Session  # noqa: E402

from ai.pipelines.legend_line_row_builder import (  # noqa: E402
    cluster_legend_line_rows,
    legend_rows_to_manifest,
)
from database import SessionLocal  # noqa: E402
from models.drawing_text_element import DrawingTextElement  # noqa: E402
from models.models import Drawing  # noqa: E402


def _load_elements(
    session: Session,
    *,
    project_id: int,
    drawing_id: int,
    page: int | None,
) -> tuple[Drawing | None, list[DrawingTextElement]]:
    drawing = session.get(Drawing, drawing_id)
    if drawing is None:
        return None, []
    if cast(int, drawing.project_id) != project_id:
        print(
            f"Warning: drawing project_id={drawing.project_id} != {project_id}",
            file=sys.stderr,
        )
    query = session.query(DrawingTextElement).filter(
        DrawingTextElement.master_drawing_id == int(drawing_id),
    )
    if page is not None:
        query = query.filter(DrawingTextElement.page == int(page))
    rows = query.order_by(DrawingTextElement.page.asc(), DrawingTextElement.id.asc()).all()
    return drawing, rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit legend line row clustering.")
    parser.add_argument("--project-id", type=int, default=688)
    parser.add_argument("--drawing-id", type=int, default=1691)
    parser.add_argument("--page", type=int, default=1, help="1-based page (default 1)")
    parser.add_argument(
        "--export",
        type=str,
        default="",
        help="Write manifest JSON (legend rows + bboxes)",
    )
    parser.add_argument(
        "--no-column-filter",
        action="store_true",
        help="Disable dominant x-column filter (debug title-block bleed)",
    )
    args = parser.parse_args()

    session = SessionLocal()
    try:
        drawing, elements = _load_elements(
            session,
            project_id=int(args.project_id),
            drawing_id=int(args.drawing_id),
            page=int(args.page),
        )
        if drawing is None:
            print(f"Drawing {args.drawing_id} not found.")
            return 1

        rows = cluster_legend_line_rows(
            elements,
            use_dominant_text_column=not args.no_column_filter,
        )
        manifest = legend_rows_to_manifest(rows)

        name = cast(str | None, drawing.name)
        print(f"Drawing id={drawing.id} name={name!r} project_id={drawing.project_id}")
        print(f"page={args.page} indexed_tokens={len(elements)} legend_rows={len(rows)}")
        print()
        for entry in manifest:
            print(f"  [{entry['index']}] {entry['text']!r}")

        if args.export:
            out_path = Path(args.export)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "drawing_id": int(args.drawing_id),
                "project_id": int(args.project_id),
                "page": int(args.page),
                "indexed_token_count": len(elements),
                "legend_row_count": len(rows),
                "rows": manifest,
            }
            out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            print(f"\nWrote manifest: {out_path.resolve()}", file=sys.stderr)

        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
