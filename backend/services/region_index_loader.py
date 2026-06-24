"""Build the list[MasterRegion] that drawing_location_resolver.py matches against.

Reads from the drawing_regions table (inspection_type_tags and location_tags
columns — migration a3f9c1d8e2b4, model in models.models.DrawingRegion).

Intended caller pattern (evidence upload / document pipeline):

    result = build_region_index(db_session, master_drawing_id)
    evidence = DocumentEvidenceInput(..., region_index=result.regions)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Sequence

from sqlalchemy.orm import Session

from ai.pipelines.document_text_extraction import BoundingBox
from ai.pipelines.drawing_location_resolver import MasterRegion
from models.models import DrawingRegion

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegionIndexLoadResult:
    """Resolved MasterRegion list plus diagnostics for callers and admin views."""

    regions: list[MasterRegion]
    total_region_count: int
    untagged_region_count: int

    @property
    def has_any_taggable_regions(self) -> bool:
        return self.total_region_count > 0

    @property
    def has_any_usable_regions(self) -> bool:
        return len(self.regions) > 0


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


def _is_untagged(row: DrawingRegion) -> bool:
    type_tags = getattr(row, "inspection_type_tags", None) or []
    location_tags = getattr(row, "location_tags", None) or []
    return not type_tags and not location_tags


def geometry_to_bounding_box(geometry: dict[str, Any]) -> BoundingBox | None:
    """Convert normalized drawing_regions geometry to a fractional bbox."""
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
    """Convert persisted regions to MasterRegion entries (skips invalid geometry)."""
    out: list[MasterRegion] = []
    for region in regions:
        mapped = drawing_region_to_master_region(region)
        if mapped is not None:
            out.append(mapped)
    return out


def build_region_index(
    db: Session,
    drawing_id: int | str,
    *,
    include_untagged: bool = False,
) -> RegionIndexLoadResult:
    """Load regions for a master drawing into the resolver's MasterRegion shape.

    By default, untagged regions (no inspection_type_tags and no location_tags)
    are excluded from ``regions`` but counted in ``untagged_region_count``.
    Pass ``include_untagged=True`` to include every mappable region regardless
    of tag state (e.g. Case A alignment overlap or admin/debug views).
    """
    master_drawing_id = int(drawing_id)
    rows: list[DrawingRegion] = (
        db.query(DrawingRegion)
        .filter(DrawingRegion.master_drawing_id == master_drawing_id)
        .order_by(DrawingRegion.id.asc())
        .all()
    )

    total = len(rows)
    untagged_rows = [row for row in rows if _is_untagged(row)]

    if include_untagged:
        candidate_rows = rows
    else:
        candidate_rows = [row for row in rows if row not in untagged_rows]

    regions = regions_to_master_index(candidate_rows)

    return RegionIndexLoadResult(
        regions=regions,
        total_region_count=total,
        untagged_region_count=len(untagged_rows),
    )


def load_master_regions(
    db: Session,
    master_drawing_id: int,
    *,
    include_untagged: bool = False,
) -> list[MasterRegion]:
    """Convenience wrapper returning only the MasterRegion list."""
    return build_region_index(
        db,
        master_drawing_id,
        include_untagged=include_untagged,
    ).regions
