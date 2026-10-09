#!/usr/bin/env python3
"""Export full indexed drawing payload to JSON for review."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))
os.chdir(_BACKEND_ROOT)

from sqlalchemy import inspect  # noqa: E402

from database import SessionLocal  # noqa: E402
from models.drawing_landmark import DrawingLandmark  # noqa: E402
from models.drawing_legend_grounding_hit import DrawingLegendGroundingHit  # noqa: E402
from models.drawing_region import DrawingRegion  # noqa: E402
from models.drawing_survey_point import DrawingSurveyPoint  # noqa: E402
from models.drawing_symbol import DrawingSymbol  # noqa: E402
from models.drawing_text_element import DrawingTextElement  # noqa: E402
from models.drawing_viewport import DrawingViewport  # noqa: E402
from models.models import Drawing, DrawingRendition  # noqa: E402


def _serialize(obj: Any) -> Any:
    if hasattr(obj, "isoformat"):
        return obj.isoformat() if obj is not None else None
    return obj


def _row_dict(row: Any, *, include: set[str] | None = None, exclude: set[str] | None = None) -> dict[str, Any]:
    exclude = exclude or set()
    out: dict[str, Any] = {}
    for c in inspect(row).mapper.column_attrs:
        key = c.key
        if include is not None and key not in include:
            continue
        if key in exclude:
            continue
        out[key] = _serialize(getattr(row, key))
    return out


def _gaps_for_drawing(drawing: Drawing, stats: dict[str, Any], *, survey_count: int) -> list[str]:
    gaps: list[str] = []
    if not drawing.scale_json:
        gaps.append("drawings.scale_json is null; index_stats scale_found may still be false.")
    if stats.get("scale_found") is False:
        gaps.append("No drawing-level scale promoted (check drawing_viewports for per-viewport scale).")
    if survey_count == 0 or stats.get("survey_points", survey_count) == 0:
        gaps.append("No drawing_survey_points / station controls on master — aux→master registration from index alone.")
    doc = stats.get("document_ai") if isinstance(stats.get("document_ai"), dict) else {}
    if doc.get("document_ai_cache_hit"):
        gaps.append("Document AI cache hit on this run — OCR tokens reused, not freshly billed.")
    merge = stats.get("text_merge") if isinstance(stats.get("text_merge"), dict) else {}
    dropped = merge.get("dropped_count") or stats.get("text_merge_dropped_count")
    if dropped:
        gaps.append(f"Proximity merge dropped {dropped} token(s) (see index_stats text_merge).")
    page_meta = drawing.page_meta_json if isinstance(drawing.page_meta_json, list) else []
    if page_meta and isinstance(page_meta[0], dict) and page_meta[0].get("keyplan_bbox") is None:
        gaps.append("keyplan_bbox not detected on page meta.")
    legend = stats.get("legend_index") if isinstance(stats.get("legend_index"), dict) else {}
    rows = legend.get("legend_line_rows") or []
    if len(rows) >= 4:
        b3 = (rows[2].get("label_bbox") if isinstance(rows[2], dict) else None) or {}
        b4 = (rows[3].get("label_bbox") if isinstance(rows[3], dict) else None) or {}
        if b3 and b4 and b3 == b4:
            gaps.append("Legend rows 3 and 4 share the same label_bbox (possible swatch overlap in UI).")
    return gaps


def export_drawing_index(*, drawing_id: int, out_path: Path) -> None:
    db = SessionLocal()
    try:
        drawing = db.get(Drawing, drawing_id)
        if drawing is None:
            raise SystemExit(f"drawing {drawing_id} not found")

        text_rows = (
            db.query(DrawingTextElement)
            .filter(DrawingTextElement.master_drawing_id == drawing_id)
            .order_by(DrawingTextElement.page.asc(), DrawingTextElement.id.asc())
            .all()
        )
        regions = (
            db.query(DrawingRegion)
            .filter(DrawingRegion.master_drawing_id == drawing_id)
            .order_by(DrawingRegion.id.asc())
            .all()
        )
        survey = (
            db.query(DrawingSurveyPoint)
            .filter(DrawingSurveyPoint.drawing_id == drawing_id)
            .order_by(DrawingSurveyPoint.id.asc())
            .all()
        )
        landmarks = (
            db.query(DrawingLandmark)
            .filter(DrawingLandmark.drawing_id == drawing_id)
            .order_by(DrawingLandmark.id.asc())
            .all()
        )
        viewports = (
            db.query(DrawingViewport)
            .filter(DrawingViewport.drawing_id == drawing_id)
            .order_by(DrawingViewport.page.asc(), DrawingViewport.viewport_id.asc())
            .all()
        )
        symbols = (
            db.query(DrawingSymbol)
            .filter(DrawingSymbol.drawing_id == drawing_id)
            .order_by(DrawingSymbol.id.asc())
            .all()
        )
        grounding = (
            db.query(DrawingLegendGroundingHit)
            .filter(DrawingLegendGroundingHit.master_drawing_id == drawing_id)
            .order_by(DrawingLegendGroundingHit.id.asc())
            .all()
        )
        renditions = (
            db.query(DrawingRendition)
            .filter(DrawingRendition.drawing_id == drawing_id)
            .order_by(DrawingRendition.page_number.asc())
            .all()
        )

        stats = drawing.index_stats_json if isinstance(drawing.index_stats_json, dict) else {}
        text_by_source = dict(Counter(str(r.source) for r in text_rows))

        payload: dict[str, Any] = {
            "export_meta": {
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "drawing_id": drawing_id,
                "indexed_at": _serialize(drawing.indexed_at),
                "index_status": drawing.index_status,
                "index_error": drawing.index_error,
            },
            "gaps_noticed": _gaps_for_drawing(drawing, stats, survey_count=len(survey)),
            "summary_counts": {
                "text_elements": len(text_rows),
                "regions": len(regions),
                "survey_points": len(survey),
                "landmarks": len(landmarks),
                "viewports": len(viewports),
                "symbols": len(symbols),
                "legend_grounding_hits": len(grounding),
            },
            "drawing": {
                "id": drawing.id,
                "project_id": drawing.project_id,
                "name": drawing.name,
                "index_status": drawing.index_status,
                "indexed_at": _serialize(drawing.indexed_at),
                "index_error": drawing.index_error,
                "page_count": drawing.page_count,
                "scale_json": drawing.scale_json,
                "page_meta_json": drawing.page_meta_json,
                "index_stats_json": drawing.index_stats_json,
            },
            "drawing_renditions": [
                {
                    "page_number": r.page_number,
                    "width_px": r.width_px,
                    "height_px": r.height_px,
                    "image_storage_key": r.image_storage_key,
                }
                for r in renditions
            ],
            "text_by_source": text_by_source,
            "drawing_text_elements": [
                _row_dict(
                    r,
                    include={
                        "id",
                        "page",
                        "text",
                        "text_normalized",
                        "source",
                        "bbox_json",
                        "ocr_confidence",
                        "legend_expansion",
                        "legend_codes_json",
                    },
                )
                for r in text_rows
            ],
            "drawing_regions": [_row_dict(r) for r in regions],
            "drawing_survey_points": [_row_dict(r) for r in survey],
            "drawing_landmarks": [_row_dict(r) for r in landmarks],
            "drawing_viewports": [_row_dict(r) for r in viewports],
            "drawing_symbols": [_row_dict(r) for r in symbols],
            "drawing_legend_grounding_hits": [_row_dict(r) for r in grounding],
        }

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"Wrote {out_path} ({out_path.stat().st_size} bytes)")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drawing-id", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    export_drawing_index(drawing_id=args.drawing_id, out_path=args.out)


if __name__ == "__main__":
    main()
