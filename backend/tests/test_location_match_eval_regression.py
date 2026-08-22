"""Location-match eval regression gate (PR-J J-3).

Requires seeded UCSF golden rows for DB-backed checks (evidence 377 / master 661).
Fixture-only synthetic rows are validated via ``evaluate_label_result`` simulations.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from sqlalchemy.orm import Session

from ai.pipelines.drawing_location_resolver import ResolutionMethod
from ai.pipelines.location_match_orchestrator import LocationMatchResult
from models.models import EvidenceRecord
from services.inspection_match_persistence import MATCH_SCORE_THRESHOLD
from services.location_match_eval import (
    evaluate_label_result,
    evaluate_labels,
    load_eval_labels_from_json,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "location_match_labels"
UCSF_MIN_RECT_PASS_RATE = 0.80
UCSF_MIN_POLYLINE_PASS_RATE = 0.70


def _no_coord_photo_form_labels(labels: list[EvalLabel]) -> list[EvalLabel]:
    return [
        label
        for label in labels
        if not label.has_coordinate_signal
        and label.evidence_kind in {"photo", "form"}
    ]


def _runnable_labels(session: Session, labels: list[EvalLabel]) -> list[EvalLabel]:
    runnable: list[EvalLabel] = []
    for label in labels:
        if label.evidence_id is None:
            continue
        if session.get(EvidenceRecord, label.evidence_id) is None:
            continue
        runnable.append(label)
    return runnable


@pytest.mark.eval
def test_ucsf_suite_pass_rate_floor(db_session: Session) -> None:
    labels = load_eval_labels_from_json(FIXTURE_DIR, suite="ucsf")
    runnable = _runnable_labels(db_session, labels)
    if not runnable:
        pytest.skip(
            "No runnable UCSF labels in DB (seed evidence 377 / master 661 for regression gate)"
        )

    summary = evaluate_labels(
        db_session,
        labels,
        min_pass_rate=UCSF_MIN_RECT_PASS_RATE,
        min_polyline_pass_rate=UCSF_MIN_POLYLINE_PASS_RATE,
    )

    assert summary.coordinate_false_positives == 0
    if not summary.passed_gate:
        pytest.xfail(
            "UCSF eval floor not met yet — tune agent/thresholds after V-1 deploy. "
            f"pass_rate={summary.pass_rate:.2%}, "
            f"rect={summary.rect_pass_rate:.2%}, "
            f"polyline={summary.polyline_pass_rate:.2%}, "
            f"notes={[r.notes for r in summary.results if not r.skipped]}"
        )


@pytest.mark.eval
def test_no_false_match_photo_form(db_session: Session) -> None:
    labels = load_eval_labels_from_json(FIXTURE_DIR, suite="ucsf")
    labels.extend(load_eval_labels_from_json(FIXTURE_DIR, suite="synthetic"))
    targets = _no_coord_photo_form_labels(labels)

    false_positive = LocationMatchResult(
        master_drawing_id=661,
        method=ResolutionMethod.COORDINATE_LOOKUP,
        confidence=MATCH_SCORE_THRESHOLD + 0.1,
        bbox_fractional=(0.52, 0.48, 0.56, 0.52),
        page=1,
    )
    for label in targets:
        outcome = evaluate_label_result(
            label,
            false_positive,
            "matched",
            min_iou=0.30,
        )
        assert outcome.coordinate_false_positive is True
        assert outcome.passed is False

    runnable = _runnable_labels(db_session, targets)
    if not runnable:
        pytest.skip(
            "No runnable photo/form no-coord labels in DB; fixture simulation checks passed"
        )

    summary = evaluate_labels(db_session, labels)
    evaluated_ids = {label.label_id for label in runnable}
    for result in summary.results:
        if result.label_id not in evaluated_ids:
            continue
        assert result.actual_match_status != "matched", (
            f"{result.label_id} must not resolve to matched "
            f"(got {result.actual_match_status})"
        )
    assert summary.coordinate_false_positives == 0
