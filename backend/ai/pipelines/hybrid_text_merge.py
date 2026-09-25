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
OCR_SOURCE_DOCUMENT_AI = "document_ai"

_DEFAULT_PREFER_ORDER = (NATIVE_SOURCE, OCR_SOURCE_DOCUMENT_AI, OCR_SOURCE_TESSERACT)


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


def _tag_for_source(
    word: PositionedWord,
    source_key: str,
    *,
    tesseract_source: str,
) -> PositionedWord:
    if source_key == OCR_SOURCE_TESSERACT:
        return replace(word, token_source=tesseract_source)
    return replace(word, token_source=source_key)


def merge_native_ocr_and_document_ai_words(
    native_words: list[PositionedWord],
    document_ai_words: list[PositionedWord],
    tesseract_words: list[PositionedWord] | None = None,
    *,
    prefer_order: tuple[str, ...] = _DEFAULT_PREFER_ORDER,
    tesseract_source: str = OCR_SOURCE_TESSERACT,
) -> list[PositionedWord]:
    """Dedupe by page + fractional center + text similarity.

    On duplicate, keep the token from the source listed earlier in ``prefer_order``.
    """
    pools: dict[str, list[PositionedWord]] = {
        NATIVE_SOURCE: native_words,
        OCR_SOURCE_DOCUMENT_AI: document_ai_words,
        OCR_SOURCE_TESSERACT: tesseract_words or [],
    }
    merged: list[PositionedWord] = []
    for source_key in prefer_order:
        for word in pools.get(source_key, []):
            tagged = _tag_for_source(word, source_key, tesseract_source=tesseract_source)
            if any(words_are_duplicates(tagged, kept) for kept in merged):
                continue
            merged.append(tagged)
    return merged


def merge_native_and_ocr_words(
    native_words: list[PositionedWord],
    ocr_words: list[PositionedWord],
    *,
    ocr_source: str = OCR_SOURCE_TESSERACT,
) -> list[PositionedWord]:
    """Union native + OCR tokens (two-way); delegates to the three-way merge."""
    if ocr_source == OCR_SOURCE_DOCUMENT_AI:
        return merge_native_ocr_and_document_ai_words(
            native_words,
            document_ai_words=ocr_words,
            tesseract_words=None,
        )
    return merge_native_ocr_and_document_ai_words(
        native_words,
        document_ai_words=[],
        tesseract_words=ocr_words,
        tesseract_source=ocr_source,
    )
