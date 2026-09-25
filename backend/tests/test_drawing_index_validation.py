"""Tests for drawing index validation helpers (Phase 5)."""

from __future__ import annotations

from services.drawing_index_validation import (
    IndexToken,
    diff_token_sets,
    keyword_hits,
    parse_audit_tsv,
    summarize_sources,
)


def test_parse_audit_tsv_and_summarize() -> None:
    tsv = (
        "page\tcentroid_x\tcentroid_y\tsource\tocr_confidence\ttext\n"
        "1\t0.1\t0.2\tnative_pdf\t1.0\tUCSF\n"
        "1\t0.5\t0.5\tdocument_ai\t0.9\tHIGHWAY\n"
    )
    tokens = parse_audit_tsv(tsv)
    assert len(tokens) == 2
    assert summarize_sources(tokens) == {"document_ai": 1, "native_pdf": 1}


def test_keyword_hits_gutter_filter() -> None:
    tokens = [
        IndexToken(1, 0.08, 0.3, "document_ai", "HIGHWAY 24"),
        IndexToken(1, 0.9, 0.3, "document_ai", "HIGHWAY"),
    ]
    hits = keyword_hits(tokens, ["HIGHWAY"], gutter_x_max=0.15, page=1)
    assert len(hits["HIGHWAY"]) == 1
    assert hits["HIGHWAY"][0].text == "HIGHWAY 24"


def test_diff_token_sets() -> None:
    base = [IndexToken(1, 0.1, 0.2, "tesseract", "SSMH")]
    curr = [
        IndexToken(1, 0.1, 0.2, "document_ai", "SSMH"),
        IndexToken(1, 0.5, 0.5, "document_ai", "MLK"),
    ]
    diff = diff_token_sets(base, curr)
    assert len(diff.shared) == 1
    assert len(diff.only_current) == 1
    assert diff.only_current[0].text == "MLK"
