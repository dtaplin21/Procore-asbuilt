"""Tests for location_match_orchestrator selection and status helpers."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy.orm import Session

from ai.pipelines.drawing_location_resolver import RegistrationTransform, ResolutionMethod
from ai.pipelines.location_match_orchestrator import (
    LocationMatchResult,
    MethodCandidate,
    _ScopedSurveyPoint,
    _coordinate_lookup_candidates,
    _enrich_evidence_stations,
    _project_aux_bbox_to_master,
    match_status_from_result,
    select_best_location_match,
)
from ai.pipelines.survey_point_extractor import SurveyPointRecord
from models.models import Drawing
from services.inspection_match_persistence import MATCH_SCORE_THRESHOLD
from services.storage import StorageService


def _survey_point(*, station: str | None = None) -> SurveyPointRecord:
    return SurveyPointRecord(
        page=1,
        northing=2131764.84,
        easting=6051541.82,
        station=station,
        structure_label=None,
        label_bbox_json={"x0": 0.0, "y0": 0.0, "x1": 0.01, "y1": 0.01},
        northing_bbox_json=None,
        easting_bbox_json=None,
        ocr_confidence=0.9,
        meta_json={},
    )


def test_enrich_evidence_stations_from_clue_text() -> None:
    clues = [
        SimpleNamespace(clue_value="SSMH, STA. 10+90.95", value=None),
    ]
    enriched = _enrich_evidence_stations(
        [_survey_point(station=None)],
        clues=clues,
        evidence_text="",
    )
    assert len(enriched) == 1
    assert enriched[0].station == "10+90.95"


def test_enrich_evidence_stations_keeps_existing_station() -> None:
    clues = [SimpleNamespace(clue_value="STA. 11+00.00", value=None)]
    enriched = _enrich_evidence_stations(
        [_survey_point(station="10+90.95")],
        clues=clues,
        evidence_text="STA. 11+00.00",
    )
    assert enriched[0].station == "10+90.95"


def test_select_best_location_match_picks_highest_confidence() -> None:
    candidates = [
        MethodCandidate(
            method=ResolutionMethod.REFERENCE_LOOKUP,
            confidence=0.80,
            bbox_fractional=(0.1, 0.1, 0.2, 0.2),
        ),
        MethodCandidate(
            method=ResolutionMethod.COORDINATE_LOOKUP,
            confidence=0.96,
            bbox_fractional=(0.3, 0.3, 0.4, 0.4),
        ),
    ]
    winner = select_best_location_match(candidates)
    assert winner is not None
    assert winner.method == ResolutionMethod.COORDINATE_LOOKUP


def test_select_best_location_match_tiebreaks_by_method_priority_within_epsilon() -> None:
    candidates = [
        MethodCandidate(
            method=ResolutionMethod.REFERENCE_LOOKUP,
            confidence=0.960,
            bbox_fractional=(0.1, 0.1, 0.2, 0.2),
        ),
        MethodCandidate(
            method=ResolutionMethod.COORDINATE_LOOKUP,
            confidence=0.955,
            bbox_fractional=(0.3, 0.3, 0.4, 0.4),
        ),
    ]
    winner = select_best_location_match(candidates)
    assert winner is not None
    assert winner.method == ResolutionMethod.COORDINATE_LOOKUP


def test_select_best_location_match_ignores_candidates_without_bbox() -> None:
    candidates = [
        MethodCandidate(
            method=ResolutionMethod.REFERENCE_LOOKUP,
            confidence=0.99,
            bbox_fractional=None,
        ),
        MethodCandidate(
            method=ResolutionMethod.STATION_LOOKUP,
            confidence=0.70,
            bbox_fractional=(0.1, 0.1, 0.2, 0.2),
        ),
    ]
    winner = select_best_location_match(candidates)
    assert winner is not None
    assert winner.method == ResolutionMethod.STATION_LOOKUP


def test_match_status_from_result_contour_always_needs_review() -> None:
    result = LocationMatchResult(
        master_drawing_id=661,
        method=ResolutionMethod.CONTOUR_MATCH,
        confidence=0.99,
        bbox_fractional=(0.1, 0.1, 0.2, 0.2),
        page=1,
    )
    assert match_status_from_result(result) == "needs_review"


def test_match_status_from_result_coordinate_matched_at_threshold() -> None:
    result = LocationMatchResult(
        master_drawing_id=661,
        method=ResolutionMethod.COORDINATE_LOOKUP,
        confidence=MATCH_SCORE_THRESHOLD,
        bbox_fractional=(0.1, 0.1, 0.2, 0.2),
        page=1,
    )
    assert match_status_from_result(result) == "matched"


def test_match_status_from_result_unresolved_is_no_match() -> None:
    result = LocationMatchResult.unresolved(661)
    assert match_status_from_result(result) == "no_match"


def test_project_aux_bbox_to_master_applies_registration_transform(
    db_session: Session,
    project,
) -> None:
    storage = StorageService(db_session)
    master = storage.create_drawing(
        project_id=cast(int, project.id),
        source="upload",
        name="Master.pdf",
        storage_key="drawings/master.pdf",
        content_type="application/pdf",
    )
    aux = Drawing(
        project_id=project.id,
        source="linked_evidence",
        name="Install.pdf",
        storage_key="linked/install.pdf",
        content_type="application/pdf",
    )
    db_session.add(aux)
    db_session.commit()

    aux_point = _ScopedSurveyPoint(
        drawing_id=cast(int, aux.id),
        page=1,
        northing=2131764.84,
        easting=6051541.82,
        station=None,
        structure_label=None,
        label_bbox_json={"x0": 0.10, "y0": 0.20, "x1": 0.14, "y1": 0.24},
        ocr_confidence=0.95,
    )
    transform = RegistrationTransform(
        scale_x=1.0,
        scale_y=1.0,
        translate_x=0.05,
        translate_y=0.05,
        rotation_degrees=0.0,
    )

    projected = _project_aux_bbox_to_master(
        db_session,
        aux_point=aux_point,
        master_drawing_id=cast(int, master.id),
        registration_transform=transform,
    )

    assert projected == pytest.approx((0.15, 0.25, 0.19, 0.29))


def test_coordinate_lookup_marks_aux_unprojected_without_transform(
    db_session: Session,
    project,
) -> None:
    storage = StorageService(db_session)
    master = storage.create_drawing(
        project_id=cast(int, project.id),
        source="upload",
        name="Master.pdf",
        storage_key="drawings/master.pdf",
        content_type="application/pdf",
    )
    aux = Drawing(
        project_id=project.id,
        source="linked_evidence",
        name="Install.pdf",
        storage_key="linked/install.pdf",
        content_type="application/pdf",
    )
    db_session.add(aux)
    db_session.commit()

    label_bbox = {"x0": 0.12, "y0": 0.18, "x1": 0.18, "y1": 0.22}
    northing = 2131764.84
    easting = 6051541.82
    evidence_points = [
        SurveyPointRecord(
            page=1,
            northing=northing,
            easting=easting,
            station=None,
            structure_label=None,
            label_bbox_json=label_bbox,
            northing_bbox_json=None,
            easting_bbox_json=None,
            ocr_confidence=0.9,
            meta_json={},
        )
    ]
    scoped_points = [
        _ScopedSurveyPoint(
            drawing_id=cast(int, aux.id),
            page=1,
            northing=northing,
            easting=easting,
            station=None,
            structure_label=None,
            label_bbox_json=label_bbox,
            ocr_confidence=0.95,
        )
    ]

    candidates = _coordinate_lookup_candidates(
        db_session,
        evidence_points=evidence_points,
        scoped_points=scoped_points,
        master_drawing_id=cast(int, master.id),
        registration_transform=None,
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.method == ResolutionMethod.COORDINATE_LOOKUP
    assert candidate.bbox_fractional is None
    assert "aux_coords_unprojected" in candidate.notes
    assert candidate.source_drawing_id == cast(int, aux.id)


def test_coordinate_lookup_projects_aux_match_with_registration_transform(
    db_session: Session,
    project,
) -> None:
    storage = StorageService(db_session)
    master = storage.create_drawing(
        project_id=cast(int, project.id),
        source="upload",
        name="Master.pdf",
        storage_key="drawings/master.pdf",
        content_type="application/pdf",
    )
    aux = Drawing(
        project_id=project.id,
        source="linked_evidence",
        name="Install.pdf",
        storage_key="linked/install.pdf",
        content_type="application/pdf",
    )
    db_session.add(aux)
    db_session.commit()

    label_bbox = {"x0": 0.10, "y0": 0.20, "x1": 0.14, "y1": 0.24}
    northing = 2131764.84
    easting = 6051541.82
    evidence_points = [
        SurveyPointRecord(
            page=1,
            northing=northing,
            easting=easting,
            station=None,
            structure_label=None,
            label_bbox_json=label_bbox,
            northing_bbox_json=None,
            easting_bbox_json=None,
            ocr_confidence=0.9,
            meta_json={},
        )
    ]
    scoped_points = [
        _ScopedSurveyPoint(
            drawing_id=cast(int, aux.id),
            page=1,
            northing=northing,
            easting=easting,
            station=None,
            structure_label=None,
            label_bbox_json=label_bbox,
            ocr_confidence=0.95,
        )
    ]
    transform = RegistrationTransform(
        scale_x=1.0,
        scale_y=1.0,
        translate_x=0.0,
        translate_y=0.0,
        rotation_degrees=0.0,
    )

    candidates = _coordinate_lookup_candidates(
        db_session,
        evidence_points=evidence_points,
        scoped_points=scoped_points,
        master_drawing_id=cast(int, master.id),
        registration_transform=transform,
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.bbox_fractional == pytest.approx((0.10, 0.20, 0.14, 0.24))
    assert candidate.source_drawing_id == cast(int, aux.id)
    assert "projected from auxiliary" in candidate.notes
