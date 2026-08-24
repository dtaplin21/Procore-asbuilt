"""Tests for scope line tracer (PR-E E-3)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

from ai.agents.evidence_dossier import (
    EvidenceDossier,
    ExpandedClue,
    MasterDrawingContext,
)
from ai.pipelines.candidate_tile_selector import CandidateTile
from ai.pipelines.document_text_extraction import BoundingBox
from ai.pipelines.drawing_location_resolver import MasterRegion
from ai.pipelines.evidence_kind_classifier import EvidenceKind
from ai.pipelines.scope_geometry import ScopeKind
from ai.pipelines.scope_line_tracer import trace_scope_geometry
from models.models import EvidenceRecord


def _bbox(x: float, y: float, w: float, h: float) -> BoundingBox:
    return BoundingBox(x=x, y=y, width=w, height=h, page_width=1.0, page_height=1.0)


def _tile(
    *,
    text: str,
    bbox: tuple[float, float, float, float],
    text_element_id: int,
) -> CandidateTile:
    return CandidateTile(
        drawing_id="661",
        page=1,
        text=text,
        confidence=0.9,
        bbox_normalized=bbox,
        text_element_id=text_element_id,
    )


def _dossier(
    *,
    evidence_text: str = "",
    evidence_meta: dict[str, object] | None = None,
    tiles: tuple[CandidateTile, ...] = (),
    regions: tuple[MasterRegion, ...] = (),
    legend_codes: tuple[str, ...] = ("SS",),
) -> EvidenceDossier:
    evidence = cast(
        EvidenceRecord,
        SimpleNamespace(id=357, project_id=2, meta=evidence_meta or {}),
    )
    return EvidenceDossier(
        evidence_id=357,
        project_id=2,
        master_drawing_id=661,
        evidence=evidence,
        extraction=None,
        clues=(),
        expanded_clues=(
            ExpandedClue(
                original_value="33-Sanitary Sewerage",
                clue_type="trade",
                expanded_values=("SS", "SANITARY SEWER"),
                confidence=0.9,
            ),
        ),
        evidence_text=evidence_text,
        base_text=evidence_text,
        evidence_kind=EvidenceKind.FORM,
        linked_attachments=(),
        auxiliary_drawings=(),
        photo_paths=(),
        survey_points_meta=(),
        master_context=MasterDrawingContext(
            master_drawing_id=661,
            regions=regions,
            total_region_count=len(regions),
            untagged_region_count=0,
            scoped_survey_points=(),
            candidate_tiles=tiles,
            legend_codes_near_candidates=legend_codes,
        ),
        investigation_meta={},
    )


def test_trace_station_range_connects_sta_label_centroids() -> None:
    anchor = (0.10, 0.20, 0.50, 0.40)
    dossier = _dossier(
        evidence_meta={"station_from": "10+00", "station_to": "11+00"},
        tiles=(
            _tile(text="STA. 10+00", bbox=(0.12, 0.22, 0.16, 0.24), text_element_id=1),
            _tile(text="STA. 11+00", bbox=(0.38, 0.30, 0.42, 0.32), text_element_id=2),
        ),
    )

    scope = trace_scope_geometry(
        dossier,
        anchor_bbox=anchor,
        scope_kind=ScopeKind.STATION_RANGE,
        page=1,
    )

    assert scope.type == "polyline"
    assert scope.points is not None
    assert len(scope.points) == 2
    assert scope.points[0][0] < scope.points[1][0]
    assert scope.points[0][0] == pytest.approx(0.14)
    assert scope.points[0][1] == pytest.approx(0.23)
    assert scope.points[1][0] == pytest.approx(0.40)
    assert scope.points[1][1] == pytest.approx(0.31)
    assert scope.meta is not None
    assert scope.meta.get("source") == "station_labels"


def test_trace_utility_line_uses_nearby_ss_labels() -> None:
    anchor = (0.10, 0.20, 0.50, 0.40)
    dossier = _dossier(
        evidence_text="Sanitary sewer lateral run in corridor",
        tiles=(
            _tile(text="SS-3", bbox=(0.14, 0.24, 0.18, 0.26), text_element_id=1),
            _tile(text="SS-4", bbox=(0.34, 0.28, 0.38, 0.30), text_element_id=2),
            _tile(text="ROOF", bbox=(0.80, 0.80, 0.84, 0.82), text_element_id=3),
        ),
    )

    scope = trace_scope_geometry(
        dossier,
        anchor_bbox=anchor,
        scope_kind=ScopeKind.UTILITY_LINE,
        page=1,
    )

    assert scope.type == "polyline"
    assert scope.points is not None
    assert len(scope.points) >= 2
    assert scope.points[0][0] < scope.points[-1][0]
    assert scope.meta is not None
    assert "SS" in scope.meta.get("legend_codes", [])


def test_trace_utility_line_clamps_centerline_when_anchor_is_off_page() -> None:
    off_page_anchor = (0.226, 1.277, 0.241, 1.362)
    dossier = _dossier(
        evidence_text="Sanitary sewer lateral run in corridor",
        tiles=(
            _tile(text="ROOF", bbox=(0.80, 0.80, 0.84, 0.82), text_element_id=3),
        ),
    )

    scope = trace_scope_geometry(
        dossier,
        anchor_bbox=off_page_anchor,
        scope_kind=ScopeKind.UTILITY_LINE,
        page=1,
    )

    geometry = scope.to_geometry_json()
    for point in geometry["points"]:
        assert 0.0 <= point[0] <= 1.0
        assert 0.0 <= point[1] <= 1.0


def test_trace_utility_line_clamps_vision_points_when_anchor_is_off_page(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from ai.pipelines.vision_location_reasoner import VisionLocationResult

    off_page_anchor = (0.226, 1.277, 0.241, 1.362)
    master_png = tmp_path / "master.png"
    master_png.write_bytes(b"\x89PNG\r\n\x1a\n")

    def fake_reason(**kwargs: object) -> VisionLocationResult:
        return VisionLocationResult(
            best_candidate_index=0,
            confidence=0.82,
            bbox_fractional=off_page_anchor,
            polyline_points=((0.23, 1.22), (0.24, 1.35)),
            highlight_detected=False,
            rationale="vision trace",
        )

    monkeypatch.setattr(
        "ai.pipelines.vision_location_reasoner.reason_over_master_crop",
        fake_reason,
    )

    dossier = _dossier(
        evidence_text="Sanitary sewer lateral run in corridor",
        tiles=(
            _tile(text="ROOF", bbox=(0.80, 0.80, 0.84, 0.82), text_element_id=3),
        ),
    )

    scope = trace_scope_geometry(
        dossier,
        anchor_bbox=off_page_anchor,
        scope_kind=ScopeKind.UTILITY_LINE,
        page=1,
        master_png_path=master_png,
    )

    assert scope.meta is not None
    assert scope.meta.get("source") == "vision_trace"
    geometry = scope.to_geometry_json()
    for point in geometry["points"]:
        assert 0.0 <= point[0] <= 1.0
        assert 0.0 <= point[1] <= 1.0
