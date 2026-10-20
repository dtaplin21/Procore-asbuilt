"""Tests for master sheet line placement inventory."""

from __future__ import annotations

from typing import cast

from models.models import Drawing
from services.inspection_placement_errors import (
    MASTER_SHEET_GRAPH_MISSING,
    MASTER_SHEET_LINES_NOT_PLACABLE,
)
from services.master_sheet_line_inventory import (
    get_master_sheet_line_inventory,
    inventory_from_index_stats,
)
from services.storage import StorageService


def _placable_stats(*, drawing_id: int = 1) -> dict:
    return {
        "sheetEntityGraph": {
            "1": {
                "drawing_id": drawing_id,
                "page": 1,
                "viewports": [
                    {
                        "viewport_id": "plan",
                        "kind": "plan",
                        "bbox_fractional": [0.05, 0.05, 0.95, 0.55],
                    }
                ],
                "lines": [
                    {
                        "points": [[0.2, 0.3], [0.8, 0.35]],
                        "confidence": 0.85,
                    }
                ],
            }
        }
    }


def _profile_only_stats() -> dict:
    return {
        "sheetEntityGraph": {
            "1": {
                "viewports": [{"viewport_id": "prof", "kind": "profile"}],
                "lines": [
                    {
                        "points": [[0.2, 0.75], [0.8, 0.78]],
                        "confidence": 0.9,
                    }
                ],
            }
        }
    }


def test_inventory_missing_graph(db_session, project) -> None:
    storage = StorageService(db_session)
    drawing = storage.create_drawing(
        project_id=cast(int, project.id),
        source="upload",
        name="Master.pdf",
        storage_key="projects/1/drawings/m.pdf",
        content_type="application/pdf",
    )
    row = db_session.get(Drawing, cast(int, drawing.id))
    assert row is not None
    setattr(row, "index_status", "ready")
    setattr(row, "index_stats_json", {})
    db_session.commit()

    inv = get_master_sheet_line_inventory(db_session, cast(int, drawing.id))

    assert inv.graph_present is False
    assert inv.is_placable is False
    assert inv.blocker_code == MASTER_SHEET_GRAPH_MISSING


def test_inventory_placable_plan_line() -> None:
    inv = inventory_from_index_stats(_placable_stats(), drawing_id=99, page=1)

    assert inv.is_placable is True
    assert inv.high_conf_plan_line_count == 1
    assert inv.blocker_code is None


def test_inventory_profile_lines_not_placable() -> None:
    inv = inventory_from_index_stats(_profile_only_stats(), drawing_id=99, page=1)

    assert inv.is_placable is False
    assert inv.blocker_code == MASTER_SHEET_LINES_NOT_PLACABLE
    assert inv.profile_only_line_count == 1
