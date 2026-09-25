#!/usr/bin/env python3
"""Audit indexed text tokens on a drawing (OCR / PDF text layer).

Prints index summary, source mix, optional bbox coverage, and every
``drawing_text_elements`` row (position + text).

Usage (from ``backend/``)::

    ./venv/bin/python scripts/audit_drawing_index_coverage.py --drawing-id 661
    ./venv/bin/python scripts/audit_drawing_index_coverage.py --drawing-id 661 --export tokens_661.tsv
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, cast

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))
os.chdir(_BACKEND_ROOT)

from sqlalchemy.orm import Session  # noqa: E402

from database import SessionLocal  # noqa: E402
from models.drawing_text_element import DrawingTextElement  # noqa: E402
from models.models import Drawing  # noqa: E402


def _bbox_area(bbox: dict[str, Any]) -> float:
    x0 = float(bbox.get("x0", 0))
    y0 = float(bbox.get("y0", 0))
    x1 = float(bbox.get("x1", 0))
    y1 = float(bbox.get("y1", 0))
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def _centroid(bbox: dict[str, Any]) -> tuple[float, float]:
    x0 = float(bbox.get("x0", 0))
    y0 = float(bbox.get("y0", 0))
    x1 = float(bbox.get("x1", 0))
    y1 = float(bbox.get("y1", 0))
    return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)


def _grid_coverage(rows: list[DrawingTextElement], *, grid: int = 50) -> float:
    """Fraction of normalized page cells (page 1) touched by at least one token bbox."""
    if not rows:
        return 0.0
    cells: set[tuple[int, int]] = set()
    for row in rows:
        if cast(int, row.page) != 1:
            continue
        bbox = row.bbox_json if isinstance(row.bbox_json, dict) else {}
        x0 = float(bbox.get("x0", 0))
        y0 = float(bbox.get("y0", 0))
        x1 = float(bbox.get("x1", 0))
        y1 = float(bbox.get("y1", 0))
        gi0 = max(0, min(grid - 1, int(x0 * grid)))
        gi1 = max(0, min(grid - 1, int(x1 * grid)))
        gj0 = max(0, min(grid - 1, int(y0 * grid)))
        gj1 = max(0, min(grid - 1, int(y1 * grid)))
        for i in range(gi0, gi1 + 1):
            for j in range(gj0, gj1 + 1):
                cells.add((i, j))
    return len(cells) / float(grid * grid)


def audit_drawing(
    session: Session,
    *,
    project_id: int,
    drawing_id: int,
) -> tuple[Drawing | None, list[DrawingTextElement]]:
    drawing = session.get(Drawing, drawing_id)
    if drawing is None:
        return None, []
    if cast(int, drawing.project_id) != project_id:
        print(
            f"Warning: drawing {drawing_id} project_id={drawing.project_id} "
            f"!= requested project_id={project_id}",
            file=sys.stderr,
        )
    rows = (
        session.query(DrawingTextElement)
        .filter(DrawingTextElement.master_drawing_id == int(drawing_id))
        .order_by(
            DrawingTextElement.page.asc(),
            DrawingTextElement.id.asc(),
        )
        .all()
    )
    return drawing, rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", type=int, default=2)
    parser.add_argument("--drawing-id", type=int, default=661)
    parser.add_argument(
        "--export",
        type=str,
        default="",
        help="Write all tokens as TSV (page, cx, cy, source, confidence, text)",
    )
    parser.add_argument(
        "--json-export",
        type=str,
        default="",
        help="Write all tokens as JSON array",
    )
    parser.add_argument(
        "--checklist",
        action="store_true",
        help="Run Phase 5 keyword checklist (see compare_index_sources.py)",
    )
    parser.add_argument(
        "--gutter-x-max",
        type=float,
        default=None,
        help="With --checklist: only tokens with centroid_x <= this (0-1)",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        drawing, rows = audit_drawing(
            db,
            project_id=int(args.project_id),
            drawing_id=int(args.drawing_id),
        )
        if drawing is None:
            print(f"Drawing {args.drawing_id} not found.")
            return 1

        name = cast(str | None, drawing.name)
        index_status = cast(str, drawing.index_status or "unknown")
        stats = drawing.index_stats_json if isinstance(drawing.index_stats_json, dict) else {}
        page_meta = drawing.page_meta_json if isinstance(drawing.page_meta_json, list) else []

        print(f"Drawing id={drawing.id} name={name!r} project_id={drawing.project_id}")
        print(f"index_status={index_status} source={drawing.source!r}")
        print(f"index_stats_json={json.dumps(stats, indent=2)}")
        print(f"pages_in_page_meta={len(page_meta)}")

        by_page: dict[int, int] = {}
        by_source: dict[str, int] = {}
        for row in rows:
            page_num = cast(int, row.page)
            by_page[page_num] = by_page.get(page_num, 0) + 1
            src = str(row.source)
            by_source[src] = by_source.get(src, 0) + 1

        print(f"\nTotal text_elements={len(rows)}")
        print(f"By page: {dict(sorted(by_page.items()))}")
        print(f"By source: {by_source}")

        page1 = [r for r in rows if cast(int, r.page) == 1]
        sum_bbox = sum(
            _bbox_area(cast(dict[str, Any], r.bbox_json))
            for r in page1
            if isinstance(r.bbox_json, dict)
        )
        grid_cov = _grid_coverage(rows)
        print(
            f"Page 1 sum of bbox areas (overlaps double-counted): {sum_bbox:.4f} "
            f"(max 1.0 if one full page)"
        )
        print(f"Page 1 grid coverage (50x50 cells with any token): {grid_cov * 100:.1f}%")

        if args.checklist:
            from services.drawing_index_validation import (
                IndexToken,
                default_validation_keywords,
                keyword_hits,
            )

            index_tokens = [
                IndexToken(
                    page=cast(int, row.page),
                    centroid_x=_centroid(
                        cast(dict[str, Any], row.bbox_json)
                        if isinstance(row.bbox_json, dict)
                        else {}
                    )[0],
                    centroid_y=_centroid(
                        cast(dict[str, Any], row.bbox_json)
                        if isinstance(row.bbox_json, dict)
                        else {}
                    )[1],
                    source=str(row.source),
                    text=str(row.text),
                    ocr_confidence=float(cast(float, row.ocr_confidence)),
                )
                for row in rows
            ]
            hits = keyword_hits(
                index_tokens,
                default_validation_keywords(),
                gutter_x_max=args.gutter_x_max,
                page=1,
            )
            print("\n--- Phase 5 keyword checklist (page 1) ---")
            for keyword in default_validation_keywords():
                matched = hits.get(keyword, [])
                status = "OK" if matched else "MISSING"
                print(f"  [{status}] {keyword}: {len(matched)}")

        print("\n--- ALL INDEXED TEXT TOKENS (page, cx, cy, source, conf, text) ---\n")
        lines_out: list[str] = []
        json_out: list[dict[str, Any]] = []

        for row in rows:
            bbox = row.bbox_json if isinstance(row.bbox_json, dict) else {}
            cx, cy = _centroid(bbox)
            text = str(row.text)
            src = str(row.source)
            conf = float(cast(float, row.ocr_confidence))
            page = cast(int, row.page)
            line = f"{page}\t{cx:.6f}\t{cy:.6f}\t{src}\t{conf:.3f}\t{text}"
            print(line)
            lines_out.append(line)
            json_out.append(
                {
                    "id": cast(int, row.id),
                    "page": page,
                    "centroid_x": cx,
                    "centroid_y": cy,
                    "bbox_json": bbox,
                    "source": src,
                    "ocr_confidence": conf,
                    "text": text,
                    "text_normalized": str(row.text_normalized),
                }
            )

        if args.export:
            out_path = Path(args.export)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            header = "page\tcentroid_x\tcentroid_y\tsource\tocr_confidence\ttext"
            out_path.write_text(header + "\n" + "\n".join(lines_out) + "\n", encoding="utf-8")
            print(f"\nWrote TSV: {out_path.resolve()}", file=sys.stderr)

        if args.json_export:
            out_path = Path(args.json_export)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(json_out, indent=2), encoding="utf-8")
            print(f"Wrote JSON: {out_path.resolve()}", file=sys.stderr)

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
