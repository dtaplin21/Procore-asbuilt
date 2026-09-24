"""Tests for DrawingLegendLineType name matching."""

from __future__ import annotations

from typing import cast

from scripts.seed_legend_reference import seed
from services.legend_lookup import match_line_type_by_name


def test_match_line_type_by_name_exact(db_session, project) -> None:
    seed(db_session, project_id=None)
    project_id = cast(int, project.id)

    row = match_line_type_by_name(
        db_session,
        "Sanitary Sewer Main",
        project_id=project_id,
    )

    assert row is not None
    assert str(row.line_type_name) == "Sanitary Sewer Main"
