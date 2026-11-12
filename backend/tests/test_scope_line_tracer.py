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
from ai.pipelines.scope_line_tracer import (
    LONG_LINE_FRAC,
    resolve_master_sheet_line_scope,
    suspect_line_reason,
    trace_scope_geometry,
)
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
        reasoning_text=evidence_text,
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

    assert scope.type == "line_segments"
    assert scope.segments is not None
    assert len(scope.segments) == 1
    start, end = scope.segments[0]
    assert start[0] < end[0]
    assert start[0] == pytest.approx(0.14)
    assert start[1] == pytest.approx(0.23)
    assert end[0] == pytest.approx(0.40)
    assert end[1] == pytest.approx(0.31)
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

    assert scope.type == "line_segments"
    assert scope.segments is not None
    assert len(scope.segments) >= 1
    assert scope.segments[0][0][0] < scope.segments[-1][1][0]
    assert scope.meta is not None
    assert "SS" in scope.meta.get("legend_codes", [])


def test_trace_utility_line_skips_aux_survey_chain_when_station_range_present() -> None:
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

    assert scope.type == "line_segments"
    assert scope.meta is not None
    assert scope.meta.get("source") != "aux_survey_chain"
    assert scope.meta.get("source") in {
        "utility_line_trace",
        "anchor_centerline_fallback",
        "vision_trace",
    }


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

    assert scope.type == "line_segments"
    assert scope.segments is not None
    assert len(scope.segments) == 1
    assert scope.segments[0][0][0] < scope.segments[0][1][0]
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
    for segment in geometry["segments"]:
        for point in segment:
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
    for segment in geometry["segments"]:
        for point in segment:
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
                            "points": [[0.25, 0.27], [0.41, 0.30]],
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

    from ai.pipelines.vision_location_reasoner import _empty_vision_result

    monkeypatch.setattr(
        "ai.pipelines.vision_location_reasoner.reason_over_master_crop",
        lambda **kwargs: _empty_vision_result(),
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
    assert scope.segments == (((0.25, 0.27), (0.41, 0.30)),)


def test_trace_utility_line_skips_mismatched_typed_sheet_line(
    db_session,
    project,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from dataclasses import replace

    from models.legend_reference import DrawingLegendLineType
    from models.models import Drawing
    from scripts.seed_legend_reference import seed
    from sqlalchemy.orm import Session

    session = cast(Session, db_session)
    seed(session, project_id=None)
    ss_row = (
        session.query(DrawingLegendLineType)
        .filter(DrawingLegendLineType.line_type_name == "Sanitary Sewer Main")
        .one()
    )
    water_row = (
        session.query(DrawingLegendLineType)
        .filter(DrawingLegendLineType.line_type_name == "Water Main")
        .one()
    )

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
                        }
                    ],
                    "labels": [],
                    "symbols": [],
                    "lines": [
                        {
                            "points": [[0.25, 0.27], [0.41, 0.30]],
                            "viewport_id": "plan",
                            "confidence": 0.95,
                            "line_type": "Water Main",
                            "legend_line_type_id": cast(int, water_row.id),
                            "source": "pdf_vector",
                        },
                        {
                            "points": [[0.19, 0.24], [0.44, 0.29]],
                            "viewport_id": "plan",
                            "confidence": 0.85,
                            "line_type": "Sanitary Sewer Main",
                            "legend_line_type_id": cast(int, ss_row.id),
                            "source": "pdf_vector",
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

    from ai.pipelines.vision_location_reasoner import _empty_vision_result

    monkeypatch.setattr(
        "ai.pipelines.vision_location_reasoner.reason_over_master_crop",
        lambda **kwargs: _empty_vision_result(),
    )

    dossier = replace(
        _dossier(
            evidence_text="Sanitary sewer lateral run in corridor",
            tiles=(
                _tile(text="ROOF", bbox=(0.80, 0.80, 0.84, 0.82), text_element_id=3),
            ),
            legend_codes=("SS",),
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
    assert scope.segments == (((0.19, 0.24), (0.44, 0.29)),)


def test_trace_utility_line_prefers_typed_over_untyped_sheet_line(
    db_session,
    project,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from dataclasses import replace

    from models.legend_reference import DrawingLegendLineType
    from models.models import Drawing
    from scripts.seed_legend_reference import seed
    from sqlalchemy.orm import Session

    session = cast(Session, db_session)
    seed(session, project_id=None)
    ss_row = (
        session.query(DrawingLegendLineType)
        .filter(DrawingLegendLineType.line_type_name == "Sanitary Sewer Main")
        .one()
    )

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
                        }
                    ],
                    "labels": [],
                    "symbols": [],
                    "lines": [
                        {
                            "points": [[0.25, 0.27], [0.41, 0.30]],
                            "viewport_id": "plan",
                            "confidence": 0.95,
                            "line_type": None,
                        },
                        {
                            "points": [[0.19, 0.24], [0.44, 0.29]],
                            "viewport_id": "plan",
                            "confidence": 0.85,
                            "line_type": "Sanitary Sewer Main",
                            "legend_line_type_id": cast(int, ss_row.id),
                            "source": "pdf_vector",
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

    from ai.pipelines.vision_location_reasoner import _empty_vision_result

    monkeypatch.setattr(
        "ai.pipelines.vision_location_reasoner.reason_over_master_crop",
        lambda **kwargs: _empty_vision_result(),
    )

    dossier = replace(
        _dossier(
            evidence_text="Sanitary sewer lateral run in corridor",
            tiles=(
                _tile(text="ROOF", bbox=(0.80, 0.80, 0.84, 0.82), text_element_id=3),
            ),
            legend_codes=("SS",),
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

    assert scope.segments == (((0.19, 0.24), (0.44, 0.29)),)


def test_resolve_master_sheet_line_strict_requires_anchor_intersection(
    db_session,
    project,
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
                        }
                    ],
                    "labels": [],
                    "symbols": [],
                    "lines": [
                        {
                            "points": [[0.80, 0.08], [0.69, 0.73]],
                            "viewport_id": "plan",
                            "confidence": 0.9,
                            "line_type": None,
                        },
                        {
                            "points": [[0.25, 0.27], [0.41, 0.30]],
                            "viewport_id": "plan",
                            "confidence": 0.85,
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

    dossier = replace(
        _dossier(
            evidence_text="Sanitary sewer",
            tiles=(),
            legend_codes=("SS",),
        ),
        master_drawing_id=master_id,
    )
    anchor = (0.18, 0.22, 0.48, 0.35)

    scope = resolve_master_sheet_line_scope(
        session,
        dossier=dossier,
        master_drawing_id=master_id,
        page=1,
        anchor_bbox=anchor,
        strict=True,
    )
    assert scope.meta is not None
    assert scope.meta.get("anchor_intersects_line") is True
    assert scope.segments == (((0.25, 0.27), (0.41, 0.30)),)

    # Pin sits outside the plan viewport, so the plan lines are not searched.
    far_anchor = (0.02, 0.02, 0.05, 0.05)
    with pytest.raises(ValueError, match="outside every viewport"):
        resolve_master_sheet_line_scope(
            session,
            dossier=dossier,
            master_drawing_id=master_id,
            page=1,
            anchor_bbox=far_anchor,
            strict=True,
        )

    # Inside the plan, but neither line comes within tolerance of the point.
    missed_anchor = (0.10, 0.40, 0.14, 0.44)
    with pytest.raises(ValueError, match="INSPECTION_NO_ANCHOR_INTERSECTING_LINE"):
        resolve_master_sheet_line_scope(
            session,
            dossier=dossier,
            master_drawing_id=master_id,
            page=1,
            anchor_bbox=missed_anchor,
            strict=True,
        )


def test_resolve_master_sheet_line_non_strict_rejects_line_that_misses_anchor(
    db_session,
    project,
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
                        }
                    ],
                    "labels": [],
                    "symbols": [],
                    "lines": [
                        {
                            "points": [[0.80, 0.08], [0.69, 0.73]],
                            "viewport_id": "plan",
                            "confidence": 0.9,
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

    dossier = replace(
        _dossier(evidence_text="Sanitary sewer", tiles=(), legend_codes=("SS",)),
        master_drawing_id=master_id,
    )

    with pytest.raises(ValueError, match="outside every viewport"):
        resolve_master_sheet_line_scope(
            session,
            dossier=dossier,
            master_drawing_id=master_id,
            page=1,
            anchor_bbox=(0.02, 0.02, 0.05, 0.05),
            strict=False,
        )


def _sheet(
    *,
    viewports: list[dict],
    lines: list[dict],
) -> dict:
    return {
        "sheetEntityGraph": {
            "1": {
                "drawing_id": 0,
                "page": 1,
                "viewports": viewports,
                "labels": [],
                "symbols": [],
                "lines": lines,
                "associations": [],
                "meta": {},
            }
        }
    }


def test_profile_station_searches_the_profile_viewport(db_session, project) -> None:
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
        index_stats_json=_sheet(
            viewports=[
                {
                    "viewport_id": "plan",
                    "kind": "plan",
                    "page": 1,
                    "bbox_fractional": [0.05, 0.08, 0.80, 0.42],
                    "scale": None,
                    "source": "manual",
                    "notes": "",
                },
                {
                    "viewport_id": "profile",
                    "kind": "profile",
                    "page": 1,
                    "bbox_fractional": [0.03, 0.45, 0.82, 0.94],
                    "scale": None,
                    "source": "manual",
                    "notes": "",
                },
            ],
            lines=[
                {
                    "points": [[0.20, 0.20], [0.50, 0.24]],
                    "viewport_id": "plan",
                    "confidence": 0.99,
                    "line_type": "SS",
                },
                {
                    "points": [[0.26, 0.80], [0.35, 0.81]],
                    "viewport_id": "profile",
                    "confidence": 0.8,
                    "line_type": "SS",
                },
                {
                    "points": [
                        [0.036, 0.017],
                        [0.905, 0.017],
                        [0.905, 0.983],
                        [0.036, 0.983],
                        [0.036, 0.017],
                    ],
                    "viewport_id": None,
                    "confidence": 0.95,
                    "line_type": "dashed",
                },
            ],
        ),
    )
    session.add(master)
    session.commit()
    master_id = cast(int, master.id)
    dossier = replace(
        _dossier(evidence_text="Sanitary sewer", tiles=(), legend_codes=("SS",)),
        master_drawing_id=master_id,
    )

    scope = resolve_master_sheet_line_scope(
        session,
        dossier=dossier,
        master_drawing_id=master_id,
        page=1,
        anchor_bbox=(0.28, 0.79, 0.32, 0.82),
        strict=False,
    )

    assert scope.segments == (((0.26, 0.80), (0.35, 0.81)),)
    assert scope.meta is not None
    assert scope.meta.get("search_viewport_kind") == "profile"
    assert scope.meta.get("search_region") == "viewport"
    assert scope.meta.get("anchor_intersects_line") is True


def test_single_letter_legend_code_does_not_match_dashed(db_session, project) -> None:
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
        index_stats_json=_sheet(
            viewports=[
                {
                    "viewport_id": "profile",
                    "kind": "profile",
                    "page": 1,
                    "bbox_fractional": [0.03, 0.45, 0.82, 0.94],
                    "scale": None,
                    "source": "manual",
                    "notes": "",
                }
            ],
            lines=[
                {
                    "points": [[0.10, 0.80], [0.60, 0.80]],
                    "viewport_id": "profile",
                    "confidence": 0.99,
                    "line_type": "dashed",
                },
                {
                    "points": [[0.22, 0.80], [0.38, 0.80]],
                    "viewport_id": "profile",
                    "confidence": 0.8,
                    "line_type": "SS",
                },
            ],
        ),
    )
    session.add(master)
    session.commit()
    master_id = cast(int, master.id)
    dossier = replace(
        _dossier(
            evidence_text="Sanitary sewer",
            tiles=(),
            legend_codes=("S", "A", "D", "E", "SS"),
        ),
        master_drawing_id=master_id,
    )

    scope = resolve_master_sheet_line_scope(
        session,
        dossier=dossier,
        master_drawing_id=master_id,
        page=1,
        anchor_bbox=(0.29, 0.79, 0.31, 0.81),
        strict=False,
    )

    assert scope.segments == (((0.22, 0.80), (0.38, 0.80)),)


def test_padded_box_corner_does_not_count_as_touching(db_session, project) -> None:
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
        index_stats_json=_sheet(
            viewports=[
                {
                    "viewport_id": "plan",
                    "kind": "plan",
                    "page": 1,
                    "bbox_fractional": [0.0, 0.0, 1.0, 1.0],
                    "scale": None,
                    "source": "manual",
                    "notes": "",
                }
            ],
            lines=[
                {
                    "points": [[0.80, 0.063], [0.90, 0.063]],
                    "viewport_id": "plan",
                    "confidence": 0.9,
                    "line_type": None,
                }
            ],
        ),
    )
    session.add(master)
    session.commit()
    master_id = cast(int, master.id)
    dossier = replace(
        _dossier(evidence_text="Sanitary sewer", tiles=(), legend_codes=("SS",)),
        master_drawing_id=master_id,
    )

    # Expanded by 0.05 this box contains the border corner (0.905, 0.017).
    # The closest border segment is still farther than the touch tolerance.
    with pytest.raises(ValueError, match="INSPECTION_NO_ANCHOR_INTERSECTING_LINE"):
        resolve_master_sheet_line_scope(
            session,
            dossier=dossier,
            master_drawing_id=master_id,
            page=1,
            anchor_bbox=(0.849, 0.029, 0.862, 0.051),
            strict=False,
        )


def test_fixed_y_band_is_recorded_when_no_viewport_exists(db_session, project) -> None:
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
        index_stats_json=_sheet(
            viewports=[],
            lines=[
                {
                    "points": [[0.20, 0.30], [0.40, 0.32]],
                    "viewport_id": None,
                    "confidence": 0.9,
                    "line_type": None,
                },
                {
                    "points": [[0.20, 0.80], [0.40, 0.82]],
                    "viewport_id": None,
                    "confidence": 0.99,
                    "line_type": None,
                },
            ],
        ),
    )
    session.add(master)
    session.commit()
    master_id = cast(int, master.id)
    dossier = replace(
        _dossier(evidence_text="Sanitary sewer", tiles=(), legend_codes=("SS",)),
        master_drawing_id=master_id,
    )

    scope = resolve_master_sheet_line_scope(
        session,
        dossier=dossier,
        master_drawing_id=master_id,
        page=1,
        anchor_bbox=(0.28, 0.29, 0.32, 0.33),
        strict=False,
    )

    assert scope.segments == (((0.20, 0.30), (0.40, 0.32)),)
    assert scope.meta is not None
    assert scope.meta.get("search_region") == "fixed_y_band"
    assert "fixed y band" in str(scope.meta.get("search_region_note"))


def test_segment_that_ends_on_the_anchor_point_counts(db_session, project) -> None:
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
        index_stats_json=_sheet(
            viewports=[
                {
                    "viewport_id": "profile",
                    "kind": "profile",
                    "page": 1,
                    "bbox_fractional": [0.03, 0.45, 0.82, 0.94],
                    "scale": None,
                    "source": "manual",
                    "notes": "",
                }
            ],
            lines=[
                {
                    "points": [[0.20, 0.80], [0.30, 0.80]],
                    "viewport_id": "profile",
                    "confidence": 0.9,
                    "line_type": None,
                }
            ],
        ),
    )
    session.add(master)
    session.commit()
    master_id = cast(int, master.id)
    dossier = replace(
        _dossier(evidence_text="Sanitary sewer", tiles=(), legend_codes=("SS",)),
        master_drawing_id=master_id,
    )

    scope = resolve_master_sheet_line_scope(
        session,
        dossier=dossier,
        master_drawing_id=master_id,
        page=1,
        anchor_bbox=(0.29, 0.79, 0.31, 0.81),
        strict=True,
    )

    assert scope.meta is not None
    assert scope.meta.get("anchor_intersects_line") is True
    assert scope.segments == (((0.20, 0.80), (0.30, 0.80)),)


_AUDITED_SHEET_BORDER = [
    [0.036, 0.017],
    [0.905, 0.017],
    [0.905, 0.983],
    [0.036, 0.983],
    [0.036, 0.017],
]


def test_audited_sheet_border_is_a_suspect_line() -> None:
    points = [(x, y) for x, y in _AUDITED_SHEET_BORDER]
    assert suspect_line_reason(points, explicitly_requested=False) == "sheet_border"
    assert suspect_line_reason(points, explicitly_requested=True) == "sheet_border"

    on_edges = [
        (0.02, 0.02),
        (0.20, 0.02),
        (0.20, 0.15),
        (0.02, 0.15),
        (0.02, 0.02),
    ]
    assert suspect_line_reason(on_edges, explicitly_requested=False) == "sheet_border"

    long_line = [(0.10, 0.50), (0.10 + LONG_LINE_FRAC + 0.01, 0.50)]
    assert suspect_line_reason(long_line, explicitly_requested=False) == "long_line"
    assert suspect_line_reason(long_line, explicitly_requested=True) is None

    short_line = [(0.20, 0.50), (0.35, 0.50)]
    assert suspect_line_reason(short_line, explicitly_requested=False) is None


def test_sheet_border_is_not_traced_when_the_anchor_lies_on_it(db_session, project) -> None:
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
        index_stats_json=_sheet(
            viewports=[
                {
                    "viewport_id": "plan",
                    "kind": "plan",
                    "page": 1,
                    "bbox_fractional": [0.0, 0.0, 1.0, 1.0],
                    "scale": None,
                    "source": "manual",
                    "notes": "",
                }
            ],
            lines=[
                {
                    "points": _AUDITED_SHEET_BORDER,
                    "viewport_id": "plan",
                    "confidence": 0.99,
                    "line_type": None,
                },
                {
                    "points": [[0.40, 0.50], [0.55, 0.50]],
                    "viewport_id": "plan",
                    "confidence": 0.8,
                    "line_type": "SS",
                },
            ],
        ),
    )
    session.add(master)
    session.commit()
    master_id = cast(int, master.id)
    dossier = replace(
        _dossier(evidence_text="Sanitary sewer", tiles=(), legend_codes=("SS",)),
        master_drawing_id=master_id,
    )

    # Anchor sits on the border's top edge. The border must not be the match.
    with pytest.raises(ValueError, match="INSPECTION_NO_ANCHOR_INTERSECTING_LINE"):
        resolve_master_sheet_line_scope(
            session,
            dossier=dossier,
            master_drawing_id=master_id,
            page=1,
            anchor_bbox=(0.39, 0.007, 0.41, 0.027),
            strict=False,
        )


def test_long_line_is_kept_only_when_its_type_was_requested(db_session, project) -> None:
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
        index_stats_json=_sheet(
            viewports=[
                {
                    "viewport_id": "plan",
                    "kind": "plan",
                    "page": 1,
                    "bbox_fractional": [0.0, 0.0, 1.0, 1.0],
                    "scale": None,
                    "source": "manual",
                    "notes": "",
                }
            ],
            lines=[
                {
                    "points": [[0.10, 0.50], [0.70, 0.50]],
                    "viewport_id": "plan",
                    "confidence": 0.99,
                    "line_type": None,
                },
                {
                    "points": [[0.40, 0.50], [0.55, 0.50]],
                    "viewport_id": "plan",
                    "confidence": 0.8,
                    "line_type": "SS",
                },
            ],
        ),
    )
    session.add(master)
    session.commit()
    master_id = cast(int, master.id)
    dossier = replace(
        _dossier(evidence_text="Sanitary sewer", tiles=(), legend_codes=("SS",)),
        master_drawing_id=master_id,
    )

    scope = resolve_master_sheet_line_scope(
        session,
        dossier=dossier,
        master_drawing_id=master_id,
        page=1,
        anchor_bbox=(0.44, 0.49, 0.48, 0.51),
        strict=False,
    )

    assert scope.segments == (((0.40, 0.50), (0.55, 0.50)),)

    long_only = Drawing(
        project_id=cast(int, project.id),
        source="upload",
        name="Master.pdf",
        content_type="application/pdf",
        processing_status="ready",
        index_status="ready",
        index_stats_json=_sheet(
            viewports=[
                {
                    "viewport_id": "plan",
                    "kind": "plan",
                    "page": 1,
                    "bbox_fractional": [0.0, 0.0, 1.0, 1.0],
                    "scale": None,
                    "source": "manual",
                    "notes": "",
                }
            ],
            lines=[
                {
                    "points": [[0.10, 0.50], [0.70, 0.50]],
                    "viewport_id": "plan",
                    "confidence": 0.9,
                    "line_type": "SS",
                }
            ],
        ),
    )
    session.add(long_only)
    session.commit()
    long_id = cast(int, long_only.id)
    long_dossier = replace(dossier, master_drawing_id=long_id)
    long_scope = resolve_master_sheet_line_scope(
        session,
        dossier=long_dossier,
        master_drawing_id=long_id,
        page=1,
        anchor_bbox=(0.44, 0.49, 0.48, 0.51),
        strict=False,
    )
    assert long_scope.segments == (((0.10, 0.50), (0.70, 0.50)),)
