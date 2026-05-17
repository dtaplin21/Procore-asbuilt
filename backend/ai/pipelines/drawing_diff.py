"""
Drawing diff pipeline.

Compares master and sub drawing for an alignment, creates DrawingDiff records,
and optionally creates Findings when severity exceeds threshold.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from sqlalchemy.orm import Session
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, cast

if TYPE_CHECKING:
    import numpy as np
    from numpy import ndarray

from errors import DrawingDiffPipelineError
from models.models import Drawing, DrawingAlignment, DrawingDiff
from services.file_storage import get_file_path
from services.storage import StorageService

logger = logging.getLogger(__name__)

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment, misc]

try:
    import cv2  # type: ignore
except ImportError:
    cv2 = None  # type: ignore[assignment]

# Raster diff (P1.4): blur, Otsu, morphology, contours — tune here.
_DIFF_GAUSSIAN_BLUR_KSIZE = (5, 5)
_DIFF_MORPH_KERNEL_SIZE = (5, 5)
_DIFF_MIN_REGION_AREA_PX = 400
_DIFF_MAX_REGIONS = 50
# Drop boxes that cover almost the whole page (alignment/noise / global illumination).
_DIFF_FULL_PAGE_AREA_FRAC = 0.88
_DIFF_FULL_PAGE_MIN_SIDE_FRAC = 0.92


def _bbox_dict_normalized_01(
    x: int,
    y: int,
    w: int,
    h: int,
    *,
    raster_w: int,
    raster_h: int,
) -> Dict[str, float]:
    """
    Persist diff geometry as ``bbox`` only (``x``, ``y``, ``width``, ``height``),
    normalized 0–1 vs raster width/height — same contract as
    ``resolveOverlayRegion`` → ``normalizeRect`` on the client.

    Does **not** emit ``points``, ``shapeType``, or ``rect`` (polygon path must
    stay unused for auto-detected regions).
    """
    if raster_w <= 0 or raster_h <= 0:
        return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}
    xf = float(x) / float(raster_w)
    yf = float(y) / float(raster_h)
    wf = float(w) / float(raster_w)
    hf = float(h) / float(raster_h)
    xf = max(0.0, min(1.0, xf))
    yf = max(0.0, min(1.0, yf))
    wf = max(0.0, min(1.0 - xf, wf))
    hf = max(0.0, min(1.0 - yf, hf))
    return {"x": xf, "y": yf, "width": wf, "height": hf}


def _coerce_transform_dict(raw: Any) -> Optional[Dict[str, Any]]:
    if raw is None:
        return None
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        try:
            raw = json.loads(s)
        except (json.JSONDecodeError, TypeError):
            return None
    if not isinstance(raw, dict):
        return None
    return raw


def _parse_transform_to_homography(transform: Any) -> Optional[ndarray]:
    """
    Parse persisted ``alignment.transform`` into a 3×3 row-major ``H`` (float64),
    mapping sub raster pixels → master raster pixels.

    Accepts **affine** (6 floats) or **homography** (9 floats). Returns ``None``
    if NumPy is unavailable, input is not a dict (after JSON coercion), or matrix
    length is invalid.

    JSON strings are handled via :func:`_coerce_transform_dict` (same as ORM JSON
    sometimes round-tripping as a string).
    """
    if np is None:
        return None
    td = _coerce_transform_dict(transform)
    if not td:
        return None
    m = td.get("matrix") or td.get("homography")
    if m is None or isinstance(m, dict):
        return None
    if not isinstance(m, (list, tuple)):
        return None
    try:
        coeffs = [float(x) for x in m]
    except (TypeError, ValueError):
        return None
    if len(coeffs) == 6:
        a, b, tx, c, d, ty = coeffs
        return np.array(
            [[a, b, tx], [c, d, ty], [0.0, 0.0, 1.0]],
            dtype=np.float64,
        )
    if len(coeffs) >= 9:
        return np.array(coeffs[:9], dtype=np.float64).reshape(3, 3)
    return None


def _alignment_page_from_transform(transform_raw: Any) -> int:
    """``alignment.transform[''page'']`` with fallback ``1`` (alignment / raster plan)."""
    td = _coerce_transform_dict(transform_raw)
    if not td:
        return 1
    try:
        p = td.get("page", 1)
        return int(p) if p is not None else 1
    except (TypeError, ValueError):
        return 1


def _alignment_page_from_alignment(alignment: DrawingAlignment) -> int:
    return _alignment_page_from_transform(getattr(alignment, "transform", None))


def _render_drawing_to_array(*, db: Session, drawing: Drawing, page: int) -> Any | None:
    """
    Lazy-load one grayscale page via :meth:`DrawingComparisonService.render_drawing_page`
    (same DPI/path as ORB alignment). Returns a numpy uint8 ``H×W`` array or ``None``.

    Imports :class:`DrawingComparisonService` inside the function to avoid circular
    imports with :mod:`services.drawing_comparison`.
    """
    from services.drawing_comparison import DrawingComparisonService

    svc = DrawingComparisonService(db)
    return svc.render_drawing_page(drawing, page)


# ---------------------------------------------------------------------------
# Step 1 — Resolve Files
# ---------------------------------------------------------------------------


def _resolve_file_paths(
    db: Session,
    alignment: DrawingAlignment,
) -> Tuple[Optional[Path], Optional[Path], Optional[str]]:
    """
    Get master and sub drawing file paths via storage_key.
    Returns (master_path, sub_path, error_message).
    """
    master_id = cast(int, alignment.master_drawing_id)
    sub_id = cast(int, alignment.sub_drawing_id)

    master = db.query(Drawing).filter(Drawing.id == master_id).first()
    sub = db.query(Drawing).filter(Drawing.id == sub_id).first()

    if master is None or sub is None:
        return None, None, "Master or sub drawing not found"

    master_key = getattr(master, "storage_key", None)
    sub_key = getattr(sub, "storage_key", None)

    if not master_key or not sub_key:
        return None, None, "Drawing has no storage_key (e.g. Procore URL)"

    try:
        master_path = get_file_path(master_key)
        sub_path = get_file_path(sub_key)
    except Exception as e:
        return None, None, f"Failed to resolve file paths: {e}"

    if not master_path.exists() or not sub_path.exists():
        return None, None, "File not found on disk"

    return master_path, sub_path, None


# ---------------------------------------------------------------------------
# Step 2 — Warp Sub Drawing (sub raster → master canvas)
# ---------------------------------------------------------------------------


def _warp_sub_raster_into_master(
    sub_gray: Any,
    master_gray: Any,
    transform_raw: Any,
) -> Any | None:
    """
    Warp sub page raster into master pixel frame using stored homography/affine.

    Output size is **master width × height**; ``BORDER_REPLICATE`` reduces fake
    edge frames vs constant padding.
    """
    if cv2 is None or np is None:
        logger.warning(
            "drawing_diff_warp_skipped",
            extra={"reason": "opencv_or_numpy_unavailable"},
        )
        return None
    if sub_gray is None or master_gray is None:
        return None

    H = _parse_transform_to_homography(transform_raw)
    if H is None:
        logger.warning("drawing_diff_warp_skipped", extra={"reason": "invalid_homography"})
        return None

    mh, mw = int(master_gray.shape[0]), int(master_gray.shape[1])
    try:
        warped = cv2.warpPerspective(
            sub_gray,
            H,
            (mw, mh),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
    except Exception as e:
        logger.warning("drawing_diff_warp_failed", extra={"reason": str(e)})
        return None
    return warped


def _diff_ensure_gray_u8(img: Any) -> Any | None:
    """Ensure ``H×W`` uint8 grayscale for pipeline steps."""
    if img is None or np is None:
        return None
    if not hasattr(img, "shape") or len(getattr(img, "shape", ())) < 2:
        return None
    if getattr(img, "dtype", None) != np.uint8:
        try:
            img = np.clip(img, 0, 255).astype(np.uint8)
        except Exception:
            return None
    if img.ndim == 2:
        return img
    if img.ndim == 3 and img.shape[2] >= 3 and cv2 is not None:
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if img.ndim == 3 and img.shape[2] == 1:
        return img[:, :, 0]
    return None


def _diff_aabb_intersect(
    a: Tuple[int, int, int, int],
    b: Tuple[int, int, int, int],
) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (
        ax + aw <= bx
        or bx + bw <= ax
        or ay + ah <= by
        or by + bh <= ay
    )


def _diff_union_rect(
    a: Tuple[int, int, int, int],
    b: Tuple[int, int, int, int],
) -> Tuple[int, int, int, int]:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1 = min(ax, bx)
    y1 = min(ay, by)
    x2 = max(ax + aw, bx + bw)
    y2 = max(ay + ah, by + bh)
    return (x1, y1, x2 - x1, y2 - y1)


def _diff_merge_axis_aligned_boxes(
    boxes: List[Tuple[int, int, int, int]],
) -> List[Tuple[int, int, int, int]]:
    """Merge overlapping axis-aligned bounding boxes (union) until stable."""
    rects = list(boxes)
    if len(rects) < 2:
        return rects
    while True:
        merged_once = False
        i = 0
        while i < len(rects):
            j = i + 1
            while j < len(rects):
                if _diff_aabb_intersect(rects[i], rects[j]):
                    rects[i] = _diff_union_rect(rects[i], rects[j])
                    rects.pop(j)
                    merged_once = True
                else:
                    j += 1
            i += 1
        if not merged_once:
            break
    return rects


def _diff_score_severity(
    *,
    num_regions: int,
    total_area_frac: float,
) -> str:
    """Map region count + covered area to severity label."""
    if num_regions >= 25 or total_area_frac >= 0.12:
        return "critical"
    if num_regions >= 12 or total_area_frac >= 0.06:
        return "high"
    if num_regions >= 4 or total_area_frac >= 0.02:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Step 3 & 4 — Generate Diff Regions, Score Severity
# ---------------------------------------------------------------------------


def _generate_and_score_diff(
    master_gray: Any,
    warped_sub: Any | None,
    *,
    page: int,
) -> List[Dict[str, Any]]:
    """
    Produce normalized diff geometry and compute severity.
    Returns list of ``{ summary, severity, diff_regions, change_details, semantic_summary? }``.

    Each diff region matches :class:`models.schemas.DrawingDiffRegion`:
    ``page``, **only** normalized ``bbox`` ``{x, y, width, height}`` in 0–1
    (no ``points`` / polygon payloads — the viewer overlay stack resolves rects
    via ``bbox``). Optional ``change_type``, ``note``, ``confidence``.

    **P2.4:** After regions exist, runs **one** sheet-level semantic pass (full master
    vs warped sub) via :func:`ai.pipelines.diff_semantics.compare_cropped_regions_semantics`
    and stores the result under ``semantic_summary`` (plus ``scope``, ``page``,
    ``region_count``). Failures are logged; ``semantic_summary`` may be omitted.
    """
    if cv2 is None or np is None:
        logger.warning(
            "drawing_diff_detect_skipped",
            extra={"reason": "opencv_or_numpy_unavailable", "page": page},
        )
        return []

    m = _diff_ensure_gray_u8(master_gray)
    w = _diff_ensure_gray_u8(warped_sub)
    if m is None or w is None:
        return []
    if m.shape != w.shape:
        logger.warning(
            "drawing_diff_detect_skipped",
            extra={"reason": "shape_mismatch", "page": page, "master": m.shape, "warped": w.shape},
        )
        return []

    mh, mw = int(m.shape[0]), int(m.shape[1])
    page_area = float(max(mw * mh, 1))

    m_blur = cv2.GaussianBlur(m, _DIFF_GAUSSIAN_BLUR_KSIZE, 0)
    w_blur = cv2.GaussianBlur(w, _DIFF_GAUSSIAN_BLUR_KSIZE, 0)
    diff = cv2.absdiff(m_blur, w_blur)

    _, th = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    k = max(3, int(_DIFF_MORPH_KERNEL_SIZE[0]) | 1)
    kernel = np.ones((k, k), dtype=np.uint8)
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, kernel)
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes: List[Tuple[int, int, int, int]] = []
    for c in contours:
        x, y, bw, bh = cv2.boundingRect(c)
        if bw * bh < _DIFF_MIN_REGION_AREA_PX:
            continue
        af = (bw * bh) / page_area
        wide = bw / float(mw) if mw else 0.0
        high = bh / float(mh) if mh else 0.0
        if af >= _DIFF_FULL_PAGE_AREA_FRAC or (
            wide >= _DIFF_FULL_PAGE_MIN_SIDE_FRAC and high >= _DIFF_FULL_PAGE_MIN_SIDE_FRAC
        ):
            continue
        boxes.append((x, y, bw, bh))

    merged = _diff_merge_axis_aligned_boxes(boxes)
    merged.sort(key=lambda b: b[2] * b[3], reverse=True)
    merged = merged[:_DIFF_MAX_REGIONS]

    if not merged:
        return []

    total_area_frac = sum((bx[2] * bx[3]) / page_area for bx in merged)
    severity = _diff_score_severity(num_regions=len(merged), total_area_frac=total_area_frac)

    diff_regions: List[Dict[str, Any]] = []
    for idx, (x, y, bw, bh) in enumerate(merged):
        diff_regions.append(
            {
                "page": page,
                "bbox": _bbox_dict_normalized_01(
                    x, y, bw, bh, raster_w=mw, raster_h=mh
                ),
                "change_type": "changed_region",
                "note": f"Detected change {idx + 1} of {len(merged)}",
                "confidence": min(0.95, 0.55 + 0.08 * min(len(merged), 5)),
            }
        )

    summary = (
        f"Detected {len(merged)} changed region(s) on page {page} "
        f"({severity} severity, ~{total_area_frac * 100:.1f}% of page area)."
    )

    change_details = {
        "source": "raster_pipeline",
        "page": page,
        "region_count": len(merged),
        "total_area_frac": round(total_area_frac, 6),
        "severity_hint": severity,
    }

    semantic_summary: Dict[str, Any] | None = None
    try:
        from ai.pipelines.diff_semantics import compare_cropped_regions_semantics

        sheet_delta = compare_cropped_regions_semantics(m, w)
        semantic_summary = {
            "scope": "sheet",
            "page": page,
            "region_count": len(merged),
        }
        semantic_summary.update(sheet_delta)
    except Exception as e:
        logger.warning(
            "drawing_diff_semantic_sheet_failed",
            extra={"page": page, "reason": str(e)},
        )

    payload: Dict[str, Any] = {
        "summary": summary,
        "severity": severity,
        "diff_regions": diff_regions,
        "change_details": change_details,
    }
    if semantic_summary is not None:
        payload["semantic_summary"] = semantic_summary

    return [payload]


# ---------------------------------------------------------------------------
# Step 5 & 6 — Persist Diff, Create Finding
# ---------------------------------------------------------------------------


def _persist_diff_and_finding(
    storage: StorageService,
    alignment_id: int,
    item: Dict[str, Any],
    severity_threshold: str,
) -> Optional[DrawingDiff]:
    """Create DrawingDiff, optionally create Finding if severity >= threshold.

    Callers should pass items with non-empty ``summary`` and ``diff_regions``;
    otherwise this returns ``None`` without writing.
    """
    summary = item.get("summary", "")
    severity = item.get("severity", "low")
    diff_regions = item.get("diff_regions", [])

    if not summary or not diff_regions:
        return None

    diff = storage.create_drawing_diff(
        alignment_id,
        summary=summary,
        severity=severity,
        diff_regions=diff_regions,
        change_details=item.get("change_details"),
        semantic_summary=item.get("semantic_summary"),
    )

    storage.create_finding_for_diff(
        diff,
        severity_threshold=severity_threshold,
    )

    return diff


# ---------------------------------------------------------------------------
# Step 7 — Main Pipeline with Logging & Error Handling
# ---------------------------------------------------------------------------


def run_drawing_diff(
    db: Session,
    alignment: DrawingAlignment,
    *,
    severity_threshold: str = "high",
) -> List[DrawingDiff]:
    """
    Run diff analysis for an alignment. Ensures failures do not crash API;
    alignment status and error_message are updated on failure.

    Flow: :func:`_resolve_file_paths` gates first. Render failure marks the
    alignment **failed** and raises :class:`DrawingDiffPipelineError`. If warping
    sub into master space fails, logs and returns ``[]`` (no persisted diffs).
    Persistence runs only when a detected item has non-empty ``summary`` and
    ``diff_regions``.
    """
    storage = StorageService(db)
    alignment_id = cast(int, alignment.id)

    logger.info("[compare-debug] run_drawing_diff start alignment_id=%s", alignment_id)

    try:
        # Step 1 — Resolve files
        master_path, sub_path, err = _resolve_file_paths(db, alignment)
        if err:
            logger.warning(
                "[compare-debug] run_drawing_diff resolve_paths failed alignment_id=%s err=%s",
                alignment_id,
                err,
            )
            logger.warning(
                "drawing_diff_resolve_failed",
                extra={"alignment_id": alignment_id, "error": err},
            )
            storage.update_alignment_status(
                alignment_id,
                "failed",
                error_message=err,
            )
            raise DrawingDiffPipelineError(message="Pipeline failure", details={"reason": err})

        if master_path is None or sub_path is None:
            raise DrawingDiffPipelineError(message="Pipeline failure", details={"reason": "File paths not resolved"})

        logger.info(
            "[compare-debug] run_drawing_diff paths OK alignment_id=%s master=%s sub=%s",
            alignment_id,
            master_path,
            sub_path,
        )

        master_id = cast(int, alignment.master_drawing_id)
        sub_id = cast(int, alignment.sub_drawing_id)
        master = db.query(Drawing).filter(Drawing.id == master_id).first()
        sub = db.query(Drawing).filter(Drawing.id == sub_id).first()
        if master is None or sub is None:
            raise DrawingDiffPipelineError(message="Pipeline failure", details={"reason": "Drawing rows missing"})

        page_i = _alignment_page_from_alignment(alignment)
        master_gray = _render_drawing_to_array(db=db, drawing=master, page=page_i)
        sub_gray = _render_drawing_to_array(db=db, drawing=sub, page=page_i)
        logger.info(
            "[compare-debug] run_drawing_diff render page=%s alignment_id=%s master_ok=%s sub_ok=%s",
            page_i,
            alignment_id,
            master_gray is not None,
            sub_gray is not None,
        )
        if master_gray is None or sub_gray is None:
            render_err = (
                "Drawing page render failed for diff "
                f"(page={page_i}, master_ok={master_gray is not None}, sub_ok={sub_gray is not None})"
            )
            logger.warning(
                "drawing_diff_render_failed",
                extra={
                    "alignment_id": alignment_id,
                    "page": page_i,
                    "master_ok": master_gray is not None,
                    "sub_ok": sub_gray is not None,
                },
            )
            storage.update_alignment_status(
                alignment_id,
                "failed",
                error_message=render_err,
            )
            raise DrawingDiffPipelineError(
                message="Pipeline failure",
                details={"reason": render_err},
            )

        transform = getattr(alignment, "transform", None)
        warped_sub = _warp_sub_raster_into_master(sub_gray, master_gray, transform)
        logger.info(
            "[compare-debug] run_drawing_diff warp alignment_id=%s warped_ok=%s",
            alignment_id,
            warped_sub is not None,
        )
        if warped_sub is None:
            logger.warning(
                "drawing_diff_no_warp_abort",
                extra={
                    "alignment_id": alignment_id,
                    "page": page_i,
                    "reason": "warp_sub_into_master_unavailable_or_failed",
                },
            )
            return []

        # Step 3 & 4 — Generate diff regions, score severity
        detected = _generate_and_score_diff(master_gray, warped_sub, page=page_i)
        logger.info(
            "[compare-debug] run_drawing_diff detected items alignment_id=%s count=%s",
            alignment_id,
            len(detected),
        )

        created: List[DrawingDiff] = []

        for item in detected:
            regions = item.get("diff_regions") or []
            summary_s = (item.get("summary") or "").strip()
            if not summary_s or not regions:
                continue
            try:
                diff = _persist_diff_and_finding(
                    storage,
                    alignment_id,
                    item,
                    severity_threshold,
                )
                if diff:
                    created.append(diff)
            except Exception as e:
                logger.exception(
                    "drawing_diff_persist_failed",
                    extra={"alignment_id": alignment_id, "item": str(item)[:200]},
                )
                # Continue with other diffs; do not fail entire pipeline

        logger.info(
            "drawing_diff_pipeline_completed",
            extra={
                "alignment_id": alignment_id,
                "diff_count": len(created),
                "detected_count": len(detected),
            },
        )
        return created

    except DrawingDiffPipelineError:
        raise
    except Exception as e:
        logger.exception(
            "drawing_diff_pipeline_failed",
            extra={"alignment_id": alignment_id},
        )
        try:
            storage.update_alignment_status(
                alignment_id,
                "failed",
                error_message=str(e),
            )
        except Exception:
            logger.exception("drawing_diff_status_update_failed")
        raise DrawingDiffPipelineError(message="Pipeline failure", details={"reason": str(e)})
