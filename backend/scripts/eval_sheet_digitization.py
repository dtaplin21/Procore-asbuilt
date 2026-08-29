#!/usr/bin/env python3
"""Print sheet-digitization entity counts for a drawing (PR-E E-1).

Usage (from ``backend/``)::

    ./venv/bin/python scripts/eval_sheet_digitization.py --drawing-id 1501
    ./venv/bin/python scripts/eval_sheet_digitization.py --drawing-id 1501 --page 1
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, cast

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from database import SessionLocal  # noqa: E402
from models.drawing_symbol import DrawingSymbol  # noqa: E402
from models.drawing_viewport import DrawingViewport  # noqa: E402
from models.models import Drawing  # noqa: E402
from services.sheet_digitization import SHEET_ENTITY_GRAPH_KEY  # noqa: E402


def _graph_counts(page_graph: dict[str, Any]) -> dict[str, int]:
    return {
        "viewports": len(page_graph.get("viewports") or []),
        "labels": len(page_graph.get("labels") or []),
        "symbols": len(page_graph.get("symbols") or []),
        "lines": len(page_graph.get("lines") or []),
        "associations": len(page_graph.get("associations") or []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--drawing-id",
        type=int,
        required=True,
        help="Drawing id to inspect (e.g. 1501 for aux C4.20)",
    )
    parser.add_argument(
        "--page",
        type=int,
        default=None,
        help="Optional page filter (default: all pages with a graph)",
    )
    args = parser.parse_args()

    session = SessionLocal()
    try:
        drawing = session.get(Drawing, int(args.drawing_id))
        if drawing is None:
            print(f"Drawing {args.drawing_id} not found", file=sys.stderr)
            return 1

        viewport_q = session.query(DrawingViewport).filter(
            DrawingViewport.drawing_id == int(args.drawing_id)
        )
        symbol_q = session.query(DrawingSymbol).filter(
            DrawingSymbol.drawing_id == int(args.drawing_id)
        )
        if args.page is not None:
            viewport_q = viewport_q.filter(DrawingViewport.page == int(args.page))
            symbol_q = symbol_q.filter(DrawingSymbol.page == int(args.page))

        viewports = viewport_q.order_by(DrawingViewport.page, DrawingViewport.viewport_id).all()
        symbols = symbol_q.all()

        print(f"drawing_id={drawing.id} name={drawing.name!r}")
        print(f"db_viewports={len(viewports)} db_symbols={len(symbols)}")
        for row in viewports:
            scale = cast(dict[str, Any] | None, row.scale_json) or {}
            rfppi = scale.get("real_feet_per_paper_inch")
            print(
                f"  viewport page={row.page} id={row.viewport_id!r} "
                f"kind={row.kind} rfppi={rfppi} source={row.source}"
            )

        stats = cast(dict[str, Any] | None, drawing.index_stats_json)
        graphs = stats.get(SHEET_ENTITY_GRAPH_KEY) if isinstance(stats, dict) else None
        if not isinstance(graphs, dict) or not graphs:
            print("sheetEntityGraph: (none)")
            return 0

        pages = sorted(graphs.keys(), key=lambda p: int(p) if str(p).isdigit() else str(p))
        for page_key in pages:
            if args.page is not None and str(args.page) != str(page_key):
                continue
            page_graph = graphs[page_key]
            if not isinstance(page_graph, dict):
                continue
            counts = _graph_counts(page_graph)
            print(
                f"sheetEntityGraph page={page_key}: "
                f"viewports={counts['viewports']} labels={counts['labels']} "
                f"symbols={counts['symbols']} lines={counts['lines']} "
                f"associations={counts['associations']}"
            )
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
