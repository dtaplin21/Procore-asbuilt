#!/usr/bin/env python3
"""Export unlabeled symbol crops for YOLO / CVAT labeling (digitization S-1).

Usage (from ``backend/``)::

    ./venv/bin/python scripts/export_symbol_crops.py --drawing-id 1501
    ./venv/bin/python scripts/export_symbol_crops.py --drawing-id 661 --viewport-id plan
    ./venv/bin/python scripts/export_symbol_crops.py --drawing-id 1501 --mode sliding

Crops land in ``data/symbol_crops/unknown/`` with a ``manifest.csv``. Sort into
class folders per ``data/symbol_crops/README.md`` before training.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import tempfile
from pathlib import Path
from typing import Literal, Sequence, cast

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

import cv2  # noqa: E402  # type: ignore[import-untyped]
import numpy as np  # noqa: E402  # type: ignore[import-untyped]

from ai.pipelines.landmark_extractor import extract_landmarks_from_page  # noqa: E402
from ai.pipelines.viewport_scale import load_viewports  # noqa: E402
from database import SessionLocal  # noqa: E402
from scripts.export_drawing_page_png import (  # noqa: E402
    DEFAULT_DPI,
    export_drawing_page_png,
)

DEFAULT_OUT_DIR = Path(_BACKEND_ROOT) / "data" / "symbol_crops"
SYMBOL_CLASSES_V1 = (
    "ssmh",
    "ssco",
    "callout_bubble",
    "north_arrow",
    "scale_bar",
    "other",
)
UNKNOWN_DIR = "unknown"
HOLDOUT_DIR = "holdout"
MANIFEST_NAME = "manifest.csv"
ProposalMode = Literal["landmarks", "sliding"]


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _pad_bbox(
    bbox: dict[str, float],
    *,
    pad: float,
) -> tuple[float, float, float, float]:
    return (
        _clamp01(float(bbox["x0"]) - pad),
        _clamp01(float(bbox["y0"]) - pad),
        _clamp01(float(bbox["x1"]) + pad),
        _clamp01(float(bbox["y1"]) + pad),
    )


def _centroid_in_viewport(
    bbox: dict[str, float],
    viewport_bbox: tuple[float, float, float, float],
) -> bool:
    cx = (float(bbox["x0"]) + float(bbox["x1"])) / 2.0
    cy = (float(bbox["y0"]) + float(bbox["y1"])) / 2.0
    x0, y0, x1, y1 = viewport_bbox
    return x0 <= cx <= x1 and y0 <= cy <= y1


def _ensure_class_dirs(out_dir: Path) -> None:
    for name in (UNKNOWN_DIR, HOLDOUT_DIR, *SYMBOL_CLASSES_V1):
        (out_dir / name).mkdir(parents=True, exist_ok=True)


def _sliding_window_bboxes(
    *,
    window_frac: float = 0.06,
    stride_frac: float = 0.04,
    max_windows: int = 300,
    clip: tuple[float, float, float, float] | None = None,
) -> list[dict[str, float]]:
    """Dense square windows for recall-oriented unlabeled export."""
    x_min, y_min, x_max, y_max = clip if clip is not None else (0.0, 0.0, 1.0, 1.0)
    bboxes: list[dict[str, float]] = []
    y = y_min
    while y + window_frac <= y_max + 1e-9 and len(bboxes) < max_windows:
        x = x_min
        while x + window_frac <= x_max + 1e-9 and len(bboxes) < max_windows:
            bboxes.append(
                {
                    "x0": _clamp01(x),
                    "y0": _clamp01(y),
                    "x1": _clamp01(min(x + window_frac, x_max)),
                    "y1": _clamp01(min(y + window_frac, y_max)),
                }
            )
            x += stride_frac
        y += stride_frac
    return bboxes


def _proposal_bboxes(
    page_png: Path,
    *,
    page: int,
    mode: ProposalMode,
    viewport_bbox: tuple[float, float, float, float] | None,
    max_crops: int,
) -> list[dict[str, float]]:
    if mode == "sliding":
        proposals = _sliding_window_bboxes(
            max_windows=max_crops,
            clip=viewport_bbox,
        )
    else:
        landmarks = extract_landmarks_from_page(page_png, {"page": page}, page=page)
        proposals = [dict(lm.bbox_json) for lm in landmarks]
        if viewport_bbox is not None:
            proposals = [b for b in proposals if _centroid_in_viewport(b, viewport_bbox)]
        # Contours often miss sparse plan symbols — fall back to windows in viewport.
        if not proposals:
            proposals = _sliding_window_bboxes(
                max_windows=max_crops,
                clip=viewport_bbox,
            )

    return proposals[:max_crops]


def _write_crop(
    image: np.ndarray,
    bbox: tuple[float, float, float, float],
    out_path: Path,
) -> bool:
    height, width = image.shape[:2]
    x0, y0, x1, y1 = bbox
    px0 = max(0, min(width - 1, int(x0 * width)))
    py0 = max(0, min(height - 1, int(y0 * height)))
    px1 = max(px0 + 1, min(width, int(np.ceil(x1 * width))))
    py1 = max(py0 + 1, min(height, int(np.ceil(y1 * height))))
    crop = image[py0:py1, px0:px1]
    if crop.size == 0:
        return False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    return bool(cv2.imwrite(str(out_path), crop))


def _append_manifest(manifest_path: Path, rows: Sequence[dict[str, object]]) -> None:
    fieldnames = ["path", "drawing_id", "page", "x0", "y0", "x1", "y1", "viewport_id"]
    write_header = not manifest_path.exists() or manifest_path.stat().st_size == 0
    with manifest_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


def export_symbol_crops(
    *,
    drawing_id: int,
    page: int = 1,
    viewport_id: str | None = None,
    out_dir: Path = DEFAULT_OUT_DIR,
    mode: ProposalMode = "landmarks",
    dpi: int = DEFAULT_DPI,
    pad: float = 0.008,
    max_crops: int = 200,
) -> Path:
    """Rasterize a page, propose crops, write PNGs + manifest.csv. Returns manifest path."""
    out_dir = out_dir if out_dir.is_absolute() else Path(_BACKEND_ROOT) / out_dir
    _ensure_class_dirs(out_dir)
    unknown_dir = out_dir / UNKNOWN_DIR
    manifest_path = out_dir / MANIFEST_NAME

    viewport_bbox: tuple[float, float, float, float] | None = None
    if viewport_id is not None:
        db = SessionLocal()
        try:
            viewports = load_viewports(db, drawing_id, page=page)
        finally:
            db.close()
        match = next((vp for vp in viewports if vp.viewport_id == viewport_id), None)
        if match is None:
            raise SystemExit(
                f"viewport_id={viewport_id!r} not found for drawing {drawing_id} page {page}"
            )
        viewport_bbox = match.bbox_fractional

    with tempfile.TemporaryDirectory(prefix="symbol_crops_") as tmp:
        page_png = Path(tmp) / f"drawing_{drawing_id}_page{page}.png"
        export_drawing_page_png(
            drawing_id=drawing_id,
            page=page,
            out_path=page_png,
            dpi=dpi,
        )
        image = cv2.imread(str(page_png), cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError(f"Failed to read rasterized page {page_png}")

        proposals = _proposal_bboxes(
            page_png,
            page=page,
            mode=mode,
            viewport_bbox=viewport_bbox,
            max_crops=max_crops,
        )
        rows: list[dict[str, object]] = []
        for index, bbox in enumerate(proposals):
            x0, y0, x1, y1 = _pad_bbox(bbox, pad=pad)
            if x1 - x0 < 1e-4 or y1 - y0 < 1e-4:
                continue
            rel_name = (
                f"d{drawing_id}_p{page}_"
                f"{viewport_id or 'page'}_{index:04d}.png"
            )
            rel_path = f"{UNKNOWN_DIR}/{rel_name}"
            abs_path = unknown_dir / rel_name
            if not _write_crop(image, (x0, y0, x1, y1), abs_path):
                continue
            rows.append(
                {
                    "path": rel_path,
                    "drawing_id": drawing_id,
                    "page": page,
                    "x0": f"{x0:.6f}",
                    "y0": f"{y0:.6f}",
                    "x1": f"{x1:.6f}",
                    "y1": f"{y1:.6f}",
                    "viewport_id": viewport_id or "",
                }
            )

    _append_manifest(manifest_path, rows)
    print(
        f"Wrote {len(rows)} crop(s) under {unknown_dir} "
        f"(mode={mode}, viewport_id={viewport_id!r})"
    )
    print(f"Manifest: {manifest_path}")
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drawing-id", type=int, required=True)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument(
        "--viewport-id",
        type=str,
        default=None,
        help="Optional seeded viewport_id; keeps crops whose centroid is inside",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Symbol crops root (default: data/symbol_crops)",
    )
    parser.add_argument(
        "--mode",
        choices=("landmarks", "sliding"),
        default="landmarks",
        help="Proposal source: contour landmarks (default) or sliding windows",
    )
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    parser.add_argument(
        "--pad",
        type=float,
        default=0.008,
        help="Fractional pad around each proposal bbox",
    )
    parser.add_argument("--max-crops", type=int, default=200)
    args = parser.parse_args()

    export_symbol_crops(
        drawing_id=cast(int, args.drawing_id),
        page=int(args.page),
        viewport_id=args.viewport_id,
        out_dir=Path(args.out_dir),
        mode=cast(ProposalMode, args.mode),
        dpi=int(args.dpi),
        pad=float(args.pad),
        max_crops=int(args.max_crops),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
