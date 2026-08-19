"""Location-match evaluation helpers for multi-suite eval labels."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, cast

from sqlalchemy.orm import Session

from ai.pipelines.drawing_location_resolver import ResolutionMethod
from ai.pipelines.location_match_orchestrator import (
    LocationMatchResult,
    match_status_from_result,
    resolve_evidence_location,
)
from models.location_match_label import LocationMatchLabel
from services.location_match_label_io import load_fixture_path, validate_entry


@dataclass(frozen=True)
class EvalLabel:
    label_id: str
    suite: str
    project_id: int
    evidence_id: int | None
    inspection_run_id: int | None
    master_drawing_id: int
    evidence_fixture_path: str | None
    master_bbox_json: dict[str, Any]
    expected_method: str
    expected_match_status: str
    rotation_deg: int | None
    has_coordinate_signal: bool
    has_station_signal: bool
    has_reference_signal: bool
    evidence_kind: str
    notes: str | None = None


@dataclass
class LabelEvalResult:
    label_id: str
    suite: str = ""
    skipped: bool = False
    skip_reason: str | None = None
    passed: bool = False
    expected_method: str = ""
    actual_method: str | None = None
    expected_match_status: str = ""
    actual_match_status: str | None = None
    iou: float | None = None
    min_iou: float = 0.30
    coordinate_false_positive: bool = False
    notes: str = ""


@dataclass
class EvalSummary:
    total: int
    evaluated: int
    skipped: int
    passed: int
    failed: int
    pass_rate: float
    min_pass_rate: float
    min_iou: float
    coordinate_false_positives: int
    passed_gate: bool
    pass_rate_by_suite: dict[str, float] = field(default_factory=dict)
    results: list[LabelEvalResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["results"] = [asdict(result) for result in self.results]
        return payload


def eval_label_from_json(entry: dict[str, Any]) -> EvalLabel:
    return EvalLabel(
        label_id=str(entry["label_id"]),
        suite=str(entry["suite"]).strip(),
        project_id=int(entry["project_id"]),
        evidence_id=int(entry["evidence_id"]) if entry.get("evidence_id") is not None else None,
        inspection_run_id=(
            int(entry["inspection_run_id"])
            if entry.get("inspection_run_id") is not None
            else None
        ),
        master_drawing_id=int(entry["master_drawing_id"]),
        evidence_fixture_path=cast(str | None, entry.get("evidence_fixture_path")),
        master_bbox_json=dict(entry["master_bbox_json"]),
        expected_method=str(entry["expected_method"]),
        expected_match_status=str(entry["expected_match_status"]),
        rotation_deg=(
            int(entry["rotation_deg"]) if entry.get("rotation_deg") is not None else None
        ),
        has_coordinate_signal=bool(entry["has_coordinate_signal"]),
        has_station_signal=bool(entry["has_station_signal"]),
        has_reference_signal=bool(entry["has_reference_signal"]),
        evidence_kind=str(entry["evidence_kind"]),
        notes=cast(str | None, entry.get("notes")),
    )


def eval_label_from_row(row: LocationMatchLabel) -> EvalLabel:
    return EvalLabel(
        label_id=cast(str, row.label_id),
        suite=cast(str, row.suite),
        project_id=cast(int, row.project_id),
        evidence_id=cast(int | None, row.evidence_id),
        inspection_run_id=cast(int | None, row.inspection_run_id),
        master_drawing_id=cast(int, row.master_drawing_id),
        evidence_fixture_path=cast(str | None, row.evidence_fixture_path),
        master_bbox_json=(
            dict(row.master_bbox_json)
            if isinstance(row.master_bbox_json, dict)
            else {}
        ),
        expected_method=cast(str, row.expected_method),
        expected_match_status=cast(str, row.expected_match_status),
        rotation_deg=cast(int | None, row.rotation_deg),
        has_coordinate_signal=bool(row.has_coordinate_signal),
        has_station_signal=bool(row.has_station_signal),
        has_reference_signal=bool(row.has_reference_signal),
        evidence_kind=cast(str, row.evidence_kind),
        notes=cast(str | None, row.notes),
    )


def filter_eval_labels(
    labels: list[EvalLabel],
    *,
    suite: str | None = None,
    project_id: int | None = None,
) -> list[EvalLabel]:
    filtered = labels
    if suite is not None:
        filtered = [label for label in filtered if label.suite == suite]
    if project_id is not None:
        filtered = [label for label in filtered if label.project_id == project_id]
    return filtered


def load_eval_labels_from_json(
    fixture_path: str | Path,
    *,
    suite: str | None = None,
    project_id: int | None = None,
) -> list[EvalLabel]:
    path = Path(fixture_path)
    entries = load_fixture_path(path, suite=suite)
    labels: list[EvalLabel] = []
    for index, entry in enumerate(entries):
        validate_entry(entry, index)
        labels.append(eval_label_from_json(entry))
    return filter_eval_labels(labels, suite=suite, project_id=project_id)


def load_eval_labels_from_db(
    session: Session,
    *,
    suite: str | None = None,
    project_id: int | None = None,
) -> list[EvalLabel]:
    query = session.query(LocationMatchLabel)
    if suite is not None:
        query = query.filter(LocationMatchLabel.suite == suite)
    if project_id is not None:
        query = query.filter(LocationMatchLabel.project_id == project_id)
    rows = query.order_by(LocationMatchLabel.label_id.asc()).all()
    return [eval_label_from_row(row) for row in rows]


def _rect_xywh_from_json(bbox_json: dict[str, Any]) -> tuple[float, float, float, float] | None:
    if bbox_json.get("type") != "rect":
        return None
    try:
        return (
            float(bbox_json["x"]),
            float(bbox_json["y"]),
            float(bbox_json["width"]),
            float(bbox_json["height"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def rect_iou(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    """Intersection-over-union for axis-aligned rects in (x, y, width, height) form."""
    lx0, ly0, lw, lh = left
    rx0, ry0, rw, rh = right
    lx1, ly1 = lx0 + lw, ly0 + lh
    rx1, ry1 = rx0 + rw, ry0 + rh

    ix0 = max(lx0, rx0)
    iy0 = max(ly0, ry0)
    ix1 = min(lx1, rx1)
    iy1 = min(ly1, ry1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0

    intersection = (ix1 - ix0) * (iy1 - iy0)
    union = (lw * lh) + (rw * rh) - intersection
    if union <= 0:
        return 0.0
    return intersection / union


def is_coordinate_false_positive(
    label: EvalLabel,
    result: LocationMatchResult,
    actual_status: str,
) -> bool:
    if label.has_coordinate_signal:
        return False
    if result.method not in (
        ResolutionMethod.COORDINATE_LOOKUP,
        ResolutionMethod.CONTOUR_MATCH,
    ):
        return False
    return actual_status != "no_match"


def evaluate_label_result(
    label: EvalLabel,
    result: LocationMatchResult,
    actual_status: str,
    *,
    min_iou: float,
) -> LabelEvalResult:
    outcome = LabelEvalResult(
        label_id=label.label_id,
        suite=label.suite,
        expected_method=label.expected_method,
        actual_method=result.method.value,
        expected_match_status=label.expected_match_status,
        actual_match_status=actual_status,
        min_iou=min_iou,
    )

    if is_coordinate_false_positive(label, result, actual_status):
        outcome.coordinate_false_positive = True
        outcome.passed = False
        outcome.notes = "Zero-coordinate label matched via coordinate/contour."
        return outcome

    method_ok = result.method.value == label.expected_method
    status_ok = actual_status == label.expected_match_status
    if not method_ok or not status_ok:
        outcome.passed = False
        parts: list[str] = []
        if not method_ok:
            parts.append(
                f"method expected {label.expected_method}, got {result.method.value}"
            )
        if not status_ok:
            parts.append(
                "status expected "
                f"{label.expected_match_status}, got {actual_status}"
            )
        outcome.notes = "; ".join(parts)
        return outcome

    truth_rect = _rect_xywh_from_json(label.master_bbox_json)
    if truth_rect is None:
        outcome.passed = False
        outcome.notes = "Invalid master_bbox_json ground truth."
        return outcome

    _tx, _ty, tw, th = truth_rect
    if tw <= 0 or th <= 0:
        outcome.passed = True
        outcome.notes = "Zero-area ground truth; method/status satisfied."
        return outcome

    if result.bbox_fractional is None:
        outcome.passed = False
        outcome.notes = "Expected bbox for IoU check but matcher returned none."
        return outcome

    outcome.iou = rect_iou(result.bbox_fractional, truth_rect)
    if outcome.iou >= min_iou:
        outcome.passed = True
        outcome.notes = f"IoU {outcome.iou:.3f} >= {min_iou:.2f}."
    else:
        outcome.passed = False
        outcome.notes = f"IoU {outcome.iou:.3f} < {min_iou:.2f}."
    return outcome


def evaluate_label(
    session: Session,
    label: EvalLabel,
    *,
    min_iou: float,
) -> LabelEvalResult:
    if label.evidence_id is None:
        return LabelEvalResult(
            label_id=label.label_id,
            suite=label.suite,
            skipped=True,
            skip_reason="missing evidence_id (fixture-only label)",
            expected_method=label.expected_method,
            expected_match_status=label.expected_match_status,
            min_iou=min_iou,
        )

    page_raw = label.master_bbox_json.get("page", 1)
    page = int(page_raw) if page_raw is not None else 1

    result = resolve_evidence_location(
        session,
        label.evidence_id,
        label.master_drawing_id,
        page=page,
    )
    actual_status = match_status_from_result(result)
    return evaluate_label_result(
        label,
        result,
        actual_status,
        min_iou=min_iou,
    )


def _pass_rate_by_suite(results: list[LabelEvalResult]) -> dict[str, float]:
    evaluated_by_suite: dict[str, list[LabelEvalResult]] = defaultdict(list)
    seen_suites: set[str] = set()
    for result in results:
        suite_name = result.suite or "default"
        seen_suites.add(suite_name)
        if result.skipped:
            continue
        evaluated_by_suite[suite_name].append(result)

    rates: dict[str, float] = {}
    for suite_name in sorted(seen_suites):
        suite_results = evaluated_by_suite.get(suite_name, [])
        if not suite_results:
            # All labels in this suite were skipped (fixture-only).
            rates[suite_name] = 1.0
            continue
        passed = sum(1 for result in suite_results if result.passed)
        rates[suite_name] = passed / len(suite_results)
    return rates


def evaluate_labels(
    session: Session,
    labels: list[EvalLabel],
    *,
    min_iou: float = 0.30,
    min_pass_rate: float = 0.80,
) -> EvalSummary:
    results: list[LabelEvalResult] = []
    for label in labels:
        results.append(evaluate_label(session, label, min_iou=min_iou))

    evaluated = [result for result in results if not result.skipped]
    passed = [result for result in evaluated if result.passed]
    failed = [result for result in evaluated if not result.passed]
    skipped = [result for result in results if result.skipped]
    coordinate_false_positives = sum(
        1 for result in evaluated if result.coordinate_false_positive
    )

    pass_rate = (len(passed) / len(evaluated)) if evaluated else 0.0
    # Fixture-only suites (all skipped) are not a gate failure.
    passed_gate = (
        True
        if not evaluated
        else (pass_rate >= min_pass_rate and coordinate_false_positives == 0)
    )

    return EvalSummary(
        total=len(labels),
        evaluated=len(evaluated),
        skipped=len(skipped),
        passed=len(passed),
        failed=len(failed),
        pass_rate=pass_rate,
        min_pass_rate=min_pass_rate,
        min_iou=min_iou,
        coordinate_false_positives=coordinate_false_positives,
        passed_gate=passed_gate,
        pass_rate_by_suite=_pass_rate_by_suite(results),
        results=results,
    )
