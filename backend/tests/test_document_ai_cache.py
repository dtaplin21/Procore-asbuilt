"""Tests for Document AI GCS cache helpers (Phase 6)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from services.document_ai_cache import cached_output_prefix, pdf_content_sha256


def test_pdf_content_sha256_stable(tmp_path: Path) -> None:
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-same")
    assert pdf_content_sha256(pdf) == pdf_content_sha256(pdf)
    pdf.write_bytes(b"%PDF-changed")
    assert pdf_content_sha256(pdf) != "0" * 64


def test_cached_output_prefix_uses_drawing_and_hash(monkeypatch) -> None:
    from config import settings

    monkeypatch.setattr(settings, "document_ai_gcs_output_bucket", "my-out-bucket")
    prefix = cached_output_prefix(drawing_id=1691, content_hash="abc123")
    assert prefix == "gs://my-out-bucket/batch-output/by-drawing/1691/abc123/"


def test_batch_extract_skips_api_when_cache_has_json(tmp_path: Path, monkeypatch) -> None:
    from config import settings

    monkeypatch.setattr(settings, "document_ai_gcs_output_bucket", "bucket")
    monkeypatch.setattr(settings, "document_ai_gcs_input_bucket", "bucket")
    monkeypatch.setattr(settings, "document_ai_processor_id", "projects/p/locations/us/processors/x")
    monkeypatch.setattr(settings, "google_cloud_project", "p")

    pdf = tmp_path / "m.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    from ai.pipelines.document_ai_batch import batch_extract_words_from_pdf
    from ai.pipelines.document_text_extraction import PositionedWord, BoundingBox

    word = PositionedWord(
        text="SSMH",
        bbox=BoundingBox(0, 0, 1, 1, 100, 100),
        page_index=0,
        token_source="document_ai",
    )

    with (
        patch(
            "ai.pipelines.document_ai_batch.list_output_json_blobs",
            return_value=["batch-output/by-drawing/1/hash/out.json"],
        ),
        patch(
            "ai.pipelines.document_ai_batch.words_from_output_blobs",
            return_value=[word],
        ),
        patch("ai.pipelines.document_ai_batch.upload_pdf") as upload_mock,
        patch("ai.pipelines.document_ai_batch.start_batch_process") as start_mock,
    ):
        result = batch_extract_words_from_pdf(
            pdf,
            drawing_id=1,
            content_hash="deadbeef",
        )

    assert result.cache_hit is True
    assert len(result.words) == 1
    upload_mock.assert_not_called()
    start_mock.assert_not_called()
