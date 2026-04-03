"""
Dashboard and cross-project metrics.

All comparison / diff-risk counts live here so StorageService and routes stay thin
and definitions stay consistent.
"""

from __future__ import annotations

from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from models.models import Drawing, DrawingAlignment, DrawingDiff, Project


def get_current_drawing_for_project(
    db: Session,
    project_id: int,
    current_drawing_id: int | None = None,
) -> Drawing | None:
    """
    Optional workspace-selected master drawing for dashboard summary.

    When ``current_drawing_id`` is set, returns that row if it belongs to ``project_id``;
    otherwise returns ``None`` (caller should not infer a default master).
    """
    if current_drawing_id is None:
        return None
    return (
        db.query(Drawing)
        .filter(Drawing.id == current_drawing_id, Drawing.project_id == project_id)
        .first()
    )


def get_project_comparison_progress(
    db: Session,
    project_id: int,
    master_drawing_id: int | None = None,
) -> dict:
    """
    Compared = distinct sub drawings that have at least one **complete** alignment
    (``DrawingAlignment.status == \"complete\"``). Only complete is counted so the
    label stays truthful (queued/processing are not "compared" yet).

    * Project scope (``master_drawing_id`` is None): all drawings in the project
      are the relevant pool; compared = distinct subs with a complete alignment in
      this project.
    * Master scope: relevant pool = drawings in the project except this master;
      compared = distinct subs with a complete alignment **for this master**.
    """
    relevant_query = db.query(func.count(Drawing.id)).filter(
        Drawing.project_id == project_id,
    )
    if master_drawing_id is not None:
        relevant_query = relevant_query.filter(Drawing.id != master_drawing_id)
    total_relevant_count = int(relevant_query.scalar() or 0)

    compared_query = (
        db.query(func.count(distinct(DrawingAlignment.sub_drawing_id)))
        .join(Drawing, Drawing.id == DrawingAlignment.sub_drawing_id)
        .filter(
            Drawing.project_id == project_id,
            DrawingAlignment.project_id == project_id,
            DrawingAlignment.status == "complete",
        )
    )
    if master_drawing_id is not None:
        compared_query = compared_query.filter(
            DrawingAlignment.master_drawing_id == master_drawing_id,
        )

    compared_count = int(compared_query.scalar() or 0)

    if master_drawing_id is not None:
        label = (
            f"{compared_count} of {total_relevant_count} relevant sub drawings have been "
            f"compared for this master."
        )
    else:
        label = (
            f"{compared_count} of {total_relevant_count} relevant sub drawings have been "
            f"compared for this project."
        )

    return {
        "compared_count": compared_count,
        "total_relevant_count": total_relevant_count,
        "label": label,
    }


def get_project_unresolved_high_severity_diff_metric(db: Session, project_id: int) -> dict:
    """
    Project-scoped unresolved high/critical diffs (``resolved`` is false on ``drawing_diffs``).
    Severity uses the same rule as the DB check: ``high`` and ``critical``.
    """
    count = (
        db.query(func.count(DrawingDiff.id))
        .join(DrawingAlignment, DrawingDiff.alignment_id == DrawingAlignment.id)
        .filter(
            DrawingAlignment.project_id == project_id,
            DrawingDiff.severity.in_(["high", "critical"]),
            DrawingDiff.resolved.is_(False),
        )
        .scalar()
        or 0
    )
    return {
        "unresolved_high_severity_count": int(count),
        "label": (
            "Unresolved high or critical diffs (severity high/critical; resolved=false on diff)"
        ),
    }


def get_unresolved_high_severity_diff_metric(db: Session) -> dict:
    """
    All unresolved high/critical diffs for drawings in **active** projects.

    ``drawing_diffs`` has no ``project_id``; we join alignment → master drawing → project.
    """
    count = (
        db.query(func.count(DrawingDiff.id))
        .join(DrawingAlignment, DrawingAlignment.id == DrawingDiff.alignment_id)
        .join(Drawing, Drawing.id == DrawingAlignment.master_drawing_id)
        .join(Project, Project.id == Drawing.project_id)
        .filter(
            Project.status == "active",
            DrawingDiff.severity.in_(["high", "critical"]),
            DrawingDiff.resolved.is_(False),
        )
        .scalar()
        or 0
    )
    return {
        "unresolved_high_severity_count": int(count),
        "label": (
            f"{count} unresolved high or critical diffs across your active projects."
        ),
    }


__all__ = [
    "get_current_drawing_for_project",
    "get_project_comparison_progress",
    "get_project_unresolved_high_severity_diff_metric",
    "get_unresolved_high_severity_diff_metric",
]
