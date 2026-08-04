"""Unit tests for allowlisted external URL fetch guards."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ai.pipelines.document_text_extraction import ExtractedDocument, PositionedWord, SourceFormat
from services.safe_url_fetch import (
    fetch_url_text_with_error,
    is_allowed_external_url,
    max_response_bytes,
    url_fetch_blocked_reason,
)


def test_procore_app_url_is_allowed() -> None:
    url = "https://app.procore.com/projects/123/locations/456"

    assert is_allowed_external_url(url) is True
    assert url_fetch_blocked_reason(url) is None


def test_procore_storage_and_s3_redirect_targets_are_allowed() -> None:
    storage = (
        "https://storage.procore.com/api/v5/files/us-east-1/pro-core.com/"
        "1789-c/5747272-p/01KXRWH87V5MSTG49T0TSEDJHB"
    )
    s3 = (
        "https://s3.amazonaws.com/pro-core.com/1789-c/5747272-p/"
        "01KXRWH87V5MSTG49T0TSEDJHB?X-Amz-Signature=abc"
    )

    assert is_allowed_external_url(storage) is True
    assert is_allowed_external_url(s3) is True
    assert url_fetch_blocked_reason(s3) is None


def test_localhost_is_rejected() -> None:
    url = "http://127.0.0.1/secret"

    assert is_allowed_external_url(url) is False
    reason = url_fetch_blocked_reason(url)
    assert reason is not None
    assert "127.0.0.1" in reason


def test_file_scheme_is_rejected() -> None:
    url = "file:///etc/passwd"

    assert is_allowed_external_url(url) is False
    reason = url_fetch_blocked_reason(url)
    assert reason is not None
    assert "file" in reason


def test_default_max_response_bytes_is_20mb() -> None:
    assert max_response_bytes() == 20 * 1024 * 1024


def test_fetch_pdf_uses_ocr_not_native_text_layer() -> None:
    url = "https://storage.procore.com/files/plan.pdf"
    fake_doc = ExtractedDocument(
        source_format=SourceFormat.SCANNED_PDF,
        page_count=1,
        words=[PositionedWord(text="Utility MR", bbox=MagicMock(), page_index=0)],
    )

    with (
        patch(
            "services.safe_url_fetch.fetch_allowed_url",
            return_value=MagicMock(
                ok=True,
                content_type="application/pdf",
                content_disposition=None,
                body=b"%PDF-1.4 fake",
            ),
        ),
        patch(
            "services.safe_url_fetch.extract_document_via_ocr",
            return_value=fake_doc,
        ) as ocr_mock,
    ):
        text, error = fetch_url_text_with_error(url)

    assert error is None
    assert text == "Utility MR"
    ocr_mock.assert_called_once()
    assert ocr_mock.call_args.kwargs.get("max_pages") is None


def test_fetch_pdf_uses_content_disposition_filename() -> None:
    url = "https://storage.procore.com/files/01KXRWH87V5MSTG49T0TSEDJHB"
    fake_doc = ExtractedDocument(
        source_format=SourceFormat.SCANNED_PDF,
        page_count=2,
        words=[PositionedWord(text="STA 10+05.00", bbox=MagicMock(), page_index=0)],
    )

    with (
        patch(
            "services.safe_url_fetch.fetch_allowed_url",
            return_value=MagicMock(
                ok=True,
                content_type="application/pdf",
                content_disposition='attachment; filename="7.20 Sanitary Sewer Install.pdf"',
                body=b"%PDF-1.4 fake",
            ),
        ),
        patch(
            "services.safe_url_fetch.extract_document_via_ocr",
            return_value=fake_doc,
        ),
    ):
        from services.safe_url_fetch import fetch_url_attachment_with_error

        attachment = fetch_url_attachment_with_error(url)

    assert attachment.error is None
    assert attachment.filename == "7.20 Sanitary Sewer Install.pdf"
    assert attachment.pages == 2


def test_fetch_image_uses_ocr() -> None:
    url = "https://storage.procore.com/files/sheet.png"
    fake_doc = ExtractedDocument(
        source_format=SourceFormat.IMAGE,
        page_count=1,
        words=[PositionedWord(text="NPC-5", bbox=MagicMock(), page_index=0)],
    )

    with (
        patch(
            "services.safe_url_fetch.fetch_allowed_url",
            return_value=MagicMock(
                ok=True,
                content_type="image/png",
                content_disposition=None,
                body=b"\x89PNG\r\n\x1a\n fake",
            ),
        ),
        patch(
            "services.safe_url_fetch.extract_document_via_ocr",
            return_value=fake_doc,
        ) as ocr_mock,
    ):
        text, error = fetch_url_text_with_error(url)

    assert error is None
    assert text == "NPC-5"
    ocr_mock.assert_called_once()
