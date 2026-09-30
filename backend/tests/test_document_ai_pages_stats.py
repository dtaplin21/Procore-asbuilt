"""Document AI page billing fields in index stats."""

from __future__ import annotations

from ai.pipelines.master_drawing_indexer import IndexResult


def test_index_stats_json_includes_document_ai_pages_processed() -> None:
    result = IndexResult(
        pages=3,
        document_ai_stats={
            "document_ai_pages_processed": 3,
            "document_ai_cache_hit": False,
        },
    )
    stats = result.to_stats_json()
    assert stats["document_ai_pages_processed"] == 3
    assert stats["document_ai"]["document_ai_pages_processed"] == 3


def test_index_stats_json_cache_hit_zero_billed_pages() -> None:
    result = IndexResult(
        document_ai_stats={
            "document_ai_pages_processed": 0,
            "document_ai_pages_in_document": 12,
            "document_ai_cache_hit": True,
        },
    )
    assert result.to_stats_json()["document_ai_pages_processed"] == 0


def test_index_stats_json_includes_merge_pipeline_fields() -> None:
    result = IndexResult(
        text_elements=991,
        document_ai_stats={"document_ai_token_count": 1092},
        merge_pipeline_stats={
            "document_ai_token_count_raw": 1092,
            "text_elements_persisted": 991,
            "text_elements_dropped_by_merge": 101,
            "merge_scope": "gutter_rotated_ocr_only",
            "text_elements_pre_merge": 1092,
            "text_elements_post_merge": 991,
        },
    )
    stats = result.to_stats_json()
    assert stats["text_elements"] == 991
    assert stats["document_ai_token_count_raw"] == 1092
    assert stats["text_elements_persisted"] == 991
    assert stats["text_elements_dropped_by_merge"] == 101
    assert stats["merge_scope"] == "gutter_rotated_ocr_only"
