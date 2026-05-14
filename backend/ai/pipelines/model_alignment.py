"""
Learned / model-based drawing alignment (P4.2).

When :envvar:`USE_MODEL_ALIGNMENT` is enabled, the comparison service calls
:func:`try_learned_matcher_align` **before** the existing ORB + homography path.
This module returns ``None`` until a real matcher is wired; the ORB pipeline
remains the production fallback (P4.1).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "corner_correspondences_for_homography",
    "try_learned_matcher_align",
]

logger = logging.getLogger(__name__)

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment, misc]


def corner_correspondences_for_homography(
    H_row_major: List[float],
    w_sub: int,
    h_sub: int,
) -> Tuple[List[Dict[str, float]], List[Dict[str, float]]]:
    """
    Build four sub→master point pairs consistent with ``cv2.findHomography(sub, master)``.

    ``source_points`` are in **master** pixel space; ``target_points`` are in **sub**
    pixel space — same convention as :meth:`DrawingComparisonService.estimate_transform`.
    """
    if np is None:
        return [], []
    if len(H_row_major) != 9:
        return [], []
    H = np.array(H_row_major, dtype=np.float32).reshape(3, 3)
    corners = np.array(
        [
            [0.0, 0.0],
            [float(w_sub), 0.0],
            [float(w_sub), float(h_sub)],
            [0.0, float(h_sub)],
        ],
        dtype=np.float32,
    )
    hom = np.column_stack([corners, np.ones(4, dtype=np.float32)])
    proj = (H @ hom.T).T
    proj = proj[:, :2] / proj[:, 2:3]
    source = [{"x": float(proj[i, 0]), "y": float(proj[i, 1])} for i in range(4)]
    target = [{"x": float(corners[i, 0]), "y": float(corners[i, 1])} for i in range(4)]
    return source, target


def try_learned_matcher_align(
    master_gray: Any,
    sub_gray: Any,
    *,
    page: int,
) -> Optional[Dict[str, Any]]:
    """
    Attempt alignment with a learned matcher.

    Must return a dict compatible with :meth:`DrawingComparisonService.validate_transform`
    (``type``, 9-float ``matrix`` homography sub→master, ``confidence``, ``page``,
    ``source_points`` / ``target_points`` with at least four pairs), or ``None`` to use ORB.

    **MVP:** always returns ``None`` (ORB/homography only). Plug in inference here when ready.
    """
    del master_gray, sub_gray, page
    logger.debug("model_alignment_stub_skip")
    return None
