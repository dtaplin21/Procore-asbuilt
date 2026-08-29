"""OCR heuristics for viewport proposals (digitization V-5).

Does not invent pixel corners via LLM. Proposals are reviewable; prefer the
manual V-3 seed until reviewed on C4.20.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol, Sequence, cast

from sqlalchemy.orm import Session

from ai.pipelines.drawing_scale_parser import parse_scale_from_text
from ai.pipelines.sheet_entity_graph import DrawingViewport, ViewportKind, ViewportScale
from ai.pipelines.viewport_scale import viewport_scale_from_json
from models.drawing_text_element import DrawingTextElement

_KIND_RE = re.compile(
    r"\b(?P<kind>SECTION|DETAIL|PLAN|PROFILE|ELEVATION)\b",
    re.IGNORECASE,
)
_NOISE_RE = re.compile(r"planning|\.dwg|\\|/", re.IGNORECASE)
_TITLEBLOCK_X_MIN = 0.85
_DRAWING_X_MAX = 0.82
_MIN_TITLE_HEIGHT = 0.0030

# Default region templates when keywords appear in chrome (titleblock/footer)
# rather than as in-drawing view titles (common on plan & profile sheets).
_LAYOUT_PLAN_PROFILE: dict[str, tuple[float, float, float, float]] = {
    "plan": (0.03, 0.03, 0.82, 0.45),
    "profile": (0.03, 0.45, 0.82, 0.94),
}


class _TextTokenLike(Protocol):
    @property
    def text(self) -> str: ...

    @property
    def bbox_json(self) -> dict[str, float]: ...


@dataclass(frozen=True)
class _OcrToken:
    text: str
    bbox_json: dict[str, float]

    @classmethod
    def from_row(cls, row: DrawingTextElement) -> _OcrToken:
        return cls(
            text=str(row.text),
            bbox_json=cast(dict[str, float], row.bbox_json),
        )


@dataclass(frozen=True)
class _KindHit:
    kind: ViewportKind
    text: str
    bbox: tuple[float, float, float, float]
    score: float


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _bbox_tuple(bbox: dict[str, float]) -> tuple[float, float, float, float]:
    return (
        float(bbox["x0"]),
        float(bbox["y0"]),
        float(bbox["x1"]),
        float(bbox["y1"]),
    )


def _bbox_height(bbox: tuple[float, float, float, float]) -> float:
    return max(0.0, bbox[3] - bbox[1])


def _bbox_center(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    return (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0


def _expand_bbox(
    bbox: tuple[float, float, float, float],
    *,
    pad_x: float,
    pad_y: float,
) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = bbox
    return (
        _clamp01(x0 - pad_x),
        _clamp01(y0 - pad_y),
        _clamp01(x1 + pad_x),
        _clamp01(y1 + pad_y),
    )


def _bboxes_overlap(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _rfppi(scale: ViewportScale | None) -> float | None:
    if scale is None:
        return None
    value = float(scale.real_feet_per_paper_inch)
    return value if value > 0 else None


def _find_kind_hits(tokens: Sequence[_TextTokenLike]) -> list[_KindHit]:
    hits: list[_KindHit] = []
    for token in tokens:
        text = (token.text or "").strip()
        if not text or len(text) > 48:
            continue
        if _NOISE_RE.search(text):
            continue
        match = _KIND_RE.search(text)
        if match is None:
            continue
        # Avoid "Planning" / partials already filtered; require kind is a
        # primary word (short labels or title phrases).
        kind = cast(ViewportKind, match.group("kind").lower())
        bbox = _bbox_tuple(token.bbox_json)
        height = _bbox_height(bbox)
        if height < _MIN_TITLE_HEIGHT and text.upper() not in {
            "PLAN",
            "PROFILE",
            "SECTION",
            "DETAIL",
            "ELEVATION",
        }:
            continue
        cx, _cy = _bbox_center(bbox)
        in_drawing = cx <= _TITLEBLOCK_X_MIN
        # Prefer larger / drawing-area labels; still keep titleblock sheet-name hits.
        score = height * 100.0 + (2.0 if in_drawing else 0.5)
        if text.upper() == kind.upper():
            score += 1.0
        hits.append(_KindHit(kind=kind, text=text, bbox=bbox, score=score))
    return hits


def _best_hit_per_kind(hits: Sequence[_KindHit]) -> dict[ViewportKind, _KindHit]:
    best: dict[ViewportKind, _KindHit] = {}
    for hit in hits:
        existing = best.get(hit.kind)
        if existing is None or hit.score > existing.score:
            best[hit.kind] = hit
    return best


def _proposal_bbox_for_kind(
    kind: ViewportKind,
    hit: _KindHit,
    *,
    kinds_present: set[ViewportKind],
) -> tuple[float, float, float, float]:
    """Heuristic region; never invents corners from an LLM."""
    if kinds_present >= {"plan", "profile"} and kind in _LAYOUT_PLAN_PROFILE:
        return _LAYOUT_PLAN_PROFILE[kind]

    if kind in {"section", "detail"}:
        return _expand_bbox(hit.bbox, pad_x=0.12, pad_y=0.14)

    if kind == "elevation":
        return _expand_bbox(hit.bbox, pad_x=0.15, pad_y=0.12)

    if kind == "plan":
        return (0.03, 0.03, _DRAWING_X_MAX, 0.75)

    if kind == "profile":
        return (0.03, 0.45, _DRAWING_X_MAX, 0.94)

    return _expand_bbox(hit.bbox, pad_x=0.10, pad_y=0.10)


def _normalize_ocr_scale_text(text: str) -> str:
    """Map common OCR quote glyphs to ASCII so scale regex can match."""
    return (
        text.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u2032", "'")
        .replace("\u2033", '"')
    )


def _nearby_scale(
    tokens: Sequence[_TextTokenLike],
    region: tuple[float, float, float, float],
    *,
    page: int,
) -> ViewportScale | None:
    """Search OCR near/inside the proposal for a scale expression."""
    rx0, ry0, rx1, ry1 = region
    pad = 0.08
    search = (
        _clamp01(rx0 - pad),
        _clamp01(ry0 - pad),
        _clamp01(rx1 + pad),
        _clamp01(ry1 + pad),
    )
    snippets: list[str] = []
    for token in tokens:
        bbox = _bbox_tuple(token.bbox_json)
        cx, cy = _bbox_center(bbox)
        if not (search[0] <= cx <= search[2] and search[1] <= cy <= search[3]):
            continue
        text = _normalize_ocr_scale_text((token.text or "").strip())
        if text:
            snippets.append(text)

    # Try individual tokens first (cleaner), then a joined window.
    for text in snippets:
        parsed = parse_scale_from_text(text, page=page)
        if parsed is not None:
            return viewport_scale_from_json(parsed)
    if snippets:
        joined = " ".join(snippets)
        parsed = parse_scale_from_text(joined, page=page)
        if parsed is not None:
            return viewport_scale_from_json(parsed)
    return None


def filter_safe_ocr_commits(
    proposals: Sequence[DrawingViewport],
) -> list[DrawingViewport]:
    """Drop overlapping plan+section pairs that share the same scale.

    Never auto-commit that ambiguous multi-scale failure mode.
    """
    kept = list(proposals)
    drop_ids: set[str] = set()
    for i, a in enumerate(kept):
        for b in kept[i + 1 :]:
            kinds = {a.kind, b.kind}
            if kinds != {"plan", "section"}:
                continue
            if not _bboxes_overlap(a.bbox_fractional, b.bbox_fractional):
                continue
            ra, rb = _rfppi(a.scale), _rfppi(b.scale)
            if ra is None or rb is None:
                continue
            if abs(ra - rb) < 1e-6:
                # Keep the higher-confidence scale; drop the other.
                a_conf = a.scale.confidence if a.scale else 0.0
                b_conf = b.scale.confidence if b.scale else 0.0
                drop_ids.add(b.viewport_id if a_conf >= b_conf else a.viewport_id)
    return [vp for vp in kept if vp.viewport_id not in drop_ids]


def propose_viewports_from_tokens(
    tokens: Sequence[_TextTokenLike],
    *,
    page: int = 1,
) -> list[DrawingViewport]:
    """Heuristic viewport proposals from OCR tokens (no LLM coordinates)."""
    hits = _find_kind_hits(tokens)
    if not hits:
        return []

    best = _best_hit_per_kind(hits)
    kinds_present = set(best.keys())
    proposals: list[DrawingViewport] = []

    for kind, hit in sorted(best.items(), key=lambda item: item[0]):
        bbox = _proposal_bbox_for_kind(kind, hit, kinds_present=kinds_present)
        scale = _nearby_scale(tokens, bbox, page=page)
        conf = scale.confidence if scale is not None else max(0.35, min(0.7, hit.score / 10.0))
        if scale is None:
            # Still emit geometry proposal; scale left unset for manual fill.
            notes = f"OCR kind hit {hit.text!r}; no nearby scale parsed"
        else:
            notes = f"OCR kind hit {hit.text!r}; scale from nearby OCR"
            # Preserve parse confidence on the scale object.
            scale = ViewportScale(
                raw_text=scale.raw_text,
                real_feet_per_paper_inch=scale.real_feet_per_paper_inch,
                confidence=float(scale.confidence),
                horizontal=scale.horizontal,
                vertical=scale.vertical,
            )
        proposals.append(
            DrawingViewport(
                viewport_id=kind,
                kind=kind,
                page=page,
                bbox_fractional=bbox,
                scale=scale,
                source="ocr",
                notes=notes,
            )
        )

    return filter_safe_ocr_commits(proposals)


def propose_viewports_from_ocr(
    session: Session,
    drawing_id: int,
    *,
    page: int = 1,
) -> list[DrawingViewport]:
    """Load indexed OCR tokens and propose viewports for one drawing page."""
    rows = (
        session.query(DrawingTextElement)
        .filter(DrawingTextElement.master_drawing_id == int(drawing_id))
        .filter(DrawingTextElement.page == int(page))
        .order_by(DrawingTextElement.id.asc())
        .all()
    )
    tokens = [_OcrToken.from_row(row) for row in rows]
    return propose_viewports_from_tokens(tokens, page=page)


def proposal_to_seed_dict(viewport: DrawingViewport) -> dict[str, Any]:
    """Convert a dataclass proposal into seed-script upsert payload shape."""
    x0, y0, x1, y1 = viewport.bbox_fractional
    scale_json: dict[str, Any] | None = None
    if viewport.scale is not None:
        scale_json = {
            "raw_text": viewport.scale.raw_text,
            "real_feet_per_paper_inch": viewport.scale.real_feet_per_paper_inch,
            "confidence": viewport.scale.confidence,
            "page": viewport.page,
        }
        if viewport.scale.horizontal is not None:
            scale_json["horizontal"] = viewport.scale.horizontal
        if viewport.scale.vertical is not None:
            scale_json["vertical"] = viewport.scale.vertical
        paper = viewport.scale.real_feet_per_paper_inch
        if paper > 0:
            scale_json["paper_inches_per_real_foot"] = 1.0 / paper
    return {
        "viewport_id": viewport.viewport_id,
        "kind": viewport.kind,
        "bbox_json": {"x0": x0, "y0": y0, "x1": x1, "y1": y1},
        "scale_json": scale_json or {
            "raw_text": "",
            "real_feet_per_paper_inch": 0.0,
            "confidence": 0.0,
            "page": viewport.page,
        },
        "source": "ocr",
        "notes": viewport.notes,
    }
