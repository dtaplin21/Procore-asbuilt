"""Document AI settings validation (Phase 7)."""

from __future__ import annotations

import pytest

from config import Settings, document_ai_configured


def test_document_ai_configured_false_when_incomplete() -> None:
    s = Settings(
        database_url="postgresql://u:p@localhost:5432/db",
        google_cloud_project="proj",
    )
    assert document_ai_configured(s) is False


def test_document_ai_configured_true_when_complete() -> None:
    s = Settings(
        database_url="postgresql://u:p@localhost:5432/db",
        google_cloud_project="proj",
        document_ai_processor_id="projects/p/locations/us/processors/abc",
        document_ai_gcs_input_bucket="in",
        document_ai_gcs_output_bucket="out",
    )
    assert document_ai_configured(s) is True


def test_rejects_openai_vision_ocr_when_document_ai_enabled() -> None:
    with pytest.raises(ValueError, match="openai_vision"):
        Settings(
            database_url="postgresql://u:p@localhost:5432/db",
            document_ai_enabled=True,
            ocr_backend="openai_vision",
        )


def test_allows_tesseract_ocr_with_document_ai_enabled() -> None:
    s = Settings(
        database_url="postgresql://u:p@localhost:5432/db",
        document_ai_enabled=True,
        ocr_backend="tesseract",
    )
    assert s.ocr_backend == "tesseract"
