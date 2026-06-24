"""
Runs the same controlled-vocabulary matching as term_extractor.py, but
over a PositionedWord sequence (from document_text_extraction.py) instead
of a plain string — so every extracted term carries a page bounding box,
not just a character offset.

This is the layer that makes "pair the extracted term with a location"
possible at all: a string offset tells you nothing about where something
sits on a page; a bounding box does.

Approach: reconstruct the page text from PositionedWord (joined with
single spaces, since that's how term_extractor's regexes expect text),
run the existing extract_terms() against that reconstructed text to get
character offsets, then map those offsets back onto the words that
produced them and union their boxes. This reuses term_extractor's tested
matching/confidence logic exactly rather than re-implementing it against
a token stream, so the two layers can't drift in matching behavior.
"""

from __future__ import annotations

from dataclasses import dataclass

from ai.pipelines.document_text_extraction import (
    BoundingBox,
    ExtractedDocument,
    PositionedWord,
)
from ai.pipelines.term_extractor import ExtractedTerm, extract_terms
from services.inspection_vocabulary import VocabCategory


@dataclass(frozen=True)
class PositionedTerm:
    """An ExtractedTerm plus where it sits on the source page."""

    term: ExtractedTerm
    page_index: int
    bbox: BoundingBox

    def to_dict(self) -> dict:
        return {
            **self.term.to_dict(),
            "pageIndex": self.page_index,
            "bbox": self.bbox.to_dict(),
        }


def _reconstruct_with_offsets(
    words: list[PositionedWord],
) -> tuple[str, list[tuple[int, int, PositionedWord]]]:
    """Join words with single spaces and record each word's
    (start_offset, end_offset, word) in the joined string, so a regex
    match's character span can be mapped back to the words it covers.
    """
    pieces: list[str] = []
    spans: list[tuple[int, int, PositionedWord]] = []
    cursor = 0
    for word in words:
        start = cursor
        end = start + len(word.text)
        spans.append((start, end, word))
        pieces.append(word.text)
        cursor = end + 1  # +1 for the joining space
    return " ".join(pieces), spans


def _union_boxes(boxes: list[BoundingBox]) -> BoundingBox:
    """Smallest box covering all given boxes — used when a matched term
    spans multiple words (e.g. "Approved As Noted" = 3 words -> 1 box).
    Assumes all boxes share the same page dimensions (true here since
    they all come from the same page).
    """
    x0 = min(b.x for b in boxes)
    y0 = min(b.y for b in boxes)
    x1 = max(b.x + b.width for b in boxes)
    y1 = max(b.y + b.height for b in boxes)
    first = boxes[0]
    return BoundingBox(
        x=x0,
        y=y0,
        width=x1 - x0,
        height=y1 - y0,
        page_width=first.page_width,
        page_height=first.page_height,
    )


def extract_positioned_terms_for_page(
    words: list[PositionedWord],
    page_index: int,
    categories: tuple[VocabCategory, ...] | None = None,
) -> list[PositionedTerm]:
    """Extract vocabulary terms from a single page's words, with bounding
    boxes. `words` should already be filtered to one page (and ideally in
    reading order — see ExtractedDocument.page_text's sort fallback).
    """
    if not words:
        return []

    reconstructed_text, spans = _reconstruct_with_offsets(words)
    matched_terms = extract_terms(reconstructed_text, categories=categories)

    positioned: list[PositionedTerm] = []
    for term in matched_terms:
        covering_words = [
            word
            for (start, end, word) in spans
            if start < term.end and end > term.start  # overlaps [term.start, term.end)
        ]
        if not covering_words:
            # Shouldn't happen given how the text was built, but don't
            # silently drop a match if it does — skip defensively.
            continue
        bbox = _union_boxes([w.bbox for w in covering_words])
        positioned.append(
            PositionedTerm(term=term, page_index=page_index, bbox=bbox)
        )

    return positioned


def extract_positioned_terms(
    document: ExtractedDocument,
    categories: tuple[VocabCategory, ...] | None = None,
) -> list[PositionedTerm]:
    """Extract vocabulary terms across every page of a document."""
    results: list[PositionedTerm] = []
    for page_index in range(document.page_count):
        page_words = [w for w in document.words if w.page_index == page_index]
        page_words.sort(key=lambda w: (round(w.bbox.y, 1), w.bbox.x))
        results.extend(
            extract_positioned_terms_for_page(page_words, page_index, categories)
        )
    return results
