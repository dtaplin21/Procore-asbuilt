"""
Dashboard and cross-project metrics.

Inspection coverage and diff-risk counts live here so StorageService and routes stay
thin and definitions stay consistent.
"""

from __future__ import annotations

from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from models.models import Drawing, DrawingAlignment, DrawingDiff, InspectionRun, Project


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


def get_project_inspection_coverage(db: Session, project_id: int) -> dict:
    """
    Master inspection coverage for dashboard KPIs.

    * ``total_masters_count`` — canonical master on the project (``projects.master_drawing_id``)
      when set, otherwise drawings with ``upload_intent == \"master\"``.
    * ``inspected_count`` — distinct master drawings with at least one **complete**
      inspection run (queued/processing runs are excluded so the label stays truthful).
    """
    from services.storage import StorageService

    storage = StorageService(db)
    total_masters_count = storage.count_project_master_drawings(project_id)
    inspected_count = storage.count_drawings_with_inspection_run(project_id)

    if total_masters_count > 0:
        label = (
            f"{inspected_count} of {total_masters_count} master drawing(s) have been "
            f"inspected for this project."
        )
    else:
        label = "Upload a master drawing to start inspection coverage tracking."

    return {
        "inspected_count": inspected_count,
        "total_masters_count": total_masters_count,
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
    "get_project_inspection_coverage",
    "get_project_unresolved_high_severity_diff_metric",
    "get_unresolved_high_severity_diff_metric",
]
