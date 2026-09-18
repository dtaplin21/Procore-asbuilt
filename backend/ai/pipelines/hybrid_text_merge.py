"""Merge native PDF text-layer words with OCR words for master drawing index."""

from __future__ import annotations

import re
from dataclasses import replace

from ai.pipelines.document_text_extraction import PositionedWord

_WHITESPACE_RE = re.compile(r"\s+")
# Max center distance (fraction of page) to treat two boxes as the same token.
_DEFAULT_CENTER_DISTANCE = 0.025
# Jaccard-like threshold on normalized character sets for fuzzy duplicate text.
_DEFAULT_TEXT_SIMILARITY = 0.88

NATIVE_SOURCE = "native_pdf"
OCR_SOURCE_TESSERACT = "tesseract"


def normalize_merge_text(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text.strip().lower())


def _fractional_center(word: PositionedWord) -> tuple[float, float]:
    x0, y0, x1, y1 = word.bbox.to_fractional()
    return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)


def _center_distance(a: PositionedWord, b: PositionedWord) -> float:
    ax, ay = _fractional_center(a)
    bx, by = _fractional_center(b)
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def _text_similarity(a: str, b: str) -> float:
    na, nb = normalize_merge_text(a), normalize_merge_text(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    sa, sb = set(na), set(nb)
    union = sa | sb
    if not union:
        return 0.0
    return len(sa & sb) / len(union)


def words_are_duplicates(
    left: PositionedWord,
    right: PositionedWord,
    *,
    max_center_distance: float = _DEFAULT_CENTER_DISTANCE,
    min_text_similarity: float = _DEFAULT_TEXT_SIMILARITY,
) -> bool:
    if left.page_index != right.page_index:
        return False
    if _center_distance(left, right) > max_center_distance:
        return False
    return _text_similarity(left.text, right.text) >= min_text_similarity


def merge_native_and_ocr_words(
    native_words: list[PositionedWord],
    ocr_words: list[PositionedWord],
    *,
    ocr_source: str = OCR_SOURCE_TESSERACT,
) -> list[PositionedWord]:
    """Union native + OCR tokens; drop OCR when a native token matches (bbox + text).

    On duplicate, the native ``PositionedWord`` is kept (better character precision).
    """
    merged: list[PositionedWord] = [
        replace(word, token_source=NATIVE_SOURCE) for word in native_words
    ]
    for ocr_word in ocr_words:
        if any(words_are_duplicates(ocr_word, native_word) for native_word in native_words):
            continue
        merged.append(replace(ocr_word, token_source=ocr_source))
    return merged
