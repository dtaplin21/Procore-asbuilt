"""Unit tests for Document AI JSON → PositionedWord parsing (no live GCP)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai.pipelines.document_ai_parser import (
    TOKEN_SOURCE_DOCUMENT_AI,
    document_ai_document_to_words,
    document_ai_tokens_to_words,
    parse_document_json_file,
)

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "document_ai" / "sample_page.json"


def test_document_ai_tokens_to_words_single_page() -> None:
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    words = document_ai_tokens_to_words(data, page_index=0)
    assert len(words) == 2
    assert words[0].text == "HIGHWAY"
    assert words[1].text == "24"
    assert words[0].token_source == TOKEN_SOURCE_DOCUMENT_AI
    assert words[0].ocr_confidence == pytest.approx(0.95)
    assert words[0].bbox.page_width == 1000.0
    assert words[0].bbox.page_height == 2000.0
    assert words[0].bbox.x == pytest.approx(100.0)
    assert words[0].bbox.y == pytest.approx(400.0)
    assert words[0].bbox.width == pytest.approx(200.0)
    assert words[0].bbox.height == pytest.approx(100.0)


def test_document_ai_document_to_words_all_pages() -> None:
    words = parse_document_json_file(_FIXTURE)
    assert [w.text for w in words] == ["HIGHWAY", "24"]
    assert all(w.page_index == 0 for w in words)


def test_document_wrapper_with_nested_document_key() -> None:
    inner = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    wrapped = {"document": inner, "uri": "gs://bucket/out/0.json"}
    words = document_ai_document_to_words(wrapped)
    assert len(words) == 2


def test_empty_page_index_returns_empty() -> None:
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    assert document_ai_tokens_to_words(data, page_index=99) == []
