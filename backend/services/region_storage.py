"""
CRUD persistence for DrawingRegion — PR2 of the region-visibility spec.

Mirrors overlay_storage.py: module-level functions called from routes and
StorageService. Geometry is normalized 0–1 JSON (rect or polygon), reconciled
with models.drawing_region.DrawingRegion — not separate pixel columns.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from models.drawing_region import DrawingRegion


def _check_normalized(value: float, name: str) -> None:
    if not (0 <= value <= 1):
        raise ValueError(f"{name} must be 0-1 (normalized), got {value}")


def validate_region_geometry(
    geometry: dict[str, Any],
    *,
    polygon_points: list[list[float]] | None = None,
) -> None:
    """Validate normalized geometry. Raises ValueError on invalid input."""
    if not isinstance(geometry, dict):
        raise ValueError("geometry must be an object")

    gtype = geometry.get("type")
    if gtype == "rect":
        for key in ("x", "y", "width", "height"):
            if key not in geometry:
                raise ValueError(f"rect geometry requires {key}")
            val = geometry[key]
            if not isinstance(val, (int, float)):
                raise ValueError(f"{key} must be a number")
            _check_normalized(float(val), key)
        width = float(geometry["width"])
        height = float(geometry["height"])
        if width <= 0 or height <= 0:
            raise ValueError("Region bounding box must have positive width and height.")
    elif gtype == "polygon":
        pts = geometry.get("points")
        if not isinstance(pts, list):
            raise ValueError("polygon must have points array")
        if len(pts) < 3:
            raise ValueError("A polygon region needs at least 3 points.")
        for i, p in enumerate(pts):
            if not isinstance(p, (list, tuple)) or len(p) < 2:
                raise ValueError(f"point {i} must be [x, y]")
            _check_normalized(float(p[0]), f"points[{i}][0]")
            _check_normalized(float(p[1]), f"points[{i}][1]")
    else:
        raise ValueError("geometry.type must be 'rect' or 'polygon'")

    if polygon_points is not None:
        if len(polygon_points) < 3:
            raise ValueError("polygon_points needs at least 3 points.")
        for i, p in enumerate(polygon_points):
            if not isinstance(p, (list, tuple)) or len(p) < 2:
                raise ValueError(f"polygon_points[{i}] must be [x, y]")
            _check_normalized(float(p[0]), f"polygon_points[{i}][0]")
            _check_normalized(float(p[1]), f"polygon_points[{i}][1]")


def _normalize_tag_list(raw: list[str] | None) -> list[str]:
    if not raw:
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def get_drawing_region(
    db: Session,
    master_drawing_id: int,
    region_id: int,
) -> DrawingRegion | None:
    return (
        db.query(DrawingRegion)
        .filter(
            DrawingRegion.master_drawing_id == master_drawing_id,
            DrawingRegion.id == region_id,
        )
        .first()
    )


def list_drawing_regions(db: Session, master_drawing_id: int) -> list[DrawingRegion]:
    return (
        db.query(DrawingRegion)
        .filter(DrawingRegion.master_drawing_id == master_drawing_id)
        .order_by(DrawingRegion.created_at.desc(), DrawingRegion.id.desc())
        .all()
    )


def create_drawing_region(
    db: Session,
    master_drawing_id: int,
    *,
    label: str,
    page: int = 1,
    geometry: dict[str, Any],
    polygon_points: list[list[float]] | None = None,
    inspection_type_tags: list[str] | None = None,
    location_tags: list[str] | None = None,
) -> DrawingRegion:
    validate_region_geometry(geometry, polygon_points=polygon_points)

    row = DrawingRegion(
        master_drawing_id=master_drawing_id,
        label=label,
        page=page,
        geometry=geometry,
        polygon_points=polygon_points,
        inspection_type_tags=_normalize_tag_list(inspection_type_tags),
        location_tags=_normalize_tag_list(location_tags),
    )
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return row


def update_drawing_region(
    db: Session,
    master_drawing_id: int,
    region_id: int,
    *,
    label: str | None = None,
    page: int | None = None,
    geometry: dict[str, Any] | None = None,
    polygon_points: list[list[float]] | None | object = ...,
    inspection_type_tags: list[str] | None = None,
    location_tags: list[str] | None = None,
) -> DrawingRegion | None:
    """Partial update — only provided fields are changed (PATCH semantics)."""
    row = get_drawing_region(db, master_drawing_id, region_id)
    if row is None:
        return None

    next_geometry = geometry if geometry is not None else row.geometry
    next_polygon = row.polygon_points if polygon_points is ... else polygon_points
    if geometry is not None or polygon_points is not ...:
        validate_region_geometry(next_geometry, polygon_points=next_polygon)

    if label is not None:
        row.label = label
    if page is not None:
        row.page = page
    if geometry is not None:
        row.geometry = geometry
    if polygon_points is not ...:
        row.polygon_points = polygon_points
    if inspection_type_tags is not None:
        row.inspection_type_tags = _normalize_tag_list(inspection_type_tags)
    if location_tags is not None:
        row.location_tags = _normalize_tag_list(location_tags)

    row.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return row


def delete_drawing_region(
    db: Session,
    master_drawing_id: int,
    region_id: int,
) -> bool:
    """Delete a region. Overlay region_id is SET NULL by the DB FK."""
    row = get_drawing_region(db, master_drawing_id, region_id)
    if row is None:
        return False
    db.delete(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return True
