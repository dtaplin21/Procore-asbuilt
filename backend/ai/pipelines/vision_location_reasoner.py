"""Vision-backed location reasoning for ambiguous matches and utility line traces."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai.agents.evidence_dossier import EvidenceDossier
from ai.pipelines.clue_fusion_scorer import (
    FusedCandidateScore,
    LLM_TIEBREAK_LOW_SCORE,
    LLM_TIEBREAK_SCORE_GAP,
)
from ai.pipelines.drawing_location_resolver import ResolutionMethod
from ai.pipelines.openai_vision import (
    _load_image,
    _mime_type_for_path,
    _vision_chat_completion,
    encode_image_as_data_url,
)
from ai.pipelines.scope_geometry import ScopeKind, infer_scope_kind
from services.inspection_match_persistence import MATCH_SCORE_THRESHOLD

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
_VISION_CONFIDENCE_BOOST = 0.08
_VALID_TASKS = frozenset({"localize", "trace_line", "detect_highlight"})


@dataclass(frozen=True)
class VisionLocationResult:
    best_candidate_index: int | None
    confidence: float
    bbox_fractional: tuple[float, float, float, float] | None
    polyline_points: tuple[tuple[float, float], ...] | None
    highlight_detected: bool
    rationale: str


def build_dossier_summary(dossier: EvidenceDossier) -> str:
    clue_lines = [
        f"- {clue.clue_type}: {', '.join(clue.expanded_values)}"
        for clue in dossier.expanded_clues
    ]
    parts = [
        f"evidence_kind={dossier.evidence_kind.value}",
        f"evidence_text={dossier.evidence_text[:1200]}",
        "expanded_clues:",
        *(clue_lines or ["(none)"]),
    ]
    return "\n".join(parts)


def should_invoke_vision(
    fused_scores: list[FusedCandidateScore],
    dossier: EvidenceDossier,
) -> bool:
    """True if top score < 0.65 OR top two within 0.05 OR scope_kind is UTILITY_LINE."""
    ordered = sorted(fused_scores, key=lambda score: -score.fused_score)
    if ordered and ordered[0].fused_score < LLM_TIEBREAK_LOW_SCORE:
        return True

    if len(ordered) >= 2:
        gap = ordered[0].fused_score - ordered[1].fused_score
        if gap <= LLM_TIEBREAK_SCORE_GAP:
            return True

    return infer_scope_kind(dossier) == ScopeKind.UTILITY_LINE


def reason_over_master_crop(
    *,
    master_png_path: Path,
    dossier_summary: str,
    candidate_bboxes: list[tuple[float, float, float, float]],
    task: str,
) -> VisionLocationResult:
    """Run structured vision reasoning on a master drawing crop."""
    normalized_task = task.strip().lower()
    if normalized_task not in _VALID_TASKS:
        raise ValueError(f"Unsupported vision task: {task!r}")

    prompt = _build_task_prompt(
        dossier_summary=dossier_summary,
        candidate_bboxes=candidate_bboxes,
        task=normalized_task,
    )

    try:
        raw_bytes, mime_type = _load_image(file_path=master_png_path)
    except (OSError, ValueError) as exc:
        logger.warning("vision_location_image_load_failed", extra={"error": str(exc)})
        return _empty_vision_result()

    data_url = encode_image_as_data_url(raw_bytes, mime_type or _mime_type_for_path(master_png_path))
    message = _vision_chat_completion(image_data_url=data_url, prompt=prompt, max_tokens=512)
    if not message:
        return _empty_vision_result()

    payload = _parse_vision_payload(message)
    if payload is None:
        return _empty_vision_result()

    return _vision_result_from_payload(payload)


def apply_vision_to_fused_scores(
    dossier: EvidenceDossier,
    scores: list[FusedCandidateScore],
    *,
    master_png_path: Path,
) -> list[FusedCandidateScore]:
    """Merge vision confidence into fused scores; never override strong coordinate match alone."""
    if not scores:
        return scores

    ordered = sorted(scores, key=lambda score: -score.fused_score)
    if _is_strong_coordinate_winner(ordered[0]):
        return scores

    if not should_invoke_vision(scores, dossier):
        return scores

    candidate_bboxes = [
        bbox
        for bbox in (
            score.candidate.bbox_fractional
            for score in ordered
            if score.candidate.bbox_fractional is not None
        )
        if bbox is not None
    ]
    if not candidate_bboxes:
        return scores

    vision = reason_over_master_crop(
        master_png_path=master_png_path,
        dossier_summary=build_dossier_summary(dossier),
        candidate_bboxes=candidate_bboxes,
        task="localize",
    )
    if vision.best_candidate_index is None or vision.confidence <= 0:
        return scores

    if vision.best_candidate_index < 0 or vision.best_candidate_index >= len(ordered):
        logger.warning(
            "vision_location_invalid_index",
            extra={
                "best_candidate_index": vision.best_candidate_index,
                "candidate_count": len(ordered),
            },
        )
        return scores

    updated: list[FusedCandidateScore] = []
    for index, score in enumerate(ordered):
        if index != vision.best_candidate_index:
            updated.append(score)
            continue

        boosted = max(
            score.fused_score,
            min(1.5, score.fused_score + vision.confidence * _VISION_CONFIDENCE_BOOST),
        )
        rationale = score.rationale
        if vision.rationale:
            rationale = f"{rationale} | vision={vision.rationale}"
        updated.append(
            FusedCandidateScore(
                candidate=score.candidate,
                fused_score=boosted,
                clue_hits=score.clue_hits,
                conflicts=score.conflicts,
                rationale=rationale,
            )
        )

    updated.sort(key=lambda item: (-item.fused_score, -item.candidate.confidence))
    return updated


def _build_task_prompt(
    *,
    dossier_summary: str,
    candidate_bboxes: list[tuple[float, float, float, float]],
    task: str,
) -> str:
    bbox_lines = [
        f"  Candidate {index}: {bbox}"
        for index, bbox in enumerate(candidate_bboxes[:5])
    ]
    shared_rules = (
        "Rules:\n"
        "- Coordinates are normalized 0-1 relative to the master drawing page.\n"
        "- Do NOT use sheet numbers.\n"
        "- Return JSON only.\n"
    )

    if task == "localize":
        schema = (
            "{\n"
            '  "best_candidate_index": 0,\n'
            '  "confidence": 0.0,\n'
            '  "bbox_fractional": [x0, y0, x1, y1],\n'
            '  "highlight_detected": false,\n'
            '  "rationale": "short explanation"\n'
            "}"
        )
        task_text = (
            "Pick the candidate bbox that best matches the inspection location and "
            "optionally refine bbox_fractional."
        )
    elif task == "trace_line":
        schema = (
            "{\n"
            '  "confidence": 0.0,\n'
            '  "polyline_points": [[x, y], [x, y]],\n'
            '  "highlight_detected": false,\n'
            '  "rationale": "short explanation"\n'
            "}"
        )
        task_text = (
            "Trace the utility line or scoped linear work area referenced by the inspection. "
            "Return at least two normalized polyline points along the line."
        )
    else:
        schema = (
            "{\n"
            '  "confidence": 0.0,\n'
            '  "bbox_fractional": [x0, y0, x1, y1],\n'
            '  "highlight_detected": true,\n'
            '  "rationale": "short explanation"\n'
            "}"
        )
        task_text = (
            "Detect any optional highlight/markup bbox if present. Highlight is enrichment only."
        )

    return "\n".join(
        [
            f"Task: {task}",
            task_text,
            shared_rules,
            f"Return schema:\n{schema}",
            "Inspection dossier:",
            dossier_summary,
            "Candidate bboxes (x0, y0, x1, y1):",
            *(bbox_lines or ["  (none)"]),
        ]
    )


def _parse_vision_payload(content: str) -> dict[str, Any] | None:
    trimmed = (content or "").strip()
    if not trimmed:
        return None

    candidates = [trimmed]
    block_match = _JSON_BLOCK_RE.search(trimmed)
    if block_match:
        candidates.insert(0, block_match.group(1))

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _vision_result_from_payload(payload: dict[str, Any]) -> VisionLocationResult:
    best_index_raw = payload.get("best_candidate_index", payload.get("best_index"))
    best_index: int | None = None
    if best_index_raw is not None:
        try:
            best_index = int(best_index_raw)
        except (TypeError, ValueError):
            best_index = None

    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    bbox = _parse_bbox_fractional(payload.get("bbox_fractional"))
    polyline = _parse_polyline_points(payload.get("polyline_points"))
    highlight_detected = bool(payload.get("highlight_detected", False))
    rationale = str(payload.get("rationale", "") or "").strip()

    return VisionLocationResult(
        best_candidate_index=best_index,
        confidence=confidence,
        bbox_fractional=bbox,
        polyline_points=polyline,
        highlight_detected=highlight_detected,
        rationale=rationale,
    )


def _parse_bbox_fractional(raw: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) < 4:
        return None
    try:
        x0, y0, x1, y1 = (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))
    except (TypeError, ValueError):
        return None
    return (_clamp01(x0), _clamp01(y0), _clamp01(x1), _clamp01(y1))


def _parse_polyline_points(raw: Any) -> tuple[tuple[float, float], ...] | None:
    if not isinstance(raw, list) or len(raw) < 2:
        return None

    points: list[tuple[float, float]] = []
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            try:
                points.append((_clamp01(float(item[0])), _clamp01(float(item[1]))))
            except (TypeError, ValueError):
                continue
        elif isinstance(item, dict):
            try:
                points.append((_clamp01(float(item["x"])), _clamp01(float(item["y"]))))
            except (KeyError, TypeError, ValueError):
                continue
    if len(points) < 2:
        return None
    return tuple(points)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _empty_vision_result() -> VisionLocationResult:
    return VisionLocationResult(
        best_candidate_index=None,
        confidence=0.0,
        bbox_fractional=None,
        polyline_points=None,
        highlight_detected=False,
        rationale="",
    )


def _is_strong_coordinate_winner(score: FusedCandidateScore) -> bool:
    if score.candidate.method != ResolutionMethod.COORDINATE_LOOKUP:
        return False
    if score.candidate.confidence < MATCH_SCORE_THRESHOLD:
        return False
    return any(hit.dimension == "coordinate" and hit.weight > 0 for hit in score.clue_hits)
