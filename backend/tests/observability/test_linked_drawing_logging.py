"""Linked drawing registration trace logging."""

from __future__ import annotations

import json
import logging

import pytest

from observability.linked_drawing_logging import (
    log_linked_drawing_registration_attempt,
    log_linked_drawing_skip,
)
from observability.logging_config import JsonFormatter


def test_json_formatter_emits_linked_drawing_fields() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="qcqa.linked_drawing",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="linked_drawing_registration_attempt",
        args=(),
        exc_info=None,
    )
    record.evidence_id = 376
    record.project_id = 2
    record.fetched_pdf_count = 0
    record.supplemental_chars = 12000
    record.skip_reason = "empty_fetched_pdfs"

    payload = json.loads(formatter.format(record))
    assert payload["fetched_pdf_count"] == 0
    assert payload["skip_reason"] == "empty_fetched_pdfs"


def test_log_registration_attempt_empty_fetched_pdfs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="qcqa.linked_drawing")

    log_linked_drawing_registration_attempt(
        evidence_id=376,
        project_id=2,
        followed_count=1,
        skipped_count=0,
        fetched_pdf_count=0,
        supplemental_chars=5000,
    )
    log_linked_drawing_skip(
        evidence_id=376,
        project_id=2,
        linked_filename="",
        skip_reason="empty_fetched_pdfs",
    )

    messages = [r.getMessage() for r in caplog.records if r.name == "qcqa.linked_drawing"]
    assert "linked_drawing_registration_attempt" in messages
    assert "linked_drawing_skip" in messages
