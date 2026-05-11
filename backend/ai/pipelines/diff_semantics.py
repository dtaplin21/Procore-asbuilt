"""
Per-region semantic deltas for drawing compare (MVP heuristics).

Takes aligned crops in the **same** pixel frame (master patch vs warped-sub patch).
Output is structured JSON suitable for :attr:`DrawingDiff.semantic_summary` or LLM post-processing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Tuple

__all__ = ["compare_cropped_regions_semantics"]

if TYPE_CHECKING:
    from numpy import ndarray

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment, misc]

# Pixel difference considered “changed” for occupancy stats (0–255 grayscale).
_DEFAULT_DIFF_THRESHOLD = 18


def _coerce_gray_u8(arr: Any) -> "ndarray":
    if np is None:
        raise RuntimeError("NumPy is required for diff_semantics")
    if arr is None or not hasattr(arr, "shape"):
        raise ValueError("Crop must be a numpy array")
    if arr.ndim != 2:
        raise ValueError("Crop must be a single-channel (H, W) grayscale array")
    if arr.size == 0:
        raise ValueError("Crop must be non-empty")
    if arr.dtype != np.uint8:
        arr = np.clip(np.asarray(arr, dtype=np.float64), 0, 255).astype(np.uint8)
    return arr


def _severity_from_signals(mean_delta: float, change_frac: float) -> str:
    """Map mean |Δ| (0–255) and changed-pixel fraction (0–1) to low..critical."""
    score = (mean_delta / 255.0) * 0.55 + min(1.0, change_frac * 1.25) * 0.45
    if score < 0.08:
        return "low"
    if score < 0.16:
        return "medium"
    if score < 0.28:
        return "high"
    return "critical"


def _change_type_and_description(
    master_mean: float,
    sub_mean: float,
    mean_abs: float,
    change_frac: float,
) -> Tuple[str, str]:
    """Heuristic labels; refined later by LLM or richer vision."""
    delta = sub_mean - master_mean
    strength = "substantial" if mean_abs > 35 else "moderate" if mean_abs > 18 else "subtle"

    if change_frac < 0.015 and mean_abs < 8:
        return (
            "minimal_difference",
            "Almost no visible difference between master and sub in this region.",
        )

    # Sub drawing darker on average → common for new ink / annotations.
    if delta < -6 and change_frac >= 0.02:
        return (
            "added_annotation",
            f"New darker marked area ({strength} contrast) appears in the sub drawing versus master.",
        )
    # Sub lighter → highlights, clouds, or erased master content.
    if delta > 6 and change_frac >= 0.02:
        return (
            "added_annotation",
            f"New lighter marked area ({strength} contrast) appears in the sub drawing versus master.",
        )

    return (
        "modified_region",
        f"Content differs between master and sub in this region ({strength} change; "
        f"~{change_frac * 100:.0f}% of pixels shifted).",
    )


def compare_cropped_regions_semantics(
    master_crop: Any,
    warped_sub_crop: Any,
    *,
    diff_threshold: int = _DEFAULT_DIFF_THRESHOLD,
) -> Dict[str, Any]:
    """
    Compare two aligned grayscale crops and return a structured semantic delta.

    Contract (keys are stable for API / UI):

    - ``change_type``: short machine label (heuristic).
    - ``description``: human-readable sentence.
    - ``severity``: ``low`` | ``medium`` | ``high`` | ``critical``.

    Extra diagnostic keys (``mean_abs_diff``, ``changed_pixel_frac``, ``source``) are
    included for debugging and future LLM context; consumers may ignore them.

    Args:
        master_crop: ``H×W`` uint8 grayscale patch from master raster.
        warped_sub_crop: Same shape, from warped sub in master coordinates.
        diff_threshold: Minimum absolute per-pixel delta to count as “changed”.
    """
    if np is None:
        raise RuntimeError("NumPy is required for diff_semantics")
    m = _coerce_gray_u8(master_crop)
    s = _coerce_gray_u8(warped_sub_crop)
    if m.shape != s.shape:
        raise ValueError(
            f"Crops must match shape; got master {m.shape} vs sub {s.shape}",
        )
    th = max(1, min(255, int(diff_threshold)))

    md = m.astype(np.float32)
    sd = s.astype(np.float32)
    adiff = np.abs(sd - md)
    mean_abs = float(np.mean(adiff))
    changed_frac = float(np.mean(adiff >= th))
    master_mean = float(np.mean(md))
    sub_mean = float(np.mean(sd))

    change_type, description = _change_type_and_description(
        master_mean,
        sub_mean,
        mean_abs,
        changed_frac,
    )
    severity = _severity_from_signals(mean_abs, changed_frac)

    out: Dict[str, Any] = {
        "change_type": change_type,
        "description": description,
        "severity": severity,
    }

    # Non-contract debug / LLM context (optional for clients).
    out["mean_abs_diff"] = round(mean_abs, 4)
    out["changed_pixel_frac"] = round(changed_frac, 6)
    out["source"] = "heuristic_crop_compare"

    return out
