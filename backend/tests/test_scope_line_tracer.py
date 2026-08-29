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
from ai.pipelines.survey_point_extractor import SurveyPointRecord
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
    scoped_survey_points: tuple[SurveyPointRecord, ...] = (),
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
            scoped_survey_points=scoped_survey_points,
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


def test_trace_utility_line_uses_aux_survey_chain_when_station_range_present() -> None:
    anchor = (0.10, 0.20, 0.50, 0.40)
    scoped_points = (
        SurveyPointRecord(
            page=1,
            northing=2_131_704.56,
            easting=6_051_547.82,
            station="10+00",
            structure_label=None,
            label_bbox_json={"x0": 0.08, "y0": 0.18, "x1": 0.12, "y1": 0.22},
            northing_bbox_json=None,
            easting_bbox_json=None,
            ocr_confidence=0.9,
            meta_json={"drawing_id": 1084},
        ),
        SurveyPointRecord(
            page=1,
            northing=2_131_705.56,
            easting=6_051_483.28,
            station="10+71",
            structure_label=None,
            label_bbox_json={"x0": 0.18, "y0": 0.19, "x1": 0.22, "y1": 0.23},
            northing_bbox_json=None,
            easting_bbox_json=None,
            ocr_confidence=0.9,
            meta_json={"drawing_id": 1084},
        ),
        SurveyPointRecord(
            page=1,
            northing=2_131_764.84,
            easting=6_051_541.82,
            station="10+90.95",
            structure_label=None,
            label_bbox_json={"x0": 0.27, "y0": 0.26, "x1": 0.31, "y1": 0.28},
            northing_bbox_json=None,
            easting_bbox_json=None,
            ocr_confidence=0.9,
            meta_json={"drawing_id": 1084},
        ),
    )
    dossier = _dossier(
        evidence_text="7/20-7/24 Trench and Install Sanitary Sewer Lines",
        evidence_meta={"station_from": "10+00", "station_to": "10+90.95"},
        scoped_survey_points=scoped_points,
    )

    scope = trace_scope_geometry(
        dossier,
        anchor_bbox=anchor,
        scope_kind=ScopeKind.UTILITY_LINE,
        page=1,
    )

    assert scope.type == "polyline"
    assert scope.points is not None
    assert len(scope.points) >= 3
    assert scope.points[0][0] < scope.points[-1][0]
    assert scope.meta is not None
    assert scope.meta.get("source") == "aux_survey_chain"
    assert scope.meta.get("source_drawing_id") == 1084


def test_trace_station_range_uses_aux_tokens_when_source_drawing_differs(
    db_session,
    project,
) -> None:
    from models.drawing_text_element import DrawingTextElement
    from models.models import Drawing

    project_id = cast(int, project.id)
    aux = Drawing(
        project_id=project_id,
        source="linked_evidence",
        name="c4-20.pdf",
        content_type="application/pdf",
        processing_status="ready",
        index_status="ready",
    )
    db_session.add(aux)
    db_session.flush()
    aux_id = cast(int, aux.id)

    db_session.add_all(
        [
            DrawingTextElement(
                master_drawing_id=aux_id,
                page=1,
                text="SAN STA 10+00",
                text_normalized="san sta 10+00",
                bbox_json={"x0": 0.08, "y0": 0.18, "x1": 0.12, "y1": 0.22},
                source="tesseract",
            ),
            DrawingTextElement(
                master_drawing_id=aux_id,
                page=1,
                text="10+90.95",
                text_normalized="10+90.95",
                bbox_json={"x0": 0.27, "y0": 0.26, "x1": 0.31, "y1": 0.28},
                source="tesseract",
            ),
        ]
    )
    db_session.commit()

    anchor = (0.10, 0.20, 0.50, 0.40)
    dossier = _dossier(
        evidence_meta={"station_from": "10+00", "station_to": "10+90.95"},
        tiles=(),
    )

    scope = trace_scope_geometry(
        dossier,
        anchor_bbox=anchor,
        scope_kind=ScopeKind.STATION_RANGE,
        page=1,
        session=db_session,
        source_drawing_id=aux_id,
    )

    assert scope.type == "polyline"
    assert scope.points is not None
    assert len(scope.points) == 2
    assert scope.points[0][0] < scope.points[1][0]
    assert scope.meta is not None
    assert scope.meta.get("source") == "aux_plan_station_labels"
    assert scope.meta.get("source_drawing_id") == aux_id


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


def test_trace_utility_line_prefers_plan_sheet_line_over_vision(
    db_session,
    project,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from dataclasses import replace

    from models.models import Drawing
    from sqlalchemy.orm import Session

    session = cast(Session, db_session)
    master = Drawing(
        project_id=cast(int, project.id),
        source="upload",
        name="Master.pdf",
        content_type="application/pdf",
        processing_status="ready",
        index_status="ready",
        index_stats_json={
            "sheetEntityGraph": {
                "1": {
                    "drawing_id": 0,
                    "page": 1,
                    "viewports": [
                        {
                            "viewport_id": "plan",
                            "kind": "plan",
                            "page": 1,
                            "bbox_fractional": [0.05, 0.05, 0.95, 0.55],
                            "scale": None,
                            "source": "manual",
                            "notes": "",
                        },
                        {
                            "viewport_id": "section_a",
                            "kind": "section",
                            "page": 1,
                            "bbox_fractional": [0.05, 0.60, 0.95, 0.95],
                            "scale": None,
                            "source": "manual",
                            "notes": "",
                        },
                    ],
                    "labels": [],
                    "symbols": [],
                    "lines": [
                        {
                            "points": [[0.20, 0.25], [0.45, 0.30]],
                            "viewport_id": "plan",
                            "confidence": 0.85,
                            "line_type": None,
                        },
                        {
                            "points": [[0.20, 0.70], [0.45, 0.75]],
                            "viewport_id": "section_a",
                            "confidence": 0.99,
                            "line_type": None,
                        },
                    ],
                    "associations": [],
                    "meta": {},
                }
            }
        },
    )
    session.add(master)
    session.commit()
    master_id = cast(int, master.id)

    master_png = tmp_path / "master.png"
    master_png.write_bytes(b"\x89PNG\r\n\x1a\n")

    def fake_reason(**kwargs: object) -> object:
        raise AssertionError("vision must not run when plan SheetLine is available")

    monkeypatch.setattr(
        "ai.pipelines.vision_location_reasoner.reason_over_master_crop",
        fake_reason,
    )

    dossier = replace(
        _dossier(
            evidence_text="Sanitary sewer lateral run in corridor",
            tiles=(
                _tile(text="ROOF", bbox=(0.80, 0.80, 0.84, 0.82), text_element_id=3),
            ),
        ),
        master_drawing_id=master_id,
    )

    scope = trace_scope_geometry(
        dossier,
        anchor_bbox=(0.18, 0.22, 0.48, 0.35),
        scope_kind=ScopeKind.UTILITY_LINE,
        page=1,
        session=session,
        master_png_path=master_png,
    )

    assert scope.meta is not None
    assert scope.meta.get("source") == "sheet_line"
    assert scope.meta.get("viewport_id") == "plan"
    assert scope.points == ((0.20, 0.25), (0.45, 0.30))
