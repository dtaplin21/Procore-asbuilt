#!/usr/bin/env python3
"""Re-run viewport scale promotion for one drawing (no full OCR re-index).

Clears stale ``viewport_promotion`` scale when ``source_viewport_id`` no longer
exists on seeded viewports, then promotes from current viewports / sheet graph.

Usage (from ``backend/``)::

    ./venv/bin/python scripts/fix_drawing_scale_promotion.py --drawing-id 1722
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))
os.chdir(_BACKEND_ROOT)

from database import SessionLocal  # noqa: E402
from models.models import Drawing  # noqa: E402
from services.drawing_scale_promotion import apply_viewport_scale_promotion  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drawing-id", type=int, required=True)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        drawing = db.get(Drawing, args.drawing_id)
        if drawing is None:
            raise SystemExit(f"drawing {args.drawing_id} not found")

        before = drawing.scale_json
        result = apply_viewport_scale_promotion(db, drawing)
        db.commit()

        stats = drawing.index_stats_json if isinstance(drawing.index_stats_json, dict) else {}
        print(
            json.dumps(
                {
                    "drawing_id": args.drawing_id,
                    "promoted": result.promoted,
                    "scale_found": result.scale_found,
                    "ambiguous": result.ambiguous,
                    "reason": result.reason,
                    "source_viewport_id": result.source_viewport_id,
                    "scale_before": before,
                    "scale_after": drawing.scale_json,
                    "index_stats_scale_found": stats.get("scale_found"),
                    "index_stats_scale_source": stats.get("scale_source"),
                },
                indent=2,
                default=str,
            )
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
