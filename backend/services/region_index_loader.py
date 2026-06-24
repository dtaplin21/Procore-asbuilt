"""Build MasterRegion index entries from persisted drawing_regions rows.

Case B reference lookup in drawing_location_resolver.py matches uploaded
evidence vocabulary terms against inspection_type_tags and location_tags
on each region. Geometry is converted to a fractional BoundingBox for
bbox_on_master (normalized 0-1, same coordinate space as region geometry).
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from sqlalchemy.orm import Session

from ai.pipelines.document_text_extraction import BoundingBox
from ai.pipelines.drawing_location_resolver import MasterRegion
from models.models import DrawingRegion

logger = logging.getLogger(__name__)


def _normalize_tag_list(raw: Any) -> tuple[str, ...]:
    if not raw:
        return ()
    if not isinstance(raw, (list, tuple)):
        return ()
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        tag = item.strip()
        if not tag:
            continue
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(tag)
    return tuple(out)


def geometry_to_bounding_box(geometry: dict[str, Any]) -> BoundingBox | None:
    """Convert normalized drawing_regions geometry to a fractional bbox.

    Region geometry is stored normalized 0-1 (rect or polygon). We use
    page_width/page_height of 1 so BoundingBox.to_fractional() returns
    the same coordinates.
    """
    if not isinstance(geometry, dict):
        return None

    gtype = geometry.get("type")
    if gtype == "rect":
        try:
            x = float(geometry["x"])
            y = float(geometry["y"])
            width = float(geometry["width"])
            height = float(geometry["height"])
        except (KeyError, TypeError, ValueError):
            return None
        return BoundingBox(
            x=x,
            y=y,
            width=width,
            height=height,
            page_width=1.0,
            page_height=1.0,
        )

    if gtype == "polygon":
        points = geometry.get("points")
        if not isinstance(points, list) or not points:
            return None
        xs: list[float] = []
        ys: list[float] = []
        for pt in points:
            if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                continue
            try:
                xs.append(float(pt[0]))
                ys.append(float(pt[1]))
            except (TypeError, ValueError):
                continue
        if not xs or not ys:
            return None
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        return BoundingBox(
            x=min_x,
            y=min_y,
            width=max_x - min_x,
            height=max_y - min_y,
            page_width=1.0,
            page_height=1.0,
        )

    return None


def drawing_region_to_master_region(region: DrawingRegion) -> MasterRegion | None:
    """Map one DrawingRegion ORM row to a MasterRegion, or None if geometry is invalid."""
    geometry = getattr(region, "geometry", None)
    if not isinstance(geometry, dict):
        logger.warning(
            "Skipping drawing_region id=%s: geometry is not a dict",
            getattr(region, "id", "?"),
        )
        return None

    bbox = geometry_to_bounding_box(geometry)
    if bbox is None:
        logger.warning(
            "Skipping drawing_region id=%s: unsupported or invalid geometry",
            getattr(region, "id", "?"),
        )
        return None

    master_drawing_id = getattr(region, "master_drawing_id", None)
    region_id = getattr(region, "id", None)
    if master_drawing_id is None or region_id is None:
        return None

    return MasterRegion(
        region_id=str(region_id),
        master_drawing_id=str(master_drawing_id),
        inspection_types=_normalize_tag_list(getattr(region, "inspection_type_tags", None)),
        location_labels=_normalize_tag_list(getattr(region, "location_tags", None)),
        bbox_on_master=bbox,
    )


def regions_to_master_index(
    regions: Sequence[DrawingRegion],
) -> list[MasterRegion]:
    """Convert persisted regions to the in-memory index used by Case B lookup."""
    out: list[MasterRegion] = []
    for region in regions:
        mapped = drawing_region_to_master_region(region)
        if mapped is not None:
            out.append(mapped)
    return out


def load_master_regions(
    db: Session,
    master_drawing_id: int,
) -> list[MasterRegion]:
    """Load all regions for a master drawing and build the resolver index."""
    rows = (
        db.query(DrawingRegion)
        .filter(DrawingRegion.master_drawing_id == master_drawing_id)
        .order_by(DrawingRegion.id.asc())
        .all()
    )
    return regions_to_master_index(rows)
