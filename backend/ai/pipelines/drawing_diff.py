"""
Drawing diff pipeline.

Compares master and sub drawing for an alignment, creates DrawingDiff records,
and optionally creates Findings when severity exceeds threshold.
"""

from __future__ import annotations

import logging
from pathlib import Path
from sqlalchemy.orm import Session
from typing import Any, Dict, List, Optional, Tuple, cast

from errors import DrawingDiffPipelineError
from models.models import Drawing, DrawingAlignment, DrawingDiff
from services.file_storage import get_file_path
from services.storage import StorageService

logger = logging.getLogger(__name__)


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
# Step 2 — Warp Sub Drawing
# ---------------------------------------------------------------------------


def _warp_sub_into_master(
    master_path: Path,
    sub_path: Path,
    transform: Optional[Dict[str, Any]],
) -> Optional[Any]:
    """
    Apply alignment.transform.matrix to warp sub drawing into master coordinates.
    Returns warped image/data for diff, or None if skipped.

    MVP: Placeholder. Requires OpenCV/PIL. Implement when vision stack is added.
    """
    if not transform or not isinstance(transform.get("matrix"), (list, tuple)):
        return None
    # TODO: Load images, build 3x3 homography from matrix, warp sub, return
    return None


# ---------------------------------------------------------------------------
# Step 3 & 4 — Generate Diff Regions, Score Severity
# ---------------------------------------------------------------------------


def _generate_and_score_diff(
    master_path: Path,
    sub_path: Path,
    warped_sub: Optional[Any],
) -> List[Dict[str, Any]]:
    """
    Produce normalized diff geometry and compute severity.
    Returns list of { summary, severity, diff_regions }.

    Diff region: { page, type, points, label, confidence }
    Severity from: number of regions, size of differences, confidence levels.

    MVP: Placeholder. Implement image-diff logic when vision stack is added.
    """
    # TODO: Run pixel/comparison diff, produce regions with normalized 0-1 coords,
    # score severity from metrics (region count, area, confidence)
    return []


# ---------------------------------------------------------------------------
# Step 5 & 6 — Persist Diff, Create Finding
# ---------------------------------------------------------------------------


def _persist_diff_and_finding(
    storage: StorageService,
    alignment_id: int,
    item: Dict[str, Any],
    severity_threshold: str,
) -> Optional[DrawingDiff]:
    """Create DrawingDiff, optionally create Finding if severity >= threshold."""
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
    """
    storage = StorageService(db)
    alignment_id = cast(int, alignment.id)

    try:
        # Step 1 — Resolve files
        master_path, sub_path, err = _resolve_file_paths(db, alignment)
        if err:
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

        # Step 2 — Warp sub drawing
        transform = getattr(alignment, "transform", None)
        warped_sub = _warp_sub_into_master(master_path, sub_path, transform)

        # Step 3 & 4 — Generate diff regions, score severity
        detected = _generate_and_score_diff(master_path, sub_path, warped_sub)

        created: List[DrawingDiff] = []

        for item in detected:
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
