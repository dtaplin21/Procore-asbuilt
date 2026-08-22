"""Tests for location-match evaluation (PR-G step G-3)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from ai.pipelines.drawing_location_resolver import ResolutionMethod
from ai.pipelines.location_match_orchestrator import LocationMatchResult
from models.location_match_label import LocationMatchLabel
from services.inspection_match_persistence import MATCH_SCORE_THRESHOLD
from services.location_match_eval import (
    EvalLabel,
    endpoint_error_norm,
    evaluate_label_result,
    evaluate_labels,
    hausdorff_distance_norm,
    is_coordinate_false_positive,
    path_overlap_ratio,
    rect_iou,
)


def _label(**overrides: object) -> EvalLabel:
    base = {
        "label_id": "test-label",
        "suite": "test",
        "project_id": 2,
        "evidence_id": 357,
        "inspection_run_id": 435,
        "master_drawing_id": 661,
        "evidence_fixture_path": None,
        "master_bbox_json": {
            "type": "rect",
            "page": 1,
            "x": 0.5,
            "y": 0.5,
            "width": 0.1,
            "height": 0.1,
        },
        "expected_method": "coordinate_lookup",
        "expected_match_status": "matched",
        "rotation_deg": 180,
        "has_coordinate_signal": True,
        "has_station_signal": False,
        "has_reference_signal": True,
        "evidence_kind": "form",
        "notes": None,
    }
    base.update(overrides)
    return EvalLabel(**base)  # type: ignore[arg-type]


def test_rect_iou_identical_rects() -> None:
    rect = (0.5, 0.5, 0.1, 0.1)
    assert rect_iou(rect, rect) == pytest.approx(1.0)


def test_rect_iou_disjoint_rects() -> None:
    assert rect_iou((0.0, 0.0, 0.1, 0.1), (0.5, 0.5, 0.1, 0.1)) == 0.0


def test_path_overlap_ratio_identical_polyline() -> None:
    line = [[0.51, 0.47], [0.54, 0.48], [0.56, 0.49]]
    assert path_overlap_ratio(line, line) == pytest.approx(1.0)


def test_endpoint_error_norm_identical_polyline() -> None:
    line = [[0.51, 0.47], [0.54, 0.48], [0.56, 0.49]]
    assert endpoint_error_norm(line, line) == pytest.approx(0.0)


def test_hausdorff_distance_norm_identical_polyline() -> None:
    line = [[0.51, 0.47], [0.54, 0.48], [0.56, 0.49]]
    assert hausdorff_distance_norm(line, line) == pytest.approx(0.0)


def test_evaluate_label_result_polyline_passes_on_overlap_and_endpoints() -> None:
    truth = {
        "type": "polyline",
        "page": 1,
        "points": [[0.51, 0.47], [0.54, 0.48], [0.56, 0.49]],
        "scope_kind": "utility_line",
    }
    predicted = {
        "type": "polyline",
        "page": 1,
        "points": [[0.51, 0.47], [0.54, 0.48], [0.56, 0.49]],
    }
    label = _label(
        master_scope_geometry_json=truth,
        master_bbox_json={
            "type": "rect",
            "page": 1,
            "x": 0.51,
            "y": 0.47,
            "width": 0.05,
            "height": 0.02,
        },
    )
    result = LocationMatchResult(
        master_drawing_id=661,
        method=ResolutionMethod.COORDINATE_LOOKUP,
        confidence=MATCH_SCORE_THRESHOLD,
        bbox_fractional=(0.51, 0.47, 0.56, 0.49),
        page=1,
    )
    outcome = evaluate_label_result(
        label,
        result,
        "matched",
        min_iou=0.30,
        predicted_scope_geometry=predicted,
    )
    assert outcome.geometry_mode == "polyline"
    assert outcome.passed is True
    assert outcome.path_overlap == pytest.approx(1.0)
    assert outcome.endpoint_error == pytest.approx(0.0)


def test_evaluate_label_result_polyline_fails_when_endpoints_drift() -> None:
    truth = {
        "type": "polyline",
        "page": 1,
        "points": [[0.51, 0.47], [0.54, 0.48], [0.56, 0.49]],
    }
    predicted = {
        "type": "polyline",
        "page": 1,
        "points": [[0.40, 0.40], [0.43, 0.41], [0.46, 0.42]],
    }
    label = _label(master_scope_geometry_json=truth)
    result = LocationMatchResult(
        master_drawing_id=661,
        method=ResolutionMethod.COORDINATE_LOOKUP,
        confidence=MATCH_SCORE_THRESHOLD,
        bbox_fractional=(0.40, 0.40, 0.46, 0.42),
        page=1,
    )
    outcome = evaluate_label_result(
        label,
        result,
        "matched",
        min_iou=0.30,
        predicted_scope_geometry=predicted,
    )
    assert outcome.passed is False
    assert outcome.path_overlap is not None
    assert outcome.endpoint_error is not None
    assert outcome.endpoint_error > 0.03


def test_coordinate_false_positive_when_no_coord_signal() -> None:
    label = _label(has_coordinate_signal=False)
    result = LocationMatchResult(
        master_drawing_id=661,
        method=ResolutionMethod.COORDINATE_LOOKUP,
        confidence=0.95,
        bbox_fractional=(0.5, 0.5, 0.1, 0.1),
        page=1,
    )
    assert is_coordinate_false_positive(label, result, "matched") is True
    assert is_coordinate_false_positive(label, result, "no_match") is False


def test_evaluate_label_result_passes_on_method_status_and_iou() -> None:
    label = _label()
    result = LocationMatchResult(
        master_drawing_id=661,
        method=ResolutionMethod.COORDINATE_LOOKUP,
        confidence=MATCH_SCORE_THRESHOLD,
        # Orchestrator format: (x0, y0, x1, y1) matching label xywh 0.5/0.5/0.1/0.1
        bbox_fractional=(0.5, 0.5, 0.6, 0.6),
        page=1,
    )
    outcome = evaluate_label_result(label, result, "matched", min_iou=0.30)
    assert outcome.passed is True
    assert outcome.iou == pytest.approx(1.0)


def test_evaluate_label_result_zero_area_truth_skips_iou() -> None:
    label = _label(
        expected_method="unresolved",
        expected_match_status="no_match",
        has_coordinate_signal=False,
        master_bbox_json={
            "type": "rect",
            "page": 1,
            "x": 0.0,
            "y": 0.0,
            "width": 0.0,
            "height": 0.0,
        },
    )
    result = LocationMatchResult.unresolved(661)
    outcome = evaluate_label_result(label, result, "no_match", min_iou=0.30)
    assert outcome.passed is True
    assert outcome.iou is None


def test_evaluate_labels_fails_below_pass_rate(db_session) -> None:
    labels = [
        _label(label_id="pass"),
        _label(label_id="fail"),
    ]

    def fake_evaluate(session, label, *, min_iou):
        from services.location_match_eval import LabelEvalResult

        passed = label.label_id == "pass"
        return LabelEvalResult(
            label_id=label.label_id,
            suite=label.suite,
            passed=passed,
            expected_method=label.expected_method,
            actual_method="coordinate_lookup" if passed else "reference_lookup",
            expected_match_status=label.expected_match_status,
            actual_match_status="matched" if passed else "needs_review",
            min_iou=min_iou,
        )

    with patch("services.location_match_eval.evaluate_label", side_effect=fake_evaluate):
        summary = evaluate_labels(db_session, labels, min_pass_rate=0.80)

    assert summary.evaluated == 2
    assert summary.passed == 1
    assert summary.pass_rate == pytest.approx(0.5)
    assert summary.passed_gate is False
    assert summary.rect_pass_rate == pytest.approx(0.5)
    assert summary.pass_rate_by_suite["test"] == pytest.approx(0.5)


def test_geometry_pass_rates_split_rect_and_polyline(db_session) -> None:
    labels = [
        _label(label_id="rect-pass", suite="mixed"),
        _label(
            label_id="poly-pass",
            suite="mixed",
            master_scope_geometry_json={
                "type": "polyline",
                "page": 1,
                "points": [[0.51, 0.47], [0.56, 0.49]],
            },
        ),
    ]

    def fake_evaluate(session, label, *, min_iou):
        from services.location_match_eval import LabelEvalResult

        if label.label_id == "rect-pass":
            return LabelEvalResult(
                label_id=label.label_id,
                suite=label.suite,
                passed=True,
                geometry_mode="rect",
                min_iou=min_iou,
            )
        return LabelEvalResult(
            label_id=label.label_id,
            suite=label.suite,
            passed=False,
            geometry_mode="polyline",
            path_overlap=0.4,
            endpoint_error=0.05,
            min_iou=min_iou,
        )

    with patch("services.location_match_eval.evaluate_label", side_effect=fake_evaluate):
        summary = evaluate_labels(db_session, labels, min_pass_rate=0.80)

    assert summary.rect_evaluated == 1
    assert summary.rect_pass_rate == pytest.approx(1.0)
    assert summary.polyline_evaluated == 1
    assert summary.polyline_pass_rate == pytest.approx(0.0)
    assert summary.passed_gate is False


def test_pass_rate_by_suite_in_summary(db_session) -> None:
    labels = [
        _label(label_id="a-pass", suite="alpha"),
        _label(label_id="a-fail", suite="alpha"),
        _label(label_id="b-pass", suite="beta"),
    ]

    def fake_evaluate(session, label, *, min_iou):
        from services.location_match_eval import LabelEvalResult

        passed = "fail" not in label.label_id
        return LabelEvalResult(
            label_id=label.label_id,
            suite=label.suite,
            passed=passed,
            min_iou=min_iou,
        )

    with patch("services.location_match_eval.evaluate_label", side_effect=fake_evaluate):
        summary = evaluate_labels(db_session, labels, min_pass_rate=0.50)

    assert summary.pass_rate_by_suite["alpha"] == pytest.approx(0.5)
    assert summary.pass_rate_by_suite["beta"] == pytest.approx(1.0)
    assert "pass_rate_by_suite" in summary.to_dict()


def test_evaluate_labels_skips_fixture_only_rows(db_session) -> None:
    labels = [_label(label_id="fixture-only", evidence_id=None)]
    summary = evaluate_labels(db_session, labels)
    assert summary.total == 1
    assert summary.skipped == 1
    assert summary.evaluated == 0
    assert summary.pass_rate == 0.0
    assert summary.passed_gate is True


def test_location_match_eval_integration(db_session) -> None:
    seeded = db_session.query(LocationMatchLabel).count()
    if seeded < 5:
        pytest.skip(f"Need >= 5 labels seeded in DB, found {seeded}")

    runnable = (
        db_session.query(LocationMatchLabel)
        .filter(LocationMatchLabel.evidence_id.isnot(None))
        .count()
    )
    if runnable < 5:
        pytest.skip(
            f"Need >= 5 labels with evidence_id in DB, found {runnable}"
        )

    from services.location_match_eval import evaluate_labels, load_eval_labels_from_db

    summary = evaluate_labels(db_session, load_eval_labels_from_db(db_session))
    assert summary.total >= 5
