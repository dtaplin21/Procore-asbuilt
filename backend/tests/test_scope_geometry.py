"""Tests for scope geometry schema and validation (PR-E E-1)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

from ai.agents.evidence_dossier import (
    EvidenceDossier,
    ExpandedClue,
    MasterDrawingContext,
)
from ai.pipelines.evidence_kind_classifier import EvidenceKind
from ai.pipelines.scope_geometry import (
    ScopeGeometry,
    ScopeKind,
    bbox_intersects_page,
    bbox_to_scope_rect,
    clamp_fractional_bbox,
    infer_scope_kind,
    validate_scope_geometry,
)
from models.models import EvidenceRecord
from services.region_storage import validate_region_geometry


def test_scope_to_geometry_polyline_persistence_shape() -> None:
    from services.inspection_match_persistence import scope_to_geometry

    scope = ScopeGeometry(
        page=1,
        type="polyline",
        points=((0.41, 0.38), (0.43, 0.39), (0.45, 0.40)),
        scope_kind=ScopeKind.UTILITY_LINE,
        meta={"station_from": "12+50", "station_to": "12+85"},
    )

    geometry = scope_to_geometry(scope, page=1)

    assert geometry["type"] == "polyline"
    assert geometry["points"] == [[0.41, 0.38], [0.43, 0.39], [0.45, 0.40]]
    assert geometry["scope_kind"] == "utility_line"
    assert geometry["label"] == "inspection_match"
    assert geometry["meta"] == {"station_from": "12+50", "station_to": "12+85"}
    validate_scope_geometry(geometry)


def test_scope_to_geometry_falls_back_to_bbox_rect() -> None:
    from services.inspection_match_persistence import scope_to_geometry

    geometry = scope_to_geometry(
        None,
        fallback_bbox=(0.1, 0.2, 0.3, 0.4),
        page=2,
    )

    assert geometry["type"] == "rect"
    assert geometry["page"] == 2
    assert geometry["label"] == "inspection_match"


def _minimal_dossier(
    *,
    evidence_text: str = "",
    expanded_clues: tuple[ExpandedClue, ...] = (),
    survey_points_meta: tuple[dict[str, object], ...] = (),
    evidence_meta: dict[str, object] | None = None,
) -> EvidenceDossier:
    evidence = cast(
        EvidenceRecord,
        SimpleNamespace(id=1, project_id=2, meta=evidence_meta or {}),
    )
    master_context = MasterDrawingContext(
        master_drawing_id=661,
        regions=(),
        total_region_count=0,
        untagged_region_count=0,
        scoped_survey_points=(),
        candidate_tiles=(),
        legend_codes_near_candidates=(),
    )
    return EvidenceDossier(
        evidence_id=357,
        project_id=2,
        master_drawing_id=661,
        evidence=evidence,
        extraction=None,
        clues=(),
        expanded_clues=expanded_clues,
        evidence_text=evidence_text,
        base_text=evidence_text,
        evidence_kind=EvidenceKind.FORM,
        linked_attachments=(),
        auxiliary_drawings=(),
        photo_paths=(),
        survey_points_meta=survey_points_meta,
        master_context=master_context,
        investigation_meta={},
    )


def test_bbox_intersects_page_rejects_fully_off_page() -> None:
    assert bbox_intersects_page((0.2, 1.28, 0.24, 1.36)) is False
    assert bbox_intersects_page((0.2, 0.2, 0.4, 0.4)) is True


def test_clamp_fractional_bbox_pulls_off_page_coords_into_range() -> None:
    assert clamp_fractional_bbox((0.226, 1.277, 0.241, 1.362)) == (
        pytest.approx(0.226),
        pytest.approx(1.0),
        pytest.approx(0.241),
        pytest.approx(1.0),
    )


def test_bbox_to_scope_rect_clamps_off_page_anchor() -> None:
    scope = bbox_to_scope_rect(
        (0.226, 1.277, 0.241, 1.362),
        page=1,
        scope_kind=ScopeKind.POINT,
    )
    geometry = scope.to_geometry_json()
    assert geometry["y"] <= 1.0
    assert geometry["y"] + geometry["height"] <= 1.001


def test_scope_geometry_polyline_clamps_off_page_points() -> None:
    scope = ScopeGeometry(
        page=1,
        type="polyline",
        points=((0.2, 1.227), (0.25, 1.3)),
        scope_kind=ScopeKind.UTILITY_LINE,
    )
    geometry = scope.to_geometry_json()
    assert geometry["points"][0][1] == pytest.approx(1.0)
    assert geometry["points"][1][1] == pytest.approx(1.0)


def test_validate_scope_geometry_accepts_rect() -> None:
    validate_scope_geometry(
        {"type": "rect", "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4}
    )


def test_validate_scope_geometry_accepts_polygon() -> None:
    validate_scope_geometry(
        {
            "type": "polygon",
            "points": [[0.1, 0.2], [0.2, 0.3], [0.15, 0.4]],
        }
    )


def test_validate_scope_geometry_accepts_polyline() -> None:
    validate_scope_geometry(
        {
            "type": "polyline",
            "points": [[0.1, 0.2], [0.4, 0.5], [0.7, 0.8]],
        }
    )


def test_validate_scope_geometry_rejects_short_polyline() -> None:
    with pytest.raises(ValueError, match="at least 2 points"):
        validate_scope_geometry({"type": "polyline", "points": [[0.1, 0.2]]})


def test_validate_scope_geometry_rejects_out_of_range_point() -> None:
    with pytest.raises(ValueError, match="must be 0-1"):
        validate_scope_geometry(
            {
                "type": "polyline",
                "points": [[0.1, 0.2], [1.2, 0.5]],
            }
        )


def test_bbox_to_scope_rect_serializes_for_overlay() -> None:
    scope = bbox_to_scope_rect(
        (0.12, 0.18, 0.22, 0.28),
        page=1,
        scope_kind=ScopeKind.UTILITY_LINE,
    )
    geometry = scope.to_geometry_json()

    assert geometry["page"] == 1
    assert geometry["type"] == "rect"
    assert geometry["x"] == pytest.approx(0.12)
    assert geometry["y"] == pytest.approx(0.18)
    assert geometry["width"] == pytest.approx(0.10)
    assert geometry["height"] == pytest.approx(0.10)
    assert geometry["scope_kind"] == "utility_line"


def test_scope_geometry_polyline_roundtrip() -> None:
    scope = ScopeGeometry(
        page=1,
        type="polyline",
        points=((0.1, 0.2), (0.3, 0.4), (0.5, 0.6)),
        scope_kind=ScopeKind.UTILITY_LINE,
        meta={"source": "line_tracer"},
    )

    geometry = scope.to_geometry_json()

    assert geometry["type"] == "polyline"
    assert geometry["points"] == [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]
    assert geometry["scope_kind"] == "utility_line"
    assert geometry["meta"] == {"source": "line_tracer"}
    validate_scope_geometry(geometry)


def test_validate_region_geometry_accepts_polyline() -> None:
    validate_region_geometry(
        {
            "type": "polyline",
            "points": [[0.1, 0.2], [0.4, 0.5]],
        }
    )


def test_infer_scope_kind_ss_install_is_utility_line() -> None:
    dossier = _minimal_dossier(
        evidence_text=(
            "Underground Sanitary Sewer #1 lateral run from SSMH to connection point"
        ),
        expanded_clues=(
            ExpandedClue(
                original_value="33-Sanitary Sewerage",
                clue_type="trade",
                expanded_values=("SS", "SANITARY SEWER", "33-Sanitary Sewerage"),
                confidence=0.9,
            ),
        ),
    )

    assert infer_scope_kind(dossier) == ScopeKind.UTILITY_LINE


def test_infer_scope_kind_colo_corridor_without_linear_language() -> None:
    dossier = _minimal_dossier(
        evidence_text="Field inspection at COLO parking lot",
        expanded_clues=(
            ExpandedClue(
                original_value="COLO",
                clue_type="location_text",
                expanded_values=("COLO",),
                confidence=0.9,
            ),
        ),
    )

    assert infer_scope_kind(dossier) == ScopeKind.CORRIDOR


def test_infer_scope_kind_coord_only_is_point() -> None:
    dossier = _minimal_dossier(
        evidence_text="Inspection observation at noted coordinates",
        survey_points_meta=(
            {
                "page": 1,
                "northing": 2131764.84,
                "easting": 6051541.82,
                "station": "12+50",
            },
        ),
    )

    assert infer_scope_kind(dossier) == ScopeKind.POINT


def test_infer_scope_kind_station_range_without_linear_language() -> None:
    dossier = _minimal_dossier(
        evidence_text="Observation between stations",
        evidence_meta={"station_from": "10+00", "station_to": "11+50"},
    )

    assert infer_scope_kind(dossier) == ScopeKind.STATION_RANGE


def test_infer_scope_kind_station_range_with_sewer_language_is_utility_line() -> None:
    dossier = _minimal_dossier(
        evidence_text="Sanitary sewer work from station 10+00 to 11+50",
        evidence_meta={"station_from": "10+00", "station_to": "11+50"},
    )

    assert infer_scope_kind(dossier) == ScopeKind.UTILITY_LINE
