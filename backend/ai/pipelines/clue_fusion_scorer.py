"""Score location candidates by fusing evidence dossier clues + legend + master context."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from ai.agents.evidence_dossier import EvidenceDossier, ExpandedClue
from ai.pipelines.candidate_tile_selector import CandidateTile
from ai.pipelines.drawing_location_resolver import MasterRegion, ResolutionMethod
from ai.pipelines.location_match_orchestrator import LocationMatchCandidate
from services.inspection_vocabulary import location_labels_compatible
from services.location_match_eval import rect_iou

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
LLM_TIEBREAK_SCORE_GAP = 0.05
LLM_TIEBREAK_LOW_SCORE = 0.65
LLM_CANDIDATE_LIMIT = 5

FUSION_TIEBREAK_PROMPT = """
Given an inspection dossier summary and candidate areas on a master construction drawing,
choose which candidate best matches the inspection location.

Rules:
- Use legend expansions, inspection types, and location terms.
- Do NOT use sheet numbers or sheet identifiers.
- Only pick among the listed candidate indices (0-based).
- Return JSON only:
{
  "best_index": 0,
  "confidence": 0.0,
  "rationale": "short explanation",
  "conflicts": ["optional disagreement notes"]
}
"""

_GENERIC_LOCATION_TERMS = frozenset(
    {
        "utility",
        "utilities",
        "site",
        "area",
        "zone",
        "general",
        "field",
        "work area",
        "construction",
    }
)
_INSPECTION_CLUE_TYPES = frozenset(
    {
        "trade",
        "inspection_type",
        "inspection_name",
        "type_specific",
    }
)
_LOCATION_CLUE_TYPES = frozenset({"location_text", "location", "location_term"})
_SEWER_LEGEND_TOKENS = frozenset({"SS", "SSMH", "SANITARY SEWER", "SANITARY SEWERAGE"})
_BBOX_IOU_THRESHOLD = 0.05


@dataclass(frozen=True)
class ClueHit:
    clue_value: str
    dimension: str  # inspection_type | location | legend | coordinate | station | linked
    weight: float


@dataclass(frozen=True)
class FusedCandidateScore:
    candidate: LocationMatchCandidate
    fused_score: float
    clue_hits: tuple[ClueHit, ...]
    conflicts: tuple[str, ...]
    rationale: str


WEIGHTS = {
    "coordinate_proximity": 0.35,
    "station_match": 0.30,
    "inspection_type_region": 0.20,
    "location_term": 0.20,
    "legend_coherence": 0.15,
    "linked_attachment_agreement": 0.10,
    "generic_location_penalty": -0.15,
    "cross_clue_convergence_bonus": 0.10,
}


def fuse_candidate_scores(
    dossier: EvidenceDossier,
    candidates: list[LocationMatchCandidate],
) -> list[FusedCandidateScore]:
    """Fuse dossier clues against each candidate; sort descending by fused_score."""
    scored = [
        _score_candidate(dossier, candidate)
        for candidate in candidates
    ]
    scored.sort(key=lambda item: (-item.fused_score, -item.candidate.confidence))
    return scored


def select_fused_winner(
    scores: list[FusedCandidateScore],
    *,
    tie_epsilon: float = 0.01,
) -> FusedCandidateScore | None:
    """Pick the top fused candidate; break near-ties by matcher confidence."""
    actionable = [
        score
        for score in scores
        if score.fused_score > 0 and score.candidate.bbox_fractional is not None
    ]
    if not actionable:
        return None

    best = max(score.fused_score for score in actionable)
    tied = [
        score
        for score in actionable
        if score.fused_score >= best - tie_epsilon
    ]
    return max(tied, key=lambda score: score.candidate.confidence)


def fuse_with_llm_tiebreak(
    dossier: EvidenceDossier,
    top_scores: list[FusedCandidateScore],
) -> FusedCandidateScore | None:
    """Optional LLM reorder when deterministic fusion is ambiguous."""
    candidates = _actionable_fused_scores(top_scores)
    if not candidates or not _should_invoke_llm_tiebreak(candidates):
        return None

    payload = _call_fusion_llm(
        dossier,
        candidates[:LLM_CANDIDATE_LIMIT],
    )
    if payload is None:
        return None

    return _apply_llm_tiebreak(candidates[:LLM_CANDIDATE_LIMIT], payload)


def _actionable_fused_scores(
    scores: list[FusedCandidateScore],
) -> list[FusedCandidateScore]:
    return [
        score
        for score in scores
        if score.fused_score > 0 and score.candidate.bbox_fractional is not None
    ]


def _should_invoke_llm_tiebreak(scores: list[FusedCandidateScore]) -> bool:
    ordered = sorted(scores, key=lambda score: -score.fused_score)
    if not ordered:
        return False

    if ordered[0].fused_score < LLM_TIEBREAK_LOW_SCORE:
        return True

    if len(ordered) >= 2:
        gap = ordered[0].fused_score - ordered[1].fused_score
        if gap <= LLM_TIEBREAK_SCORE_GAP:
            return True

    return False


def _apply_llm_tiebreak(
    candidates: list[FusedCandidateScore],
    payload: dict[str, Any],
) -> FusedCandidateScore | None:
    try:
        best_index = int(payload["best_index"])
        llm_confidence = float(payload.get("confidence", 0.0))
    except (KeyError, TypeError, ValueError):
        logger.warning(
            "clue_fusion_llm_invalid_index",
            extra={"payload": payload},
        )
        return None

    if best_index < 0 or best_index >= len(candidates):
        logger.warning(
            "clue_fusion_llm_out_of_range",
            extra={"best_index": best_index, "candidate_count": len(candidates)},
        )
        return None

    llm_confidence = max(0.0, min(1.0, llm_confidence))
    chosen = candidates[best_index]
    rationale = str(payload.get("rationale", "") or "").strip()
    raw_conflicts = payload.get("conflicts", [])
    llm_conflicts = tuple(
        str(item).strip()
        for item in raw_conflicts
        if isinstance(raw_conflicts, list) and str(item).strip()
    )

    adjusted_score = max(
        chosen.fused_score,
        min(1.5, chosen.fused_score + llm_confidence * 0.05),
    )
    merged_rationale = chosen.rationale
    if rationale:
        merged_rationale = f"{merged_rationale} | llm={rationale}"

    merged_conflicts = tuple(dict.fromkeys([*chosen.conflicts, *llm_conflicts]))

    return FusedCandidateScore(
        candidate=chosen.candidate,
        fused_score=adjusted_score,
        clue_hits=chosen.clue_hits,
        conflicts=merged_conflicts,
        rationale=merged_rationale,
    )


def _build_fusion_prompt(
    dossier: EvidenceDossier,
    candidates: list[FusedCandidateScore],
) -> str:
    clue_lines = [
        f"- {clue.clue_type}: {', '.join(clue.expanded_values)}"
        for clue in dossier.expanded_clues
    ]
    attachment_lines = [
        f"- {attachment.filename}: {attachment.text_preview[:240]}"
        for attachment in dossier.linked_attachments
    ]
    candidate_lines: list[str] = []
    for index, score in enumerate(candidates):
        region = _region_for_candidate(dossier, score.candidate)
        region_labels = (
            ", ".join(region.location_labels) if region is not None else "unknown"
        )
        inspection_types = (
            ", ".join(region.inspection_types) if region is not None else "unknown"
        )
        candidate_lines.append(
            "\n".join(
                [
                    f"Candidate {index}:",
                    f"  method={score.candidate.method.value}",
                    f"  fused_score={score.fused_score:.3f}",
                    f"  region_id={score.candidate.region_id}",
                    f"  location_labels={region_labels}",
                    f"  inspection_types={inspection_types}",
                    f"  supporting_clues={', '.join(score.candidate.supporting_clues)}",
                    f"  deterministic_rationale={score.rationale}",
                ]
            )
        )

    sections = [
        FUSION_TIEBREAK_PROMPT.strip(),
        "Inspection dossier summary:",
        f"- evidence_kind={dossier.evidence_kind.value}",
        f"- evidence_text={dossier.evidence_text[:1200]}",
        "- expanded_clues:",
        *(clue_lines or ["  (none)"]),
        "- legend_codes_near_candidates:",
        f"  {', '.join(dossier.master_context.legend_codes_near_candidates) or '(none)'}",
    ]
    if attachment_lines:
        sections.extend(["- linked_attachments:", *attachment_lines])
    sections.extend(["Candidate areas:", *candidate_lines])
    return "\n".join(sections)


def _parse_fusion_payload(content: str) -> dict[str, Any] | None:
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
            return _sanitize_fusion_dict(parsed)
    return None


def _sanitize_fusion_dict(raw: dict[str, Any]) -> dict[str, Any]:
    try:
        best_index = int(raw.get("best_index", -1))
    except (TypeError, ValueError):
        best_index = -1

    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    rationale = str(raw.get("rationale", "") or "").strip()
    conflicts_raw = raw.get("conflicts", [])
    conflicts: list[str] = []
    if isinstance(conflicts_raw, list):
        conflicts = [str(item).strip() for item in conflicts_raw if str(item).strip()]

    return {
        "best_index": best_index,
        "confidence": max(0.0, min(1.0, confidence)),
        "rationale": rationale,
        "conflicts": conflicts,
    }


def _call_fusion_llm(
    dossier: EvidenceDossier,
    candidates: list[FusedCandidateScore],
) -> dict[str, Any] | None:
    """Wire to the repo's existing OpenAI chat client."""
    try:
        from config import settings
        from openai import OpenAI
    except ImportError:
        return None

    if not getattr(settings, "openai_api_key", None):
        return None

    if not candidates:
        return None

    prompt = _build_fusion_prompt(dossier, candidates)
    client = OpenAI(api_key=settings.openai_api_key)

    try:
        resp = client.chat.completions.create(
            model=settings.openai_chat_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=256,
        )
        message = (resp.choices[0].message.content or "").strip()
        return _parse_fusion_payload(message)
    except Exception as exc:
        logger.warning("clue_fusion_llm_failed", extra={"error": str(exc)})
        return None


def _score_candidate(
    dossier: EvidenceDossier,
    candidate: LocationMatchCandidate,
) -> FusedCandidateScore:
    region = _region_for_candidate(dossier, candidate)
    nearby_text = _nearby_tile_text(dossier, candidate)
    hits: list[ClueHit] = []
    conflicts: list[str] = []
    dimensions: set[str] = set()

    hits.extend(_coordinate_hits(candidate, dimensions))
    hits.extend(_station_hits(candidate, dimensions))
    hits.extend(
        _inspection_type_hits(
            dossier.expanded_clues,
            region=region,
            nearby_text=nearby_text,
            dimensions=dimensions,
        )
    )
    location_hits, location_conflicts = _location_term_hits(
        dossier.expanded_clues,
        region=region,
        nearby_text=nearby_text,
        dimensions=dimensions,
    )
    hits.extend(location_hits)
    conflicts.extend(location_conflicts)
    hits.extend(
        _legend_hits(
            dossier.expanded_clues,
            legend_codes=dossier.master_context.legend_codes_near_candidates,
            nearby_text=nearby_text,
            dimensions=dimensions,
        )
    )
    hits.extend(
        _linked_attachment_hits(
            dossier,
            region=region,
            nearby_text=nearby_text,
            dimensions=dimensions,
        )
    )

    generic_only = _generic_location_only(dossier.expanded_clues, hits)
    penalty = 0.0
    if generic_only:
        penalty = WEIGHTS["generic_location_penalty"]
        hits.append(
            ClueHit(
                clue_value="generic location only",
                dimension="location",
                weight=penalty,
            )
        )

    bonus = 0.0
    if len(dimensions) >= 3:
        bonus = WEIGHTS["cross_clue_convergence_bonus"]
        hits.append(
            ClueHit(
                clue_value=f"{len(dimensions)} dimensions",
                dimension="convergence",
                weight=bonus,
            )
        )

    matcher_base = candidate.confidence * 0.1
    fused_score = matcher_base + sum(hit.weight for hit in hits)
    fused_score = max(0.0, min(fused_score, 1.5))

    rationale_parts = [
        f"matcher={candidate.method.value}@{candidate.confidence:.2f}",
    ]
    if region is not None:
        rationale_parts.append(
            f"region={region.region_id} labels={','.join(region.location_labels)}"
        )
    if hits:
        rationale_parts.append(
            "hits="
            + "; ".join(f"{hit.dimension}:{hit.clue_value}" for hit in hits[:6])
        )
    if conflicts:
        rationale_parts.append("conflicts=" + "; ".join(conflicts[:3]))

    return FusedCandidateScore(
        candidate=candidate,
        fused_score=fused_score,
        clue_hits=tuple(hits),
        conflicts=tuple(conflicts),
        rationale=" | ".join(rationale_parts),
    )


def _region_for_candidate(
    dossier: EvidenceDossier,
    candidate: LocationMatchCandidate,
) -> MasterRegion | None:
    if candidate.region_id is not None:
        region_key = str(candidate.region_id)
        for region in dossier.master_context.regions:
            if region.region_id == region_key:
                return region

    if candidate.bbox_fractional is None:
        return None

    best_region: MasterRegion | None = None
    best_iou = 0.0
    candidate_rect = _xyxy_to_xywh(candidate.bbox_fractional)
    for region in dossier.master_context.regions:
        region_rect = _xyxy_to_xywh(region.bbox_on_master.to_fractional())
        overlap = rect_iou(candidate_rect, region_rect)
        if overlap > best_iou:
            best_iou = overlap
            best_region = region

    if best_iou >= _BBOX_IOU_THRESHOLD:
        return best_region
    return None


def _nearby_tile_text(
    dossier: EvidenceDossier,
    candidate: LocationMatchCandidate,
) -> str:
    if candidate.bbox_fractional is None:
        return ""

    texts: list[str] = []
    candidate_rect = _xyxy_to_xywh(candidate.bbox_fractional)
    for tile in dossier.master_context.candidate_tiles:
        if tile.bbox_normalized is None:
            continue
        tile_rect = _xyxy_to_xywh(tile.bbox_normalized)
        if rect_iou(candidate_rect, tile_rect) >= _BBOX_IOU_THRESHOLD:
            texts.append(tile.text)
    return " ".join(texts).upper()


def _coordinate_hits(
    candidate: LocationMatchCandidate,
    dimensions: set[str],
) -> list[ClueHit]:
    if candidate.method != ResolutionMethod.COORDINATE_LOOKUP and not any(
        clue.startswith("coordinate:") for clue in candidate.supporting_clues
    ):
        return []

    dimensions.add("coordinate")
    value = next(
        (clue for clue in candidate.supporting_clues if clue.startswith("coordinate:")),
        "survey coordinate",
    )
    weight = WEIGHTS["coordinate_proximity"] * max(candidate.confidence, 0.5)
    return [ClueHit(clue_value=value, dimension="coordinate", weight=weight)]


def _station_hits(
    candidate: LocationMatchCandidate,
    dimensions: set[str],
) -> list[ClueHit]:
    if candidate.method != ResolutionMethod.STATION_LOOKUP and not any(
        clue.startswith("station:") for clue in candidate.supporting_clues
    ):
        return []

    dimensions.add("station")
    value = next(
        (clue for clue in candidate.supporting_clues if clue.startswith("station:")),
        "station match",
    )
    weight = WEIGHTS["station_match"] * max(candidate.confidence, 0.5)
    return [ClueHit(clue_value=value, dimension="station", weight=weight)]


def _inspection_type_hits(
    expanded_clues: tuple[ExpandedClue, ...],
    *,
    region: MasterRegion | None,
    nearby_text: str,
    dimensions: set[str],
) -> list[ClueHit]:
    if region is None:
        return []

    hits: list[ClueHit] = []
    region_types = {tag.lower() for tag in region.inspection_types}
    for clue in expanded_clues:
        if clue.clue_type not in _INSPECTION_CLUE_TYPES:
            continue
        for value in clue.expanded_values:
            normalized = value.strip().lower()
            if not normalized:
                continue
            if any(
                normalized in tag or tag in normalized for tag in region_types
            ) or normalized.upper() in nearby_text:
                dimensions.add("inspection_type")
                weight = WEIGHTS["inspection_type_region"] * max(clue.confidence, 0.5)
                hits.append(
                    ClueHit(
                        clue_value=value,
                        dimension="inspection_type",
                        weight=weight,
                    )
                )
                break
    return hits


def _location_term_hits(
    expanded_clues: tuple[ExpandedClue, ...],
    *,
    region: MasterRegion | None,
    nearby_text: str,
    dimensions: set[str],
) -> tuple[list[ClueHit], list[str]]:
    hits: list[ClueHit] = []
    conflicts: list[str] = []
    region_labels = region.location_labels if region is not None else ()

    for clue in expanded_clues:
        if clue.clue_type not in _LOCATION_CLUE_TYPES:
            continue
        for value in clue.expanded_values:
            normalized = value.strip()
            if not normalized or _is_generic_location(normalized):
                continue

            region_match = bool(
                region_labels
                and location_labels_compatible(normalized, region_labels)
            )
            text_match = normalized.upper() in nearby_text

            if region_match or text_match:
                dimensions.add("location")
                weight = WEIGHTS["location_term"] * max(clue.confidence, 0.5)
                hits.append(
                    ClueHit(
                        clue_value=normalized,
                        dimension="location",
                        weight=weight,
                    )
                )
            elif region is not None and region_labels:
                conflicts.append(
                    f"location {normalized!r} not in region tags {region_labels}"
                )

    return hits, conflicts


def _legend_hits(
    expanded_clues: tuple[ExpandedClue, ...],
    *,
    legend_codes: tuple[str, ...],
    nearby_text: str,
    dimensions: set[str],
) -> list[ClueHit]:
    report_tokens = _sewer_tokens_from_clues(expanded_clues)
    if not report_tokens:
        return []

    drawing_tokens = {
        token.upper()
        for token in legend_codes
        if token.strip()
    }
    drawing_tokens.update(_sewer_tokens_from_text(nearby_text))

    overlap = report_tokens.intersection(drawing_tokens)
    if not overlap:
        return []

    dimensions.add("legend")
    token = sorted(overlap)[0]
    return [
        ClueHit(
            clue_value=token,
            dimension="legend",
            weight=WEIGHTS["legend_coherence"],
        )
    ]


def _linked_attachment_hits(
    dossier: EvidenceDossier,
    *,
    region: MasterRegion | None,
    nearby_text: str,
    dimensions: set[str],
) -> list[ClueHit]:
    if not dossier.linked_attachments:
        return []

    hits: list[ClueHit] = []
    region_labels = region.location_labels if region is not None else ()
    for attachment in dossier.linked_attachments:
        preview = attachment.text_preview.upper()
        if not preview.strip():
            continue

        for clue in dossier.expanded_clues:
            if clue.clue_type not in _LOCATION_CLUE_TYPES:
                continue
            for value in clue.expanded_values:
                token = value.strip().upper()
                if not token or token not in preview:
                    continue
                region_ok = (
                    region is None
                    or not region_labels
                    or location_labels_compatible(value, region_labels)
                    or token in nearby_text
                )
                if region_ok:
                    dimensions.add("linked")
                    hits.append(
                        ClueHit(
                            clue_value=f"{attachment.filename}:{value}",
                            dimension="linked",
                            weight=WEIGHTS["linked_attachment_agreement"],
                        )
                    )
                    return hits
    return hits


def _generic_location_only(
    expanded_clues: tuple[ExpandedClue, ...],
    hits: list[ClueHit],
) -> bool:
    location_clues = [
        value
        for clue in expanded_clues
        if clue.clue_type in _LOCATION_CLUE_TYPES
        for value in clue.expanded_values
        if value.strip()
    ]
    if not location_clues:
        return False

    non_generic = [
        value
        for value in location_clues
        if not _is_generic_location(value)
    ]
    if non_generic:
        return False

    location_hits = [hit for hit in hits if hit.dimension == "location" and hit.weight > 0]
    other_positive = [
        hit
        for hit in hits
        if hit.dimension not in {"location", "convergence"} and hit.weight > 0
    ]
    return bool(location_hits) and not other_positive


def _is_generic_location(value: str) -> bool:
    normalized = " ".join(value.strip().lower().split())
    return normalized in _GENERIC_LOCATION_TERMS


def _sewer_tokens_from_clues(
    expanded_clues: tuple[ExpandedClue, ...],
) -> set[str]:
    tokens: set[str] = set()
    for clue in expanded_clues:
        for value in clue.expanded_values:
            tokens.update(_sewer_tokens_from_text(value))
    return tokens


def _sewer_tokens_from_text(text: str) -> set[str]:
    upper = text.upper()
    found: set[str] = set()
    for token in _SEWER_LEGEND_TOKENS:
        if token in upper:
            found.add(token)
    if re.search(r"\bSS\b", upper):
        found.add("SS")
    if re.search(r"\bSSMH\b", upper):
        found.add("SSMH")
    return found


def _xyxy_to_xywh(bbox: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = bbox
    return (x0, y0, max(x1 - x0, 0.0), max(y1 - y0, 0.0))
