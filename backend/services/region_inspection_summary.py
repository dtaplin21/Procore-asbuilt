"""
Implements GET .../region-inspection-summary from the region-visibility spec (PR1).

Joins drawing_regions + drawing_overlays + inspection_runs to answer, for every
backend region on a master drawing, whether it is hidden (no inspection linked)
or inspected (>=1 overlay links to it), plus display fields for the Objects
viewer bold region and hover tooltip.

Reconciled with this codebase: integer PKs, ``master_drawing_id``, normalized
``geometry`` JSON (not separate x/y/width columns), ``tags_json`` as JSON dict,
``created_at`` as upload timestamp (``DrawingOverlay.uploaded_at``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from models.drawing_overlay import DrawingOverlay
from models.drawing_region import DrawingRegion
from models.inspection_run import InspectionRun
from services.region_index_loader import geometry_to_bounding_box


class RegionViewerState(str, Enum):
    HIDDEN = "hidden"
    INSPECTED = "inspected"


@dataclass(frozen=True)
class RegionInspectionSummaryEntry:
    region_id: int
    master_drawing_id: int
    state: RegionViewerState
    label: str
    bbox: tuple[float, float, float, float]
    location_tags: tuple[str, ...]
    inspection_type_tags: tuple[str, ...]
    latest_overlay_id: int | None = None
    latest_inspection_run_id: int | None = None
    inspection_type: str | None = None
    inspection_status_display: str | None = None
    inspection_date: date | None = None
    procore_inspection_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "regionId": self.region_id,
            "masterDrawingId": self.master_drawing_id,
            "state": self.state.value,
            "label": self.label,
            "bbox": list(self.bbox),
            "locationTags": list(self.location_tags),
            "inspectionTypeTags": list(self.inspection_type_tags),
            "latestOverlayId": self.latest_overlay_id,
            "latestInspectionRunId": self.latest_inspection_run_id,
            "inspectionType": self.inspection_type,
            "inspectionStatusDisplay": self.inspection_status_display,
            "inspectionDate": self.inspection_date.isoformat() if self.inspection_date else None,
            "procoreInspectionId": self.procore_inspection_id,
        }


def _normalize_tag_tuple(raw: Any) -> tuple[str, ...]:
    if not raw:
        return ()
    if not isinstance(raw, (list, tuple)):
        return ()
    out: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return tuple(out)


def _region_bbox_fractional(region: DrawingRegion) -> tuple[float, float, float, float]:
    geometry = getattr(region, "geometry", None)
    if isinstance(geometry, dict):
        bbox = geometry_to_bounding_box(geometry)
        if bbox is not None:
            return bbox.to_fractional()
    return (0.0, 0.0, 0.0, 0.0)


def _inspection_status_display(overlay: DrawingOverlay) -> str | None:
    """Full vocab string from tags_json.inspectionStatuses[0], not overlay.status."""
    raw = getattr(overlay, "tags_json", None)
    tags: dict[str, Any] | None = None
    if isinstance(raw, dict):
        tags = raw
    elif isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                tags = parsed
        except (TypeError, ValueError):
            tags = None
    if tags is None:
        meta = getattr(overlay, "meta", None)
        if isinstance(meta, dict):
            tags = meta
    if not tags:
        return None
    statuses = tags.get("inspectionStatuses") or []
    if not statuses:
        return None
    first = statuses[0]
    return str(first) if first is not None else None


def _inspection_type_display(
    overlay: DrawingOverlay,
    run: InspectionRun | None,
    inspection_type_tags: tuple[str, ...],
) -> str | None:
    if run is not None:
        run_type = getattr(run, "inspection_type", None)
        if isinstance(run_type, str) and run_type.strip():
            return run_type.strip()
    tags = getattr(overlay, "tags_json", None)
    if isinstance(tags, dict):
        types = tags.get("inspectionTypes") or []
        if types and isinstance(types[0], str):
            return types[0]
    if inspection_type_tags:
        return inspection_type_tags[0]
    label = getattr(overlay, "label", None)
    if isinstance(label, str) and label.strip():
        return label.strip()
    return None


def _uploaded_at(overlay: DrawingOverlay) -> datetime:
    uploaded = getattr(overlay, "uploaded_at", None)
    if isinstance(uploaded, datetime):
        return uploaded
    created = getattr(overlay, "created_at", None)
    if isinstance(created, datetime):
        return created
    return datetime.min.replace(tzinfo=None)


def build_region_inspection_summary(
    db: Session,
    master_drawing_id: int | str,
) -> list[RegionInspectionSummaryEntry]:
    """Build summary rows for every backend region on a master drawing."""
    drawing_id = int(master_drawing_id)
    regions = (
        db.query(DrawingRegion)
        .filter(DrawingRegion.master_drawing_id == drawing_id)
        .order_by(DrawingRegion.id.asc())
        .all()
    )
    if not regions:
        return []

    overlays = (
        db.query(DrawingOverlay)
        .filter(
            DrawingOverlay.master_drawing_id == drawing_id,
            DrawingOverlay.region_id.isnot(None),
        )
        .all()
    )

    latest_overlay_by_region: dict[int, DrawingOverlay] = {}
    for overlay in overlays:
        region_id = getattr(overlay, "region_id", None)
        if region_id is None:
            continue
        rid = int(region_id)
        existing = latest_overlay_by_region.get(rid)
        if existing is None or _uploaded_at(overlay) > _uploaded_at(existing):
            latest_overlay_by_region[rid] = overlay

    run_ids = {
        int(o.inspection_run_id)
        for o in latest_overlay_by_region.values()
        if getattr(o, "inspection_run_id", None) is not None
    }
    runs_by_id: dict[int, InspectionRun] = {}
    if run_ids:
        runs = db.query(InspectionRun).filter(InspectionRun.id.in_(run_ids)).all()
        runs_by_id = {int(r.id): r for r in runs}

    entries: list[RegionInspectionSummaryEntry] = []
    for region in regions:
        rid = int(region.id)
        location_tags = _normalize_tag_tuple(getattr(region, "location_tags", None))
        inspection_type_tags = _normalize_tag_tuple(
            getattr(region, "inspection_type_tags", None)
        )
        bbox = _region_bbox_fractional(region)
        label = str(getattr(region, "label", "") or "")

        latest_overlay = latest_overlay_by_region.get(rid)
        if latest_overlay is None:
            entries.append(
                RegionInspectionSummaryEntry(
                    region_id=rid,
                    master_drawing_id=drawing_id,
                    state=RegionViewerState.HIDDEN,
                    label=label,
                    bbox=bbox,
                    location_tags=location_tags,
                    inspection_type_tags=inspection_type_tags,
                )
            )
            continue

        run_id = int(latest_overlay.inspection_run_id)
        run = runs_by_id.get(run_id)
        entries.append(
            RegionInspectionSummaryEntry(
                region_id=rid,
                master_drawing_id=drawing_id,
                state=RegionViewerState.INSPECTED,
                label=label,
                bbox=bbox,
                location_tags=location_tags,
                inspection_type_tags=inspection_type_tags,
                latest_overlay_id=int(latest_overlay.id),
                latest_inspection_run_id=run_id,
                inspection_type=_inspection_type_display(
                    latest_overlay, run, inspection_type_tags
                ),
                inspection_status_display=_inspection_status_display(latest_overlay),
                inspection_date=getattr(latest_overlay, "inspection_date", None),
                procore_inspection_id=(
                    str(run.procore_inspection_id)
                    if run is not None and getattr(run, "procore_inspection_id", None)
                    else None
                ),
            )
        )

    return entries
