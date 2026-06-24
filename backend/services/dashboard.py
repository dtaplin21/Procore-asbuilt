"""
Dashboard and cross-project metrics.

Inspection coverage KPIs live here so StorageService and routes stay thin.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from models.models import Drawing


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

    * ``total_masters_count`` — ``1`` when ``projects.master_drawing_id`` is set, else ``0``.
    * ``inspected_count`` — distinct masters with at least one **complete** inspection run.
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


def get_unresolved_high_severity_diff_metric(db: Session) -> dict:
    """Deprecated compare KPI — compare stack removed; always returns zero."""
    _ = db
    return {
        "unresolved_high_severity_count": 0,
        "label": "Compare diffs removed; no unresolved diff risk metric.",
    }


__all__ = [
    "get_current_drawing_for_project",
    "get_project_inspection_coverage",
    "get_unresolved_high_severity_diff_metric",
]
