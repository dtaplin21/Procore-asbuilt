"""Merge adjacent OCR tokens into short phrases (gutter + vertical edge ROIs only).

- Left gutter: ``gutter_rotated_ocr`` in ``DRAWING_INDEX_GUTTER_*`` band (horizontal + vertical).
- Plan edge: ``document_ai`` in ``DRAWING_INDEX_VERTICAL_PHRASE_RECT`` (vertical stack / small y-gap only).

All other tokens pass through unchanged.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from typing import Final, Literal

from ai.pipelines.document_text_extraction import BoundingBox, PositionedWord
from ai.pipelines.fractional_coords import clamp_fractional_bbox
from config import settings

GUTTER_MERGE_ENABLED_SOURCES: Final[frozenset[str]] = frozenset({"gutter_rotated_ocr"})
VERTICAL_PHRASE_MERGE_SOURCES: Final[frozenset[str]] = frozenset({"document_ai"})
# Stored on ``index_stats_json`` so raw vs persisted gaps are attributed to merge, not data loss.
MERGE_SCOPE_STATS_LABEL: Final[str] = "gutter_rotated_ocr_only"
MAX_MERGE_CHAIN_LEN: Final[int] = 4
MAX_MERGED_STRING_LEN: Final[int] = 40

MergeZone = Literal["gutter", "vertical_phrase"]

# Fractional page coords.
_HORIZ_X_GAP = 0.018
_ROW_Y_OVERLAP_MIN = 0.35
_VERT_Y_GAP = 0.022
_STACK_X0_TOL = 0.015


def _parse_rect(value: str | None) -> tuple[float, float, float, float] | None:
    if not value or not str(value).strip():
        return None
    parts = [p.strip() for p in str(value).split(",")]
    if len(parts) != 4:
        return None
    return clamp_fractional_bbox((float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3])))


def _gutter_band_rect() -> tuple[float, float, float, float]:
    x1 = float(settings.drawing_index_gutter_x_max)
    y0 = float(settings.drawing_index_gutter_y_min)
    y1 = float(settings.drawing_index_gutter_y_max)
    return clamp_fractional_bbox((0.0, y0, x1, y1))


def _vertical_phrase_rect() -> tuple[float, float, float, float] | None:
    return _parse_rect(settings.drawing_index_vertical_phrase_rect)


def _centroid_in_rect(word: PositionedWord, rect: tuple[float, float, float, float]) -> bool:
    x0, y0, x1, y1 = word.bbox.to_fractional()
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    rx0, ry0, rx1, ry1 = rect
    return rx0 <= cx <= rx1 and ry0 <= cy <= ry1


def merge_zone_for_token(word: PositionedWord) -> MergeZone | None:
    source = (word.token_source or "").strip().lower()
    if source in GUTTER_MERGE_ENABLED_SOURCES and _centroid_in_rect(word, _gutter_band_rect()):
        return "gutter"
    vrect = _vertical_phrase_rect()
    if vrect is not None and source in VERTICAL_PHRASE_MERGE_SOURCES and _centroid_in_rect(word, vrect):
        return "vertical_phrase"
    return None


def should_merge_token(word: PositionedWord) -> bool:
    return merge_zone_for_token(word) is not None


def _frac_box(word: PositionedWord) -> tuple[float, float, float, float]:
    return word.bbox.to_fractional()


def boxes_are_vertically_stacked(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
    *,
    x_tol: float = _STACK_X0_TOL,
) -> bool:
    """Same column (x0 within tolerance) and overlapping y intervals."""
    same_column = abs(a[0] - b[0]) <= x_tol
    y_overlap = not (a[3] < b[1] or b[3] < a[1])
    return same_column and y_overlap


def _y_interval_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return not (a[3] < b[1] or b[3] < a[1])


def _small_vertical_gap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    if a[1] <= b[1]:
        top, bottom = a, b
    else:
        top, bottom = b, a
    gap = bottom[1] - top[3]
    return 0.0 <= gap <= _VERT_Y_GAP


def _y_overlap_ratio(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    _, ay0, _, ay1 = a
    _, by0, _, by1 = b
    overlap = max(0.0, min(ay1, by1) - max(ay0, by0))
    min_h = max(min(ay1 - ay0, by1 - by0), 1e-9)
    return overlap / min_h


def _merge_bbox(a: BoundingBox, b: BoundingBox) -> BoundingBox:
    pw = a.page_width or b.page_width
    ph = a.page_height or b.page_height
    ax0, ay0, ax1, ay1 = a.to_fractional()
    bx0, by0, bx1, by1 = b.to_fractional()
    x0 = min(ax0, bx0) * pw
    y0 = min(ay0, by0) * ph
    x1 = max(ax1, bx1) * pw
    y1 = max(ay1, by1) * ph
    return BoundingBox(x=x0, y=y0, width=x1 - x0, height=y1 - y0, page_width=pw, page_height=ph)


def _same_source(a: PositionedWord, b: PositionedWord) -> bool:
    return (a.token_source or "") == (b.token_source or "")


def _should_merge_horizontal(a: PositionedWord, b: PositionedWord) -> bool:
    if a.page_index != b.page_index or not _same_source(a, b):
        return False
    fa, fb = _frac_box(a), _frac_box(b)
    la_box, rb_box = (fa, fb) if fa[0] <= fb[0] else (fb, fa)
    if _y_overlap_ratio(la_box, rb_box) < _ROW_Y_OVERLAP_MIN:
        return False
    gap = rb_box[0] - la_box[2]
    return 0.0 <= gap <= _HORIZ_X_GAP


def _should_merge_vertical(a: PositionedWord, b: PositionedWord) -> bool:
    if a.page_index != b.page_index or not _same_source(a, b):
        return False
    fa, fb = _frac_box(a), _frac_box(b)
    cx_a = (fa[0] + fa[2]) / 2.0
    cx_b = (fb[0] + fb[2]) / 2.0
    if abs(cx_a - cx_b) > _STACK_X0_TOL:
        return False
    if boxes_are_vertically_stacked(fa, fb):
        return True
    return _small_vertical_gap(fa, fb)


@dataclass
class _ChainWord:
    word: PositionedWord
    chain_len: int = 1


def _combined_text(a: PositionedWord, b: PositionedWord, *, vertical: bool) -> str:
    if vertical:
        top, bottom = (a, b) if _frac_box(a)[1] <= _frac_box(b)[1] else (b, a)
        # Edge labels read upward: lower token on page (larger y) first — e.g. HIGHWAY 24.
        return f"{bottom.text.strip()} {top.text.strip()}".strip()
    left, right = (a, b) if _frac_box(a)[0] <= _frac_box(b)[0] else (b, a)
    return f"{left.text.strip()} {right.text.strip()}".strip()


def _can_merge_chains(left: _ChainWord, right: _ChainWord, *, vertical: bool) -> bool:
    if left.chain_len + right.chain_len > MAX_MERGE_CHAIN_LEN:
        return False
    text = _combined_text(left.word, right.word, vertical=vertical)
    return len(text) <= MAX_MERGED_STRING_LEN


def _combine_chain(left: _ChainWord, right: _ChainWord, *, vertical: bool) -> _ChainWord:
    text = _combined_text(left.word, right.word, vertical=vertical)
    conf = min(float(left.word.ocr_confidence), float(right.word.ocr_confidence))
    merged_word = replace(
        left.word,
        text=text,
        bbox=_merge_bbox(left.word.bbox, right.word.bbox),
        ocr_confidence=conf,
    )
    return _ChainWord(word=merged_word, chain_len=left.chain_len + right.chain_len)


def _merge_page_phrases(
    words: list[PositionedWord],
    *,
    allow_horizontal: bool,
    max_chain: int = MAX_MERGE_CHAIN_LEN,
    max_len: int = MAX_MERGED_STRING_LEN,
) -> list[PositionedWord]:
    pending = [_ChainWord(word=w) for w in words]
    changed = True
    while changed:
        changed = False
        used: set[int] = set()
        merged: list[_ChainWord] = []
        for i, item in enumerate(pending):
            if i in used:
                continue
            partner_idx: int | None = None
            vertical = False
            for j in range(i + 1, len(pending)):
                if j in used:
                    continue
                other = pending[j]
                if allow_horizontal and _should_merge_horizontal(item.word, other.word):
                    if item.chain_len + other.chain_len <= max_chain:
                        candidate = _combined_text(item.word, other.word, vertical=False)
                        if len(candidate) <= max_len:
                            partner_idx = j
                            vertical = False
                            break
                if _should_merge_vertical(item.word, other.word):
                    if _can_merge_chains(item, other, vertical=True):
                        partner_idx = j
                        vertical = True
                        break
            if partner_idx is None:
                merged.append(item)
                used.add(i)
                continue
            combined = _combine_chain(item, pending[partner_idx], vertical=vertical)
            merged.append(combined)
            used.add(i)
            used.add(partner_idx)
            changed = True
        pending = merged
    return [item.word for item in pending]


def merge_proximate_phrases(words: list[PositionedWord]) -> list[PositionedWord]:
    """Merge tokens only inside gated ROIs; all others pass through unchanged."""
    if not words:
        return []

    by_key: dict[tuple[int, MergeZone], list[PositionedWord]] = defaultdict(list)
    for word in words:
        zone = merge_zone_for_token(word)
        if zone is not None:
            by_key[(int(word.page_index), zone)].append(word)

    if not by_key:
        return list(words)

    merged_by_key: dict[tuple[int, MergeZone], list[PositionedWord]] = {}
    for key, group in by_key.items():
        allow_horizontal = key[1] == "gutter"
        merged_by_key[key] = _merge_page_phrases(group, allow_horizontal=allow_horizontal)

    emitted: set[tuple[int, MergeZone]] = set()
    out: list[PositionedWord] = []
    for word in words:
        zone = merge_zone_for_token(word)
        if zone is None:
            out.append(word)
            continue
        key = (int(word.page_index), zone)
        if key not in emitted:
            out.extend(merged_by_key.get(key, [word]))
            emitted.add(key)
    return out
