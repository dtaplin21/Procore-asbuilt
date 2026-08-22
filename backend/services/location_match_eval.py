"""Location-match evaluation helpers for multi-suite eval labels."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from math import hypot
from pathlib import Path
from typing import Any, Sequence, cast

from sqlalchemy.orm import Session

from ai.pipelines.drawing_location_resolver import ResolutionMethod
from ai.pipelines.location_match_orchestrator import LocationMatchResult
from models.drawing_overlay import DrawingOverlay
from models.location_match_label import LocationMatchLabel
from models.models import EvidenceRecord
from services.inspection_match_persistence import (
    AgentMatchResult,
    resolve_inspection_run_id,
)
from services.location_match_label_io import load_fixture_path, validate_entry

MIN_PATH_OVERLAP = 0.70
MAX_ENDPOINT_ERROR = 0.03
DEFAULT_MIN_POLYLINE_PASS_RATE = 0.70

PolylinePoints = Sequence[Sequence[float]]


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
    master_scope_geometry_json: dict[str, Any] | None = None


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
    path_overlap: float | None = None
    min_path_overlap: float = MIN_PATH_OVERLAP
    endpoint_error: float | None = None
    max_endpoint_error: float = MAX_ENDPOINT_ERROR
    hausdorff_distance: float | None = None
    geometry_mode: str = "rect"
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
    min_path_overlap: float = MIN_PATH_OVERLAP
    min_polyline_pass_rate: float = DEFAULT_MIN_POLYLINE_PASS_RATE
    rect_evaluated: int = 0
    rect_passed: int = 0
    rect_pass_rate: float = 0.0
    polyline_evaluated: int = 0
    polyline_passed: int = 0
    polyline_pass_rate: float = 0.0
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
        master_scope_geometry_json=(
            dict(entry["master_scope_geometry_json"])
            if isinstance(entry.get("master_scope_geometry_json"), dict)
            else None
        ),
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
        master_scope_geometry_json=(
            dict(row.master_scope_geometry_json)
            if isinstance(row.master_scope_geometry_json, dict)
            else None
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


def xywh_from_xyxy(
    bbox: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    """Convert orchestrator ``(x0, y0, x1, y1)`` fractional bbox to ``(x, y, w, h)``."""
    x0, y0, x1, y1 = bbox
    return (x0, y0, max(x1 - x0, 0.0), max(y1 - y0, 0.0))


def _polyline_points(line: PolylinePoints) -> tuple[tuple[float, float], ...]:
    return tuple((float(point[0]), float(point[1])) for point in line)


def _euclidean(a: tuple[float, float], b: tuple[float, float]) -> float:
    return hypot(a[0] - b[0], a[1] - b[1])


def _point_to_segment_distance(
    px: float,
    py: float,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> float:
    dx = x1 - x0
    dy = y1 - y0
    if dx == 0.0 and dy == 0.0:
        return hypot(px - x0, py - y0)

    t = ((px - x0) * dx + (py - y0) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    proj_x = x0 + t * dx
    proj_y = y0 + t * dy
    return hypot(px - proj_x, py - proj_y)


def _point_to_polyline_distance(
    px: float,
    py: float,
    points: Sequence[tuple[float, float]],
) -> float:
    if len(points) < 2:
        if not points:
            return float("inf")
        return hypot(px - points[0][0], py - points[0][1])

    return min(
        _point_to_segment_distance(px, py, points[i][0], points[i][1], points[i + 1][0], points[i + 1][1])
        for i in range(len(points) - 1)
    )


def hausdorff_distance_norm(line_a: PolylinePoints, line_b: PolylinePoints) -> float:
    """Symmetric Hausdorff distance between polylines in normalized 0-1 space."""
    points_a = _polyline_points(line_a)
    points_b = _polyline_points(line_b)
    if len(points_a) < 2 or len(points_b) < 2:
        return float("inf")

    def directed(from_points: Sequence[tuple[float, float]], to_points: Sequence[tuple[float, float]]) -> float:
        return max(_point_to_polyline_distance(x, y, to_points) for x, y in from_points)

    return max(directed(points_a, points_b), directed(points_b, points_a))


def path_overlap_ratio(
    predicted: PolylinePoints,
    expected: PolylinePoints,
    *,
    tolerance: float = 0.02,
) -> float:
    """Fraction of expected polyline vertices covered by the predicted path."""
    expected_points = _polyline_points(expected)
    predicted_points = _polyline_points(predicted)
    if len(expected_points) < 2 or len(predicted_points) < 2:
        return 0.0

    covered = sum(
        1
        for x, y in expected_points
        if _point_to_polyline_distance(x, y, predicted_points) <= tolerance
    )
    return covered / len(expected_points)


def endpoint_error_norm(predicted: PolylinePoints, expected: PolylinePoints) -> float:
    """Endpoint alignment error, allowing reversed polyline orientation."""
    predicted_points = _polyline_points(predicted)
    expected_points = _polyline_points(expected)
    if len(predicted_points) < 2 or len(expected_points) < 2:
        return float("inf")

    forward = max(
        _euclidean(predicted_points[0], expected_points[0]),
        _euclidean(predicted_points[-1], expected_points[-1]),
    )
    reverse = max(
        _euclidean(predicted_points[0], expected_points[-1]),
        _euclidean(predicted_points[-1], expected_points[0]),
    )
    return min(forward, reverse)


def _scope_polyline_points(scope: dict[str, Any]) -> tuple[tuple[float, float], ...] | None:
    if scope.get("type") != "polyline":
        return None
    raw_points = scope.get("points")
    if not isinstance(raw_points, list) or len(raw_points) < 2:
        return None
    try:
        return _polyline_points(raw_points)
    except (IndexError, TypeError, ValueError):
        return None


def _predicted_scope_from_overlay(session: Session, label: EvalLabel) -> dict[str, Any] | None:
    run_id = label.inspection_run_id
    if run_id is None and label.evidence_id is not None:
        run_id = resolve_inspection_run_id(session, str(label.evidence_id))

    if run_id is None:
        return None

    overlay = (
        session.query(DrawingOverlay)
        .filter(
            DrawingOverlay.inspection_run_id == run_id,
            DrawingOverlay.master_drawing_id == label.master_drawing_id,
        )
        .order_by(DrawingOverlay.id.desc())
        .first()
    )
    if overlay is None or not isinstance(overlay.geometry, dict):
        return None
    return cast(dict[str, Any], overlay.geometry)


def _bbox_xyxy_from_agent_result(
    agent_result: AgentMatchResult,
) -> tuple[float, float, float, float] | None:
    scope = agent_result.scope
    if scope is not None:
        if (
            scope.type == "rect"
            and scope.x is not None
            and scope.y is not None
            and scope.width is not None
            and scope.height is not None
        ):
            return (
                scope.x,
                scope.y,
                scope.x + scope.width,
                scope.y + scope.height,
            )
        if scope.type == "polyline" and scope.points:
            xs = [point[0] for point in scope.points]
            ys = [point[1] for point in scope.points]
            return (min(xs), min(ys), max(xs), max(ys))

    return None


def _resolution_method_from_overlay(session: Session, label: EvalLabel) -> ResolutionMethod:
    run_id = label.inspection_run_id
    if run_id is None and label.evidence_id is not None:
        run_id = resolve_inspection_run_id(session, str(label.evidence_id))
    if run_id is None:
        return ResolutionMethod.UNRESOLVED

    overlay = (
        session.query(DrawingOverlay)
        .filter(
            DrawingOverlay.inspection_run_id == run_id,
            DrawingOverlay.master_drawing_id == label.master_drawing_id,
        )
        .order_by(DrawingOverlay.id.desc())
        .first()
    )
    if overlay is None or not isinstance(overlay.meta, dict):
        return ResolutionMethod.UNRESOLVED

    candidates = overlay.meta.get("agent_candidates")
    if isinstance(candidates, list) and candidates:
        first = candidates[0]
        if isinstance(first, dict):
            raw_method = first.get("method")
            if isinstance(raw_method, str):
                try:
                    return ResolutionMethod(raw_method)
                except ValueError:
                    pass

    return ResolutionMethod.UNRESOLVED


def _location_result_from_agent(
    session: Session,
    label: EvalLabel,
    agent_result: AgentMatchResult,
) -> LocationMatchResult:
    if agent_result.status in {"no_match", "index_pending"}:
        return LocationMatchResult.unresolved(label.master_drawing_id)

    method = _resolution_method_from_overlay(session, label)
    if method == ResolutionMethod.UNRESOLVED:
        method = ResolutionMethod.REFERENCE_LOOKUP

    return LocationMatchResult(
        master_drawing_id=label.master_drawing_id,
        method=method,
        confidence=float(agent_result.fused_score or 0.0),
        bbox_fractional=_bbox_xyxy_from_agent_result(agent_result),
        page=agent_result.page,
        region_id=agent_result.region_id,
        notes=agent_result.rationale,
    )


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
    predicted_scope_geometry: dict[str, Any] | None = None,
    min_path_overlap: float = MIN_PATH_OVERLAP,
    max_endpoint_error: float = MAX_ENDPOINT_ERROR,
) -> LabelEvalResult:
    truth_scope = label.master_scope_geometry_json
    truth_polyline = (
        _scope_polyline_points(truth_scope)
        if isinstance(truth_scope, dict)
        else None
    )
    geometry_mode = "polyline" if truth_polyline is not None else "rect"

    outcome = LabelEvalResult(
        label_id=label.label_id,
        suite=label.suite,
        expected_method=label.expected_method,
        actual_method=result.method.value,
        expected_match_status=label.expected_match_status,
        actual_match_status=actual_status,
        min_iou=min_iou,
        min_path_overlap=min_path_overlap,
        max_endpoint_error=max_endpoint_error,
        geometry_mode=geometry_mode,
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

    if truth_polyline is not None:
        predicted_scope = predicted_scope_geometry or {}
        predicted_polyline = _scope_polyline_points(predicted_scope)
        if predicted_polyline is None:
            outcome.passed = False
            outcome.notes = "Expected polyline prediction for path overlap check."
            return outcome

        outcome.path_overlap = path_overlap_ratio(predicted_polyline, truth_polyline)
        outcome.endpoint_error = endpoint_error_norm(predicted_polyline, truth_polyline)
        outcome.hausdorff_distance = hausdorff_distance_norm(predicted_polyline, truth_polyline)

        if (
            outcome.path_overlap >= min_path_overlap
            and outcome.endpoint_error <= max_endpoint_error
        ):
            outcome.passed = True
            outcome.notes = (
                f"path_overlap {outcome.path_overlap:.3f} >= {min_path_overlap:.2f}, "
                f"endpoint_error {outcome.endpoint_error:.3f} <= {max_endpoint_error:.2f}."
            )
        else:
            outcome.passed = False
            outcome.notes = (
                f"path_overlap {outcome.path_overlap:.3f} (min {min_path_overlap:.2f}), "
                f"endpoint_error {outcome.endpoint_error:.3f} (max {max_endpoint_error:.2f})."
            )
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

    # Orchestrator bboxes are (x0, y0, x1, y1); labels store (x, y, width, height).
    outcome.iou = rect_iou(xywh_from_xyxy(result.bbox_fractional), truth_rect)
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
        geometry_mode = (
            "polyline"
            if isinstance(label.master_scope_geometry_json, dict)
            and label.master_scope_geometry_json.get("type") == "polyline"
            else "rect"
        )
        return LabelEvalResult(
            label_id=label.label_id,
            suite=label.suite,
            skipped=True,
            skip_reason="missing evidence_id (fixture-only label)",
            expected_method=label.expected_method,
            expected_match_status=label.expected_match_status,
            min_iou=min_iou,
            geometry_mode=geometry_mode,
        )

    if session.get(EvidenceRecord, label.evidence_id) is None:
        return LabelEvalResult(
            label_id=label.label_id,
            suite=label.suite,
            skipped=True,
            skip_reason=f"evidence_id {label.evidence_id} not found in DB",
            expected_method=label.expected_method,
            expected_match_status=label.expected_match_status,
            min_iou=min_iou,
        )

    page_raw = label.master_bbox_json.get("page", 1)
    page = int(page_raw) if page_raw is not None else 1

    from ai.agents.inspection_location_agent import InspectionLocationAgent

    agent = InspectionLocationAgent()
    agent_result = agent.run(
        session,
        evidence_id=cast(int, label.evidence_id),
        master_drawing_id=label.master_drawing_id,
        page=page,
        inspection_run_id=label.inspection_run_id,
    )
    result = _location_result_from_agent(session, label, agent_result)
    actual_status = agent_result.status
    predicted_scope = (
        agent_result.scope.to_geometry_json()
        if agent_result.scope is not None
        else _predicted_scope_from_overlay(session, label)
    )
    return evaluate_label_result(
        label,
        result,
        actual_status,
        min_iou=min_iou,
        predicted_scope_geometry=predicted_scope,
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


def _geometry_pass_rates(
    results: list[LabelEvalResult],
) -> tuple[int, int, float, int, int, float]:
    rect_results = [
        result
        for result in results
        if not result.skipped and result.geometry_mode == "rect"
    ]
    polyline_results = [
        result
        for result in results
        if not result.skipped and result.geometry_mode == "polyline"
    ]

    rect_passed = sum(1 for result in rect_results if result.passed)
    polyline_passed = sum(1 for result in polyline_results if result.passed)

    rect_pass_rate = (rect_passed / len(rect_results)) if rect_results else 1.0
    polyline_pass_rate = (
        (polyline_passed / len(polyline_results)) if polyline_results else 1.0
    )
    return (
        len(rect_results),
        rect_passed,
        rect_pass_rate,
        len(polyline_results),
        polyline_passed,
        polyline_pass_rate,
    )


def evaluate_labels(
    session: Session,
    labels: list[EvalLabel],
    *,
    min_iou: float = 0.30,
    min_pass_rate: float = 0.80,
    min_path_overlap: float = MIN_PATH_OVERLAP,
    max_endpoint_error: float = MAX_ENDPOINT_ERROR,
    min_polyline_pass_rate: float = DEFAULT_MIN_POLYLINE_PASS_RATE,
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
    (
        rect_evaluated,
        rect_passed,
        rect_pass_rate,
        polyline_evaluated,
        polyline_passed,
        polyline_pass_rate,
    ) = _geometry_pass_rates(results)

    rect_gate_ok = rect_evaluated == 0 or rect_pass_rate >= min_pass_rate
    polyline_gate_ok = (
        polyline_evaluated == 0 or polyline_pass_rate >= min_polyline_pass_rate
    )
    passed_gate = (
        True
        if not evaluated
        else (
            rect_gate_ok
            and polyline_gate_ok
            and coordinate_false_positives == 0
        )
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
        min_path_overlap=min_path_overlap,
        min_polyline_pass_rate=min_polyline_pass_rate,
        coordinate_false_positives=coordinate_false_positives,
        passed_gate=passed_gate,
        rect_evaluated=rect_evaluated,
        rect_passed=rect_passed,
        rect_pass_rate=rect_pass_rate,
        polyline_evaluated=polyline_evaluated,
        polyline_passed=polyline_passed,
        polyline_pass_rate=polyline_pass_rate,
        pass_rate_by_suite=_pass_rate_by_suite(results),
        results=results,
    )
