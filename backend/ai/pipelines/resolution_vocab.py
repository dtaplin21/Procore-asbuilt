"""Shared vocabulary categories used for location resolution."""

from __future__ import annotations

from services.inspection_vocabulary import VocabCategory

RESOLUTION_VOCAB_CATEGORIES: tuple[VocabCategory, ...] = tuple(
    category
    for category in VocabCategory
    if category
    not in (VocabCategory.SHEET_IDENTIFIER, VocabCategory.CONFIDENCE_LABEL)
)
