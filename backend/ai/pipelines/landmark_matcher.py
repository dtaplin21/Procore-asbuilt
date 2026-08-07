"""Match evidence landmarks to master landmarks using Hu moment fingerprints."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from ai.pipelines.landmark_extractor import LandmarkRecord, extract_landmarks_from_page

HU_MATCH_THRESHOLD = 0.15
MIN_LANDMARK_MATCHES = 2
VECTOR_ERROR_MAX_NORM = 0.03
BBOX_PADDING_NORM = 0.01
CONFIDENCE_TWO_PAIRS = 0.70
CONFIDENCE_THREE_OR_MORE_PAIRS = 0.72
HINT_CONFIDENCE_BOOST = 0.02


@dataclass(frozen=True)
class ContourMatchResult:
    confidence: float
    bbox_fractional: tuple[float, float, float, float]
    pair_count: int
    notes: str


def hu_distance(a: list[float], b: list[float]) -> float:
    total = 0.0
    for left, right in zip(a, b):
        if left == 0.0 and right == 0.0:
            continue
        left_sign = 1.0 if left >= 0 else -1.0
        right_sign = 1.0 if right >= 0 else -1.0
        total += abs(
            left_sign * math.log10(abs(left) + 1e-10)
            - right_sign * math.log10(abs(right) + 1e-10)
        )
    return total


def _centroid(bbox: dict[str, float]) -> tuple[float, float]:
    return (
        (bbox["x0"] + bbox["x1"]) / 2.0,
        (bbox["y0"] + bbox["y1"]) / 2.0,
    )


def _union_master_bbox(
    master_landmarks: Sequence[LandmarkRecord],
    *,
    padding: float = BBOX_PADDING_NORM,
) -> tuple[float, float, float, float]:
    x0 = min(float(item.bbox_json["x0"]) for item in master_landmarks)
    y0 = min(float(item.bbox_json["y0"]) for item in master_landmarks)
    x1 = max(float(item.bbox_json["x1"]) for item in master_landmarks)
    y1 = max(float(item.bbox_json["y1"]) for item in master_landmarks)
    return (
        max(0.0, x0 - padding),
        max(0.0, y0 - padding),
        min(1.0, x1 + padding),
        min(1.0, y1 + padding),
    )


def _vector_error_norm(
    evidence_a: LandmarkRecord,
    evidence_b: LandmarkRecord,
    master_a: LandmarkRecord,
    master_b: LandmarkRecord,
) -> float:
    ev_ax, ev_ay = _centroid(evidence_a.bbox_json)
    ev_bx, ev_by = _centroid(evidence_b.bbox_json)
    ms_ax, ms_ay = _centroid(master_a.bbox_json)
    ms_bx, ms_by = _centroid(master_b.bbox_json)
    delta_ev = (ev_bx - ev_ax, ev_by - ev_ay)
    delta_ms = (ms_bx - ms_ax, ms_by - ms_ay)
    return math.hypot(delta_ev[0] - delta_ms[0], delta_ev[1] - delta_ms[1])


def _greedy_landmark_pairs(
    evidence_landmarks: Sequence[LandmarkRecord],
    master_landmarks: Sequence[LandmarkRecord],
) -> list[tuple[int, int, float]]:
    candidates: list[tuple[float, int, int]] = []
    for ev_index, evidence in enumerate(evidence_landmarks):
        for ms_index, master in enumerate(master_landmarks):
            distance = hu_distance(
                list(evidence.hu_moments_json),
                list(master.hu_moments_json),
            )
            if distance <= HU_MATCH_THRESHOLD:
                candidates.append((distance, ev_index, ms_index))

    candidates.sort(key=lambda item: item[0])
    used_evidence: set[int] = set()
    used_master: set[int] = set()
    pairs: list[tuple[int, int, float]] = []
    for distance, ev_index, ms_index in candidates:
        if ev_index in used_evidence or ms_index in used_master:
            continue
        used_evidence.add(ev_index)
        used_master.add(ms_index)
        pairs.append((ev_index, ms_index, distance))
    return pairs


def _pairs_have_consistent_vectors(
    evidence_landmarks: Sequence[LandmarkRecord],
    master_landmarks: Sequence[LandmarkRecord],
    pairs: Sequence[tuple[int, int, float]],
) -> bool:
    if len(pairs) < MIN_LANDMARK_MATCHES:
        return False

    for i in range(len(pairs)):
        for j in range(i + 1, len(pairs)):
            ev_i, ms_i, _ = pairs[i]
            ev_j, ms_j, _ = pairs[j]
            error = _vector_error_norm(
                evidence_landmarks[ev_i],
                evidence_landmarks[ev_j],
                master_landmarks[ms_i],
                master_landmarks[ms_j],
            )
            if error > VECTOR_ERROR_MAX_NORM:
                return False
    return True


def run_landmark_matcher(
    *,
    master_landmarks: Sequence[LandmarkRecord],
    evidence_rendition_png: str,
    evidence_page_meta: dict[str, Any],
    optional_hint_bbox: tuple[float, float, float, float] | None = None,
) -> ContourMatchResult | None:
    """Return a contour match from full-page evidence landmark extraction."""
    if not master_landmarks:
        return None

    evidence_landmarks = extract_landmarks_from_page(
        evidence_rendition_png,
        evidence_page_meta,
        optional_hint_bbox=optional_hint_bbox,
    )
    if not evidence_landmarks:
        return None

    pairs = _greedy_landmark_pairs(evidence_landmarks, master_landmarks)
    if len(pairs) < MIN_LANDMARK_MATCHES:
        return None
    if not _pairs_have_consistent_vectors(evidence_landmarks, master_landmarks, pairs):
        return None

    matched_master = [master_landmarks[ms_index] for _, ms_index, _ in pairs]
    bbox = _union_master_bbox(matched_master)
    pair_count = len(pairs)
    confidence = (
        CONFIDENCE_THREE_OR_MORE_PAIRS
        if pair_count >= 3
        else CONFIDENCE_TWO_PAIRS
    )
    if optional_hint_bbox is not None and any(
        float(record.meta_json.get("hint_overlap", 0.0)) > 0
        for record in evidence_landmarks
        if isinstance(record, LandmarkRecord)
    ):
        confidence = min(confidence + HINT_CONFIDENCE_BOOST, CONFIDENCE_THREE_OR_MORE_PAIRS)

    return ContourMatchResult(
        confidence=confidence,
        bbox_fractional=bbox,
        pair_count=pair_count,
        notes=f"Contour match from {pair_count} landmark pairs",
    )
