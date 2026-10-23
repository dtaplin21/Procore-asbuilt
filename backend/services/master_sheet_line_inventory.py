"""Inventory of digitized SheetLines on a master drawing (placement readiness)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, cast

from sqlalchemy.orm import Session

from models.models import Drawing
from services.inspection_placement_errors import (
    MASTER_SHEET_GRAPH_MISSING,
    MASTER_SHEET_LINES_NOT_PLACABLE,
)
from services.sheet_digitization import SHEET_ENTITY_GRAPH_KEY, load_page_lines

# Keep in sync with scope_line_tracer plan-band heuristics.
_PLAN_VIEW_MAX_Y = 0.55
_PLAN_VIEW_MIN_Y = 0.10
_DEFAULT_MIN_CONFIDENCE = 0.7


@dataclass(frozen=True)
class MasterSheetLineInventory:
    drawing_id: int
    page: int
    graph_present: bool
    line_count: int
    plan_viewport_count: int
    high_conf_plan_line_count: int
    profile_only_line_count: int
    is_placable: bool
    blocker_code: str | None
    blocker_message: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def master_sheet_lines_required_for_matching() -> bool:
    """When true, inspection match jobs defer until placable master sheet lines exist."""
    from services.inspection_placement_errors import placement_strict_enabled

    return placement_strict_enabled()


def get_master_sheet_line_inventory(
    session: Session,
    drawing_id: int,
    *,
    page: int = 1,
    min_confidence: float = _DEFAULT_MIN_CONFIDENCE,
) -> MasterSheetLineInventory:
    drawing = session.get(Drawing, int(drawing_id))
    if drawing is None:
        return MasterSheetLineInventory(
            drawing_id=int(drawing_id),
            page=page,
            graph_present=False,
            line_count=0,
            plan_viewport_count=0,
            high_conf_plan_line_count=0,
            profile_only_line_count=0,
            is_placable=False,
            blocker_code=MASTER_SHEET_GRAPH_MISSING,
            blocker_message=f"Drawing {drawing_id} not found",
        )
    stats = cast(dict[str, Any] | None, drawing.index_stats_json)
    return inventory_from_index_stats(
        stats,
        drawing_id=int(drawing_id),
        page=page,
        min_confidence=min_confidence,
    )


def inventory_from_index_stats(
    stats: dict[str, Any] | None,
    *,
    drawing_id: int,
    page: int = 1,
    min_confidence: float = _DEFAULT_MIN_CONFIDENCE,
) -> MasterSheetLineInventory:
    if not isinstance(stats, dict):
        return _empty_inventory(
            drawing_id=drawing_id,
            page=page,
            code=MASTER_SHEET_GRAPH_MISSING,
            message=f"No index_stats_json on master drawing {drawing_id}",
        )

    graphs = stats.get(SHEET_ENTITY_GRAPH_KEY)
    if not isinstance(graphs, dict) or not graphs:
        return _empty_inventory(
            drawing_id=drawing_id,
            page=page,
            code=MASTER_SHEET_GRAPH_MISSING,
            message=(
                f"No {SHEET_ENTITY_GRAPH_KEY} on master drawing {drawing_id} "
                f"(re-index with SHEET_DIGITIZATION_ENABLED=true)"
            ),
        )

    page_graph = graphs.get(str(page))
    if not isinstance(page_graph, dict):
        return _empty_inventory(
            drawing_id=drawing_id,
            page=page,
            code=MASTER_SHEET_GRAPH_MISSING,
            message=f"No sheet graph for page {page} on master drawing {drawing_id}",
        )

    plan_viewport_count = sum(
        1
        for vp in page_graph.get("viewports") or []
        if isinstance(vp, dict) and vp.get("kind") == "plan"
    )
    plan_bbox = _plan_viewport_bbox(page_graph)

    raw_lines = load_page_lines(page_graph)
    line_count = sum(1 for raw in raw_lines if isinstance(raw, dict))

    high_conf_plan = 0
    profile_only = 0
    for raw in raw_lines:
        if not isinstance(raw, dict):
            continue
        try:
            confidence = float(raw.get("confidence") or 0.0)
        except (TypeError, ValueError):
            continue
        if confidence < min_confidence:
            continue
        if _line_mid_y_in_plan(raw, plan_bbox):
            high_conf_plan += 1
        elif _line_has_geometry(raw):
            profile_only += 1

    if line_count == 0:
        return MasterSheetLineInventory(
            drawing_id=drawing_id,
            page=page,
            graph_present=True,
            line_count=0,
            plan_viewport_count=plan_viewport_count,
            high_conf_plan_line_count=0,
            profile_only_line_count=0,
            is_placable=False,
            blocker_code=MASTER_SHEET_GRAPH_MISSING,
            blocker_message=(
                f"Sheet graph on master drawing {drawing_id} page {page} has no lines "
                f"(digitization may have failed or been skipped)"
            ),
        )

    if high_conf_plan == 0:
        detail = (
            f"master drawing {drawing_id} page {page}: "
            f"lines={line_count}, plan_viewports={plan_viewport_count}, "
            f"high_conf_plan_lines=0, profile_band_lines={profile_only}"
        )
        if plan_viewport_count == 0 and profile_only > 0:
            detail += " (lines appear outside plan viewport — check viewport seeding)"
        return MasterSheetLineInventory(
            drawing_id=drawing_id,
            page=page,
            graph_present=True,
            line_count=line_count,
            plan_viewport_count=plan_viewport_count,
            high_conf_plan_line_count=0,
            profile_only_line_count=profile_only,
            is_placable=False,
            blocker_code=MASTER_SHEET_LINES_NOT_PLACABLE,
            blocker_message=detail,
        )

    return MasterSheetLineInventory(
        drawing_id=drawing_id,
        page=page,
        graph_present=True,
        line_count=line_count,
        plan_viewport_count=plan_viewport_count,
        high_conf_plan_line_count=high_conf_plan,
        profile_only_line_count=profile_only,
        is_placable=True,
        blocker_code=None,
        blocker_message=None,
    )


def placement_failure_from_inventory(
    inventory: MasterSheetLineInventory,
) -> tuple[str, str] | None:
    if inventory.is_placable:
        return None
    code = inventory.blocker_code or MASTER_SHEET_LINES_NOT_PLACABLE
    message = inventory.blocker_message or "No placable master sheet lines"
    return code, message


def _empty_inventory(
    *,
    drawing_id: int,
    page: int,
    code: str,
    message: str,
) -> MasterSheetLineInventory:
    return MasterSheetLineInventory(
        drawing_id=drawing_id,
        page=page,
        graph_present=False,
        line_count=0,
        plan_viewport_count=0,
        high_conf_plan_line_count=0,
        profile_only_line_count=0,
        is_placable=False,
        blocker_code=code,
        blocker_message=message,
    )


def _plan_viewport_bbox(page_graph: dict[str, Any]) -> tuple[float, float, float, float] | None:
    for vp in page_graph.get("viewports") or []:
        if not isinstance(vp, dict) or vp.get("kind") != "plan":
            continue
        bb = vp.get("bbox_fractional")
        if isinstance(bb, (list, tuple)) and len(bb) == 4:
            return tuple(float(v) for v in bb)
    return None


def _line_has_geometry(raw: dict[str, Any]) -> bool:
    points_raw = raw.get("points")
    return isinstance(points_raw, (list, tuple)) and len(points_raw) >= 2


def _line_mid_y_in_plan(
    raw: dict[str, Any],
    plan_bbox: tuple[float, float, float, float] | None,
) -> bool:
    points_raw = raw.get("points")
    if not isinstance(points_raw, (list, tuple)) or len(points_raw) < 2:
        return False
    ys: list[float] = []
    for pt in points_raw:
        if isinstance(pt, (list, tuple)) and len(pt) >= 2:
            ys.append(float(pt[1]))
    if not ys:
        return False
    mid_y = sum(ys) / len(ys)
    if plan_bbox is not None:
        return plan_bbox[1] <= mid_y <= plan_bbox[3]
    return _PLAN_VIEW_MIN_Y <= mid_y <= _PLAN_VIEW_MAX_Y
