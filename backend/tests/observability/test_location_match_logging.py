"""Location match trace logging helpers."""

from __future__ import annotations

import json
import logging

import pytest

from observability.location_match_logging import (
    log_inspection_match_result,
    serialize_method_candidate,
)
from observability.logging_config import JsonFormatter


class _FakeMethod:
    value = "reference_lookup"


class _FakeCandidate:
    method = _FakeMethod()
    confidence = 0.94
    bbox_fractional = (0.6, 1.15, 0.608, 1.193)
    page = 1
    region_id = 42
    source_drawing_id = 661
    notes = "Clue tile match on drawing 661."


def test_serialize_method_candidate_rounds_bbox() -> None:
    payload = serialize_method_candidate(_FakeCandidate())
    assert payload["method"] == "reference_lookup"
    assert payload["confidence"] == 0.94
    assert payload["bbox"] == [0.6, 1.15, 0.608, 1.193]


def test_json_formatter_emits_match_trace_fields() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="qcqa.location_match",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="inspection_match_result",
        args=(),
        exc_info=None,
    )
    record.request_id = "req-1"
    record.evidence_id = 363
    record.inspection_run_id = 438
    record.match_status = "matched"
    record.match_method = "reference_lookup"
    record.confidence = 0.94
    record.bbox = [0.6, 1.15, 0.608, 1.193]
    record.candidates = [{"method": "reference_lookup", "confidence": 0.94}]
    record.match_detail = {"scoped_point_count": 0, "evidence_point_count": 2}

    payload = json.loads(formatter.format(record))
    assert payload["msg"] == "inspection_match_result"
    assert payload["evidence_id"] == 363
    assert payload["match_method"] == "reference_lookup"
    assert payload["match_detail"]["scoped_point_count"] == 0


def test_log_inspection_match_result_emits_structured_event(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="qcqa.location_match")

    class _Result:
        method = _FakeMethod()
        confidence = 0.94
        bbox_fractional = (0.6, 1.15, 0.608, 1.193)
        page = 1
        region_id = 42
        notes = "Clue tile match on drawing 661."

    log_inspection_match_result(
        evidence_id=363,
        master_drawing_id=661,
        result=_Result(),
        match_status="matched",
        inspection_run_id=438,
    )

    assert any(r.msg == "inspection_match_result" for r in caplog.records)
