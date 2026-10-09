"""Promote a viewport-level scale to ``drawings.scale_json`` when unambiguous.

Viewport scales come from OCR-adjacent parsing (see ``viewport_detector``) and
are stored on ``drawing_viewports`` / ``index_stats_json['sheetEntityGraph']``.
Title-block ``parse_scale_from_words`` often misses campus plan sheets even when
the PLAN viewport scale is already parsed — this closes that gap without
silently picking among conflicting viewport scales.
"""

from __future__ import annotations

import dataclasses
from typing import Any


MIN_PROMOTION_CONFIDENCE = 0.6
SCALE_AGREEMENT_REL_TOL = 0.02
SCALE_BAR_VETO_REL_TOL = 0.05
PREFERRED_VIEWPORT_KIND = "plan"


@dataclasses.dataclass
class ScaleCandidate:
    page: int | None
    viewport_id: str
    kind: str
    real_feet_per_paper_inch: float
    confidence: float
    raw_text: str | None
    bbox_fractional: list[float]
    scale_json: dict[str, Any]

    @property
    def area_fractional(self) -> float:
        if len(self.bbox_fractional) < 4:
            return 0.0
        x0, y0, x1, y1 = self.bbox_fractional
        return max(0.0, x1 - x0) * max(0.0, y1 - y0)


@dataclasses.dataclass
class ScalePromotionResult:
    promoted: bool
    scale_json: dict[str, Any] | None
    scale_found: bool
    scale_source: str | None
    source_viewport_id: str | None
    source_page: int | None
    ambiguous: bool
    candidates: list[ScaleCandidate]
    reason: str


def _bbox_fractional_from_viewport(vp: dict[str, Any]) -> list[float]:
    raw = vp.get("bbox_fractional")
    if isinstance(raw, (list, tuple)) and len(raw) >= 4:
        return [float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3])]
    bbox = vp.get("bbox_json")
    if isinstance(bbox, dict):
        return [
            float(bbox.get("x0", 0)),
            float(bbox.get("y0", 0)),
            float(bbox.get("x1", 0)),
            float(bbox.get("y1", 0)),
        ]
    return [0.0, 0.0, 0.0, 0.0]


def _collect_candidates(sheet_entity_graph_pages: dict[str, Any]) -> list[ScaleCandidate]:
    """``sheet_entity_graph_pages`` is the ``sheetEntityGraph`` shape: page key → page payload."""
    candidates: list[ScaleCandidate] = []
    for page_key, page_data in sheet_entity_graph_pages.items():
        if not isinstance(page_data, dict):
            continue
        try:
            page_num: int | None = int(page_key)
        except (TypeError, ValueError):
            page_num = None

        for vp in page_data.get("viewports", []) or []:
            if not isinstance(vp, dict):
                continue
            scale = vp.get("scale")
            if not scale or not isinstance(scale, dict):
                continue
            feet_per_inch = scale.get("real_feet_per_paper_inch")
            if feet_per_inch is None:
                continue
            try:
                feet_val = float(feet_per_inch)
            except (TypeError, ValueError):
                continue
            try:
                confidence = float(scale.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0
            candidates.append(
                ScaleCandidate(
                    page=page_num,
                    viewport_id=str(vp.get("viewport_id", "unknown")),
                    kind=str(vp.get("kind", "unknown")),
                    real_feet_per_paper_inch=feet_val,
                    confidence=confidence,
                    raw_text=scale.get("raw_text") if scale.get("raw_text") is not None else None,
                    bbox_fractional=_bbox_fractional_from_viewport(vp),
                    scale_json=dict(scale),
                )
            )
    return candidates


def _scales_agree(a: ScaleCandidate, b: ScaleCandidate) -> bool:
    if a.real_feet_per_paper_inch == 0 or b.real_feet_per_paper_inch == 0:
        return a.real_feet_per_paper_inch == b.real_feet_per_paper_inch
    rel_diff = abs(a.real_feet_per_paper_inch - b.real_feet_per_paper_inch) / max(
        a.real_feet_per_paper_inch, b.real_feet_per_paper_inch
    )
    return rel_diff <= SCALE_AGREEMENT_REL_TOL


def _pick_best(candidates: list[ScaleCandidate]) -> ScaleCandidate:
    def sort_key(c: ScaleCandidate) -> tuple[int, float, float, str]:
        return (
            0 if c.kind == PREFERRED_VIEWPORT_KIND else 1,
            -c.confidence,
            -c.area_fractional,
            c.viewport_id,
        )

    return sorted(candidates, key=sort_key)[0]


def promote_scale(
    sheet_entity_graph_pages: dict[str, Any],
    existing_drawing_scale_json: dict[str, Any] | None,
    scale_bar_feet_per_paper_inch: float | None = None,
) -> ScalePromotionResult:
    """Pure promotion logic — caller persists ``scale_json`` / ``index_stats_json``."""
    if existing_drawing_scale_json:
        return ScalePromotionResult(
            promoted=False,
            scale_json=existing_drawing_scale_json,
            scale_found=True,
            scale_source=None,
            source_viewport_id=None,
            source_page=None,
            ambiguous=False,
            candidates=[],
            reason="drawing.scale_json already set — not overwriting an existing value.",
        )

    all_candidates = _collect_candidates(sheet_entity_graph_pages)
    eligible = [c for c in all_candidates if c.confidence >= MIN_PROMOTION_CONFIDENCE]

    if not eligible:
        return ScalePromotionResult(
            promoted=False,
            scale_json=None,
            scale_found=False,
            scale_source=None,
            source_viewport_id=None,
            source_page=None,
            ambiguous=False,
            candidates=all_candidates,
            reason=(
                f"No viewport scale met the confidence threshold ({MIN_PROMOTION_CONFIDENCE})."
                if all_candidates
                else "No viewport reported a parsed scale."
            ),
        )

    best = _pick_best(eligible)
    disagreeing = [c for c in eligible if not _scales_agree(c, best)]

    if disagreeing:
        other = disagreeing[0]
        return ScalePromotionResult(
            promoted=False,
            scale_json=None,
            scale_found=False,
            scale_source=None,
            source_viewport_id=None,
            source_page=None,
            ambiguous=True,
            candidates=all_candidates,
            reason=(
                f"Conflicting viewport scales above confidence threshold: "
                f"{best.viewport_id} ({best.real_feet_per_paper_inch} ft/in) vs "
                f"{other.viewport_id} ({other.real_feet_per_paper_inch} ft/in). "
                "Refusing to silently pick one — needs a human check or a "
                "better viewport-kind classifier."
            ),
        )

    if scale_bar_feet_per_paper_inch is not None:
        bar = float(scale_bar_feet_per_paper_inch)
        if bar > 0 and best.real_feet_per_paper_inch > 0:
            rel = abs(best.real_feet_per_paper_inch - bar) / max(
                best.real_feet_per_paper_inch, bar
            )
            if rel > SCALE_BAR_VETO_REL_TOL:
                return ScalePromotionResult(
                    promoted=False,
                    scale_json=None,
                    scale_found=False,
                    scale_source=None,
                    source_viewport_id=None,
                    source_page=None,
                    ambiguous=True,
                    candidates=all_candidates,
                    reason=(
                        f"Viewport '{best.viewport_id}' scale "
                        f"{best.real_feet_per_paper_inch} ft/in disagrees with the "
                        f"sheet's scale bar ({bar:.2f} ft/in). Not promoting."
                    ),
                )

    promoted_scale_json = dict(best.scale_json)
    promoted_scale_json["source"] = "viewport_promotion"
    promoted_scale_json["source_viewport_id"] = best.viewport_id
    promoted_scale_json["source_page"] = best.page

    return ScalePromotionResult(
        promoted=True,
        scale_json=promoted_scale_json,
        scale_found=True,
        scale_source="viewport_promotion",
        source_viewport_id=best.viewport_id,
        source_page=best.page,
        ambiguous=False,
        candidates=all_candidates,
        reason=(
            f"Promoted scale from viewport '{best.viewport_id}' "
            f"(kind={best.kind}, confidence={best.confidence})."
        ),
    )


def scale_promotion_audit_entries(result: ScalePromotionResult) -> dict[str, Any]:
    """Patch fragment for ``drawing.index_stats_json``."""
    patch: dict[str, Any] = {
        "scale_found": result.scale_found,
        "scale_promotion_reason": result.reason,
    }
    if result.scale_source is not None:
        patch["scale_source"] = result.scale_source
    if result.ambiguous:
        patch["scale_ambiguous"] = True
        patch["scale_candidates"] = [dataclasses.asdict(c) for c in result.candidates]
    if result.promoted:
        patch["scale_promotion"] = {
            "source_viewport_id": result.source_viewport_id,
            "source_page": result.source_page,
        }
    return patch
