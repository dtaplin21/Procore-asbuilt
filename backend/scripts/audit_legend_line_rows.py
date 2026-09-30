#!/usr/bin/env python3
"""Audit legend line rows clustered from indexed drawing text (Step 2a).

Uses ``drawing_text_elements`` (Document AI / native / gutter OCR) with
``DRAWING_INDEX_LEGEND_RECT`` or ``--legend-rect`` — not auto-region labels.

Usage (from ``backend/``)::

    ./venv/bin/python scripts/audit_legend_line_rows.py --drawing-id 1722 --project-id 1348
    ./venv/bin/python scripts/audit_legend_line_rows.py --drawing-id 1722 --legend-rect 0.70,0.02,0.98,0.135 --export Notes/legend-rows.json
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

from ai.pipelines.legend_line_row_builder import legend_rows_to_manifest  # noqa: E402
from config import settings  # noqa: E402
from database import SessionLocal  # noqa: E402
from models.models import Drawing  # noqa: E402
from services.legend_index_helpers import (  # noqa: E402
    cluster_legend_rows_for_drawing,
    parse_fractional_rect,
    resolved_legend_rect,
    text_elements_for_legend_clustering,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit legend line row clustering.")
    parser.add_argument("--project-id", type=int, default=688)
    parser.add_argument("--drawing-id", type=int, default=1691)
    parser.add_argument("--page", type=int, default=1, help="1-based page (default 1)")
    parser.add_argument(
        "--legend-rect",
        type=str,
        default="",
        help="Fractional x0,y0,x1,y1 (default: DRAWING_INDEX_LEGEND_RECT from .env)",
    )
    parser.add_argument(
        "--export",
        type=str,
        default="",
        help="Write manifest JSON (legend rows + bboxes)",
    )
    args = parser.parse_args()

    legend_rect = parse_fractional_rect(args.legend_rect.strip()) if args.legend_rect.strip() else resolved_legend_rect()

    session = SessionLocal()
    try:
        drawing = session.get(Drawing, int(args.drawing_id))
        if drawing is None:
            print(f"Drawing {args.drawing_id} not found.")
            return 1
        if cast(int, drawing.project_id) != int(args.project_id):
            print(
                f"Warning: drawing project_id={drawing.project_id} != {args.project_id}",
                file=sys.stderr,
            )

        elements = text_elements_for_legend_clustering(
            session,
            int(args.drawing_id),
            page=int(args.page),
        )
        rows = cluster_legend_rows_for_drawing(
            session,
            int(args.drawing_id),
            page=int(args.page),
            legend_rect=legend_rect,
        )
        manifest = legend_rows_to_manifest(rows)

        name = cast(str | None, drawing.name)
        sources = (settings.drawing_index_legend_cluster_sources or "native_pdf,document_ai").strip()
        print(f"Drawing id={drawing.id} name={name!r} project_id={drawing.project_id}")
        print(f"page={args.page} cluster_sources={sources!r} legend_rect={legend_rect}")
        print(f"indexed_tokens_for_cluster={len(elements)} legend_rows={len(rows)}")
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
                "legend_rect": list(legend_rect) if legend_rect else None,
                "cluster_sources": sources,
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
