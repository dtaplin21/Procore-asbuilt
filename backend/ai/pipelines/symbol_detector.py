"""Optional YOLO symbol detection for sheet digitization (S-2).

Weights are optional: missing path / missing ultralytics → empty list so indexing
and SheetEntityGraph construction never block on symbols.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Sequence

from ai.pipelines.sheet_entity_graph import (
    DrawingViewport,
    SheetSymbol,
    assign_viewport_id,
)

logger = logging.getLogger(__name__)

SYMBOL_DETECTOR_WEIGHTS_MISSING = "symbol_detector_weights_missing"
SYMBOL_DETECTOR_RUNTIME_MISSING = "symbol_detector_runtime_missing"


def resolve_symbol_detector_weights_path(
    weights_path: Path | str | None = None,
) -> Path | None:
    """Resolve explicit path or ``SYMBOL_DETECTOR_WEIGHTS_PATH`` from settings."""
    if weights_path is not None:
        path = Path(weights_path)
        return path if path.is_file() else None

    try:
        from config import settings
    except Exception:  # noqa: BLE001 — settings optional in unit tests
        return None

    raw = getattr(settings, "symbol_detector_weights_path", None)
    if not raw:
        return None
    path = Path(str(raw))
    return path if path.is_file() else None


def _crop_offsets(
    page_w: int,
    page_h: int,
    viewport: DrawingViewport | None,
) -> tuple[int, int, int, int]:
    """Return (offset_x, offset_y, crop_w, crop_h) in page pixels."""
    if viewport is None:
        return 0, 0, page_w, page_h
    x0, y0, x1, y1 = viewport.bbox_fractional
    px0 = max(0, min(page_w - 1, int(x0 * page_w)))
    py0 = max(0, min(page_h - 1, int(y0 * page_h)))
    px1 = max(px0 + 1, min(page_w, int(math.ceil(x1 * page_w))))
    py1 = max(py0 + 1, min(page_h, int(math.ceil(y1 * page_h))))
    return px0, py0, px1 - px0, py1 - py0


def _run_yolo(
    image_bgr: object,
    *,
    weights_path: Path,
    conf_threshold: float,
) -> list[tuple[str, float, tuple[float, float, float, float]]]:
    """Run ultralytics YOLO; returns (class_name, conf, xyxy_px_in_image)."""
    try:
        from ultralytics import YOLO  # type: ignore[import-untyped]
    except ImportError:
        logger.warning(
            "%s: ultralytics not installed; returning no symbols",
            SYMBOL_DETECTOR_RUNTIME_MISSING,
        )
        return []

    model = YOLO(str(weights_path))
    results = model.predict(
        source=image_bgr,
        conf=float(conf_threshold),
        verbose=False,
    )
    if not results:
        return []

    result = results[0]
    names = getattr(result, "names", None) or getattr(model, "names", {}) or {}
    boxes = getattr(result, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return []

    detections: list[tuple[str, float, tuple[float, float, float, float]]] = []
    xyxy = boxes.xyxy
    confs = boxes.conf
    clss = boxes.cls
    for i in range(len(boxes)):
        x0, y0, x1, y1 = (float(v) for v in xyxy[i].tolist())
        conf = float(confs[i].item()) if confs is not None else float(conf_threshold)
        cls_id = int(clss[i].item()) if clss is not None else -1
        if isinstance(names, dict):
            class_name = str(names.get(cls_id, f"class_{cls_id}"))
        else:
            class_name = str(names[cls_id]) if 0 <= cls_id < len(names) else f"class_{cls_id}"
        detections.append((class_name, conf, (x0, y0, x1, y1)))
    return detections


def detect_symbols(
    rendition_png: Path | str,
    *,
    weights_path: Path | str | None,
    viewport: DrawingViewport | None = None,
    viewports: Sequence[DrawingViewport] | None = None,
    conf_threshold: float = 0.25,
) -> list[SheetSymbol]:
    """Detect symbols on a page PNG; empty when weights/runtime are unavailable.

    ``viewport`` crops inference to that region. ``viewports`` (defaulting to
    ``(viewport,)`` when set) are used with ``assign_viewport_id`` for labels.
    """
    resolved = resolve_symbol_detector_weights_path(weights_path)
    if resolved is None:
        logger.info("%s: path=%r", SYMBOL_DETECTOR_WEIGHTS_MISSING, weights_path)
        return []

    try:
        import cv2  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("%s: opencv unavailable", SYMBOL_DETECTOR_RUNTIME_MISSING)
        return []

    image = cv2.imread(str(rendition_png), cv2.IMREAD_COLOR)
    if image is None:
        return []

    page_h, page_w = image.shape[:2]
    if page_h <= 0 or page_w <= 0:
        return []

    offset_x, offset_y, crop_w, crop_h = _crop_offsets(page_w, page_h, viewport)
    if viewport is not None:
        work = image[offset_y : offset_y + crop_h, offset_x : offset_x + crop_w]
        if work.size == 0:
            return []
    else:
        work = image

    detections = _run_yolo(work, weights_path=resolved, conf_threshold=conf_threshold)
    assign_from: tuple[DrawingViewport, ...]
    if viewports is not None:
        assign_from = tuple(viewports)
    elif viewport is not None:
        assign_from = (viewport,)
    else:
        assign_from = ()

    symbols: list[SheetSymbol] = []
    for class_name, conf, (x0, y0, x1, y1) in detections:
        # Map crop-local pixels → full-page fractional.
        fx0 = (x0 + offset_x) / float(page_w)
        fy0 = (y0 + offset_y) / float(page_h)
        fx1 = (x1 + offset_x) / float(page_w)
        fy1 = (y1 + offset_y) / float(page_h)
        bbox = (
            max(0.0, min(1.0, fx0)),
            max(0.0, min(1.0, fy0)),
            max(0.0, min(1.0, fx1)),
            max(0.0, min(1.0, fy1)),
        )
        if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
            continue
        viewport_id = assign_viewport_id(bbox, assign_from) if assign_from else None
        symbols.append(
            SheetSymbol(
                symbol_class=class_name,
                bbox_fractional=bbox,
                viewport_id=viewport_id,
                confidence=conf,
                detector="yolo",
            )
        )
    return symbols
