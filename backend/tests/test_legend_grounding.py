"""Tests for legend grounding (text + template match)."""

from __future__ import annotations

import numpy as np
from PIL import Image

from ai.pipelines.legend_grounding import (
    DocumentAiGroundingProvider,
    PageWord,
    _find_text_occurrences,
    _mostly_inside_exclude,
)


def test_find_text_occurrences_matches_token_sequence() -> None:
    words = [
        PageWord("SSMH", "SSMH", (0.2, 0.3, 0.22, 0.31), 0.9),
        PageWord("OR", "OR", (0.23, 0.3, 0.25, 0.31), 0.88),
        PageWord("SDMH", "SDMH", (0.26, 0.3, 0.29, 0.31), 0.87),
    ]
    hits = _find_text_occurrences(
        label="SSMH OR SDMH",
        words=words,
        exclude_region=None,
    )
    assert len(hits) == 1
    assert hits[0].match_method == "document_ai_text"
    assert hits[0].confidence == 0.87


def test_exclude_region_drops_legend_sample() -> None:
    bbox = (0.71, 0.03, 0.75, 0.05)
    exclude = (0.70, 0.02, 0.78, 0.08)
    assert _mostly_inside_exclude(bbox, exclude) is True


def test_template_match_finds_repeated_patch() -> None:
    page = np.full((200, 300), 255, dtype=np.uint8)
    page[40:60, 50:80] = 0
    page[120:140, 180:210] = 0
    full = Image.fromarray(page, mode="L").convert("RGB")
    tmpl = full.crop((50, 40, 80, 60))

    provider = DocumentAiGroundingProvider(
        min_confidence=0.4,
        template_threshold=0.85,
        sync_ocr_fallback=False,
    )
    hits = provider.find_occurrences(
        full_page_image=full,
        exemplar_crop=tmpl,
        exemplar_label="patch",
        exclude_region_fractional=(0.0, 0.0, 0.3, 0.4),
        full_page_words=[],
    )
    template_hits = [h for h in hits if h.match_method == "template_match"]
    assert len(template_hits) >= 1
