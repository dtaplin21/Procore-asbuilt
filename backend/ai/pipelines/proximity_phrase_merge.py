"""Merge adjacent OCR tokens into single phrases (e.g. gutter ``HIGHWAY`` + ``24``)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

from ai.pipelines.document_text_extraction import BoundingBox, PositionedWord

# Fractional page coords — conservative thresholds to avoid over-merging plan text.
_HORIZ_X_GAP = 0.018
_ROW_Y_OVERLAP_MIN = 0.35
_VERT_X_CENTER_MAX = 0.022
_VERT_Y_GAP = 0.022


def _frac_box(word: PositionedWord) -> tuple[float, float, float, float]:
    return word.bbox.to_fractional()


def _x_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax0, _, ax1, _ = a
    bx0, _, bx1, _ = b
    return max(0.0, min(ax1, bx1) - max(ax0, bx0))


def _y_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    _, ay0, _, ay1 = a
    _, by0, _, by1 = b
    overlap = max(0.0, min(ay1, by1) - max(ay0, by0))
    min_h = max(min(ay1 - ay0, by1 - by0), 1e-9)
    return overlap / min_h


def _centers(box: tuple[float, float, float, float]) -> tuple[float, float]:
    x0, y0, x1, y1 = box
    return (x0 + x1) / 2.0, (y0 + y1) / 2.0


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
    if _y_overlap(la_box, rb_box) < _ROW_Y_OVERLAP_MIN:
        return False
    gap = rb_box[0] - la_box[2]
    return 0.0 <= gap <= _HORIZ_X_GAP


def _should_merge_vertical(a: PositionedWord, b: PositionedWord) -> bool:
    if a.page_index != b.page_index or not _same_source(a, b):
        return False
    fa, fb = _frac_box(a), _frac_box(b)
    if fa[1] <= fb[1]:
        ta, bb = fa, fb
    else:
        ta, bb = fb, fa
    cx_t, _ = _centers(ta)
    cx_b, _ = _centers(bb)
    if abs(cx_t - cx_b) > _VERT_X_CENTER_MAX:
        return False
    if _x_overlap(ta, bb) <= 0.0:
        return False
    gap = bb[1] - ta[3]
    return 0.0 <= gap <= _VERT_Y_GAP


def _combine_words(a: PositionedWord, b: PositionedWord, *, vertical: bool) -> PositionedWord:
    if vertical:
        top, bottom = (a, b) if _frac_box(a)[1] <= _frac_box(b)[1] else (b, a)
        text = f"{top.text.strip()} {bottom.text.strip()}".strip()
    else:
        left, right = (a, b) if _frac_box(a)[0] <= _frac_box(b)[0] else (b, a)
        text = f"{left.text.strip()} {right.text.strip()}".strip()
    conf = min(float(a.ocr_confidence), float(b.ocr_confidence))
    return replace(
        a,
        text=text,
        bbox=_merge_bbox(a.bbox, b.bbox),
        ocr_confidence=conf,
    )


def _merge_page_phrases(words: list[PositionedWord]) -> list[PositionedWord]:
    pending = list(words)
    changed = True
    while changed:
        changed = False
        used: set[int] = set()
        merged: list[PositionedWord] = []
        for i, word in enumerate(pending):
            if i in used:
                continue
            partner_idx: int | None = None
            vertical = False
            for j in range(i + 1, len(pending)):
                if j in used:
                    continue
                other = pending[j]
                if _should_merge_horizontal(word, other):
                    partner_idx = j
                    vertical = False
                    break
                if _should_merge_vertical(word, other):
                    partner_idx = j
                    vertical = True
                    break
            if partner_idx is None:
                merged.append(word)
                used.add(i)
                continue
            combined = _combine_words(word, pending[partner_idx], vertical=vertical)
            merged.append(combined)
            used.add(i)
            used.add(partner_idx)
            changed = True
        pending = merged
    return pending


def merge_proximate_phrases(words: list[PositionedWord]) -> list[PositionedWord]:
    """Return a new list with nearby tokens on each page merged into phrases."""
    if not words:
        return []
    by_page: dict[int, list[PositionedWord]] = defaultdict(list)
    for word in words:
        by_page[int(word.page_index)].append(word)
    out: list[PositionedWord] = []
    for page_index in sorted(by_page):
        page_words = by_page[page_index]
        out.extend(_merge_page_phrases(page_words))
    return out
