"""JsonFormatter whitelist: workflow and finding fields must appear in JSON output."""

from __future__ import annotations

import json
import logging

from observability.logging_config import JsonFormatter


def test_json_formatter_emits_workflow_fields() -> None:
    formatter = JsonFormatter()

    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="job_status_transition",
        args=(),
        exc_info=None,
    )
    record.request_id = "req-123"
    record.project_id = 42
    record.job_id = 99
    record.status = "processing"
    record.previous_status = "pending"

    output = formatter.format(record)
    payload = json.loads(output)

    assert payload["msg"] == "job_status_transition"
    assert payload["request_id"] == "req-123"
    assert payload["project_id"] == 42
    assert payload["job_id"] == 99
    assert payload["status"] == "processing"
    assert payload["previous_status"] == "pending"


def test_json_formatter_emits_finding_fields() -> None:
    formatter = JsonFormatter()

    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="finding_created",
        args=(),
        exc_info=None,
    )
    record.request_id = "req-456"
    record.project_id = 7
    record.finding_id = 123
    record.evidence_ids = [5, 6]
    record.finding_type = "deviation"
    record.severity = "high"

    output = formatter.format(record)
    payload = json.loads(output)

    assert payload["msg"] == "finding_created"
    assert payload["request_id"] == "req-456"
    assert payload["project_id"] == 7
    assert payload["finding_id"] == 123
    assert payload["evidence_ids"] == [5, 6]
    assert payload["finding_type"] == "deviation"
    assert payload["severity"] == "high"
