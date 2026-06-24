"""
Extracts and classifies controlled-vocabulary entities out of free-text
evidence / inspection notes, using the canonical taxonomy defined in
services.inspection_vocabulary.

This is wired into inspection_mapping.py: when evidence text is mapped onto
master-drawing regions, extract_terms() is called first so the resulting
overlay/finding records carry normalized vocabulary tags (inspection type,
status, location, etc.) instead of raw free text.

Design notes
------------
- PHRASE categories match canonical terms and their aliases as whole words/
  phrases (case-insensitive), longest-match-first, so "Underground Fire
  Water Rough In" doesn't get pre-empted by a shorter "Underground" match
  at the same position.
- PATTERN categories (currently just sheet identifiers) use regex.
- CONFIDENCE_LABEL terms are excluded from extraction targets — a note
  saying "High Confidence" isn't an entity in the text, it's metadata
  *about* an extraction. confidence_for() below computes it instead.
- Every extracted entity reports the canonical form, the exact surface
  text matched, its position in the source string, and a confidence
  score/label so the result can drive both the strict (canonical) overlay
  pipeline and any downstream "are we sure about this" UI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from services.inspection_vocabulary import (
    VOCABULARY,
    MatchStrategy,
    VocabCategory,
)

# Categories that are never extraction targets in free text — they describe
# confidence *about* a match, not an entity present in the source.
_NON_EXTRACTABLE_CATEGORIES = frozenset({VocabCategory.CONFIDENCE_LABEL})


class ConfidenceLabel:
    HIGH = "High Confidence"
    MEDIUM = "Medium Confidence"
    LOW = "Low Confidence"


@dataclass(frozen=True)
class ExtractedTerm:
    category: VocabCategory
    canonical: str
    matched_text: str
    start: int
    end: int
    confidence_score: float  # 0.0–1.0
    confidence_label: str  # one of ConfidenceLabel.*

    def to_dict(self) -> dict:
        return {
            "category": self.category.value,
            "canonical": self.canonical,
            "matchedText": self.matched_text,
            "start": self.start,
            "end": self.end,
            "confidenceScore": self.confidence_score,
            "confidenceLabel": self.confidence_label,
        }


def confidence_for(score: float) -> str:
    """Map a raw confidence score to one of the three canonical labels."""
    if score >= 0.85:
        return ConfidenceLabel.HIGH
    if score >= 0.6:
        return ConfidenceLabel.MEDIUM
    return ConfidenceLabel.LOW


# ---------------------------------------------------------------------------
# Compiled matchers
# ---------------------------------------------------------------------------
# Built once at import time. PHRASE categories compile one alternation
# regex per category (canonical + aliases), longest alternative first so
# multi-word terms win over their own substrings. PATTERN categories
# compile their raw patterns.


def _escape_sorted_longest_first(strings: list[str]) -> list[str]:
    return sorted({re.escape(s) for s in strings}, key=len, reverse=True)


def _build_phrase_pattern(
    category: VocabCategory,
) -> tuple[re.Pattern, dict[str, str]] | None:
    cat_def = VOCABULARY[category]
    surface_forms: list[str] = []
    surface_to_canonical: dict[str, str] = {}
    for term in cat_def.terms:
        surface_forms.append(term.canonical)
        surface_to_canonical[term.canonical.lower()] = term.canonical
        for alias in term.aliases:
            surface_forms.append(alias)
            surface_to_canonical[alias.lower()] = term.canonical

    if not surface_forms:
        return None

    alternation = "|".join(_escape_sorted_longest_first(surface_forms))
    # \b works fine here since all current surface forms are alnum/space;
    # if a future term introduces leading/trailing punctuation, revisit.
    pattern = re.compile(rf"\b(?:{alternation})\b", re.IGNORECASE)
    return pattern, surface_to_canonical


def _build_pattern_matcher(category: VocabCategory) -> re.Pattern | None:
    cat_def = VOCABULARY[category]
    if not cat_def.patterns:
        return None
    # Sheet identifiers currently define a single pattern; if more than one
    # is added, OR them together.
    combined = "|".join(f"(?:{p})" for p in cat_def.patterns)
    return re.compile(combined, re.IGNORECASE)


_PHRASE_MATCHERS: dict[VocabCategory, re.Pattern] = {}
_PHRASE_SURFACE_MAPS: dict[VocabCategory, dict[str, str]] = {}
_PATTERN_MATCHERS: dict[VocabCategory, re.Pattern] = {}

for _category, _def in VOCABULARY.items():
    if _category in _NON_EXTRACTABLE_CATEGORIES:
        continue
    if _def.strategy == MatchStrategy.PHRASE:
        _built = _build_phrase_pattern(_category)
        if _built is not None:
            _PHRASE_MATCHERS[_category], _PHRASE_SURFACE_MAPS[_category] = _built
    elif _def.strategy == MatchStrategy.PATTERN:
        _compiled = _build_pattern_matcher(_category)
        if _compiled is not None:
            _PATTERN_MATCHERS[_category] = _compiled


# ---------------------------------------------------------------------------
# Confidence heuristics
# ---------------------------------------------------------------------------
# Deliberately simple and auditable rather than a black-box model, since
# inspection records may end up referenced in compliance contexts.
#
#   - Exact canonical casing match -> high base confidence.
#   - Alias / case-insensitive match -> slightly lower.
#   - Sheet identifiers get a confidence bump if immediately preceded by a
#     drawing-term word ("Sheet", "Drawing", "Detail", "Plan") since that
#     context rules out e.g. a stray part number.
#   - A curated set of single-word terms double as ordinary English words
#     ("Site", "Note", "New", "Plan", "Level", "Building", "Detail",
#     "Section", "Close", "Test", "Review"...) and are downgraded when
#     they appear alone with no supporting multi-word/contextual signal,
#     so a generic sentence doesn't light up as a high-confidence
#     inspection record. Multi-word matches (e.g. "Mechanical Room",
#     "Approved As Noted") are unambiguous by construction and are not
#     downgraded.

_SHEET_ID_CONTEXT_WORDS = {"sheet", "drawing", "detail", "plan", "dwg", "ref"}
_SHEET_ID_CONTEXT_PATTERN = re.compile(
    r"\b(?:" + "|".join(_SHEET_ID_CONTEXT_WORDS) + r")\b", re.IGNORECASE
)

_AMBIGUOUS_SINGLE_WORD_TERMS = {
    "site", "area", "phase", "building", "level", "floor", "roof",
    "section", "detail", "plan", "note", "comment", "stamp", "new",
    "review", "test", "close", "document", "observe", "confirm",
    "modify", "verify", "remove", "open", "closed", "completed",
}


def _phrase_confidence(matched_text: str, canonical: str) -> float:
    base = 0.95 if matched_text == canonical else 0.9 if matched_text.lower() == canonical.lower() else 0.8
    is_single_word = " " not in canonical.strip()
    if is_single_word and canonical.lower() in _AMBIGUOUS_SINGLE_WORD_TERMS:
        # Standalone ambiguous word: cap below the high-confidence
        # threshold so it surfaces as Medium, prompting a human glance,
        # rather than silently passing as a confident extraction.
        return min(base, 0.7)
    return base


def _sheet_id_confidence(text: str, start: int) -> float:
    window = text[max(0, start - 20) : start]
    if _SHEET_ID_CONTEXT_PATTERN.search(window):
        return 0.9
    return 0.65


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_terms(
    text: str,
    categories: tuple[VocabCategory, ...] | None = None,
) -> list[ExtractedTerm]:
    """Extract and classify controlled-vocabulary entities from free text.

    Args:
        text: raw evidence / inspection note text.
        categories: optional subset of categories to extract; defaults to
            all extractable categories.

    Returns:
        List of ExtractedTerm, sorted by position in the source text.
        Overlapping matches within the same category are resolved by
        keeping the longest match at a given start position.
    """
    if not text:
        return []

    target_categories = categories or tuple(
        c for c in VOCABULARY if c not in _NON_EXTRACTABLE_CATEGORIES
    )

    results: list[ExtractedTerm] = []

    for category in target_categories:
        if category in _PHRASE_MATCHERS:
            pattern = _PHRASE_MATCHERS[category]
            surface_to_canonical = _PHRASE_SURFACE_MAPS[category]
            for match in pattern.finditer(text):
                matched_text = match.group(0)
                canonical = surface_to_canonical.get(
                    matched_text.lower(), matched_text
                )
                score = _phrase_confidence(matched_text, canonical)
                results.append(
                    ExtractedTerm(
                        category=category,
                        canonical=canonical,
                        matched_text=matched_text,
                        start=match.start(),
                        end=match.end(),
                        confidence_score=score,
                        confidence_label=confidence_for(score),
                    )
                )
        elif category in _PATTERN_MATCHERS:
            pattern = _PATTERN_MATCHERS[category]
            for match in pattern.finditer(text):
                matched_text = match.group(0)
                score = _sheet_id_confidence(text, match.start())
                results.append(
                    ExtractedTerm(
                        category=category,
                        canonical=matched_text.upper(),
                        matched_text=matched_text,
                        start=match.start(),
                        end=match.end(),
                        confidence_score=score,
                        confidence_label=confidence_for(score),
                    )
                )

    results.sort(key=lambda t: (t.start, -(t.end - t.start)))
    return _drop_overlaps(results)


def _drop_overlaps(terms: list[ExtractedTerm]) -> list[ExtractedTerm]:
    """Within the same category, drop shorter matches fully contained in a
    longer match starting at/before them (keeps "Underground Fire Water
    Rough In" over a spurious standalone "Underground" at the same spot).
    Matches in different categories are allowed to overlap (e.g. a sheet
    ID inside a sentence that also contains a drawing term).
    """
    kept: list[ExtractedTerm] = []
    for term in terms:
        overlapped = False
        for existing in kept:
            if existing.category != term.category:
                continue
            if term.start >= existing.start and term.end <= existing.end:
                overlapped = True
                break
        if not overlapped:
            kept.append(term)
    kept.sort(key=lambda t: t.start)
    return kept


def extract_by_category(text: str) -> dict[str, list[ExtractedTerm]]:
    """Same extraction, grouped by category value for convenient lookup
    (e.g. result["inspection_status"], result["sheet_identifier"]).
    """
    grouped: dict[str, list[ExtractedTerm]] = {}
    for term in extract_terms(text):
        grouped.setdefault(term.category.value, []).append(term)
    return grouped


def overall_confidence_label(terms: list[ExtractedTerm]) -> str:
    """Roll up a list of extracted terms into a single confidence label
    for the record as a whole (e.g. an inspection_runs row) — the
    weakest-link score, since a downstream reviewer should be flagged to
    the least-certain extraction, not the average.
    """
    if not terms:
        return ConfidenceLabel.LOW
    lowest_score = min(t.confidence_score for t in terms)
    return confidence_for(lowest_score)
