"""Phase 19 — backend match scores must not leak to frontend API responses."""

from __future__ import annotations

from datetime import datetime, timezone

from api.schemas.frontend_safe import (
    FORBIDDEN_FRONTEND_SCORE_KEYS,
    contains_forbidden_frontend_score_fields,
)
from api.schemas.inspection_match_response import InspectionMatchStatusResponse
from models.schemas import DrawingOverlayResponse


def test_inspection_match_status_response_rejects_extra_score_fields() -> None:
    payload = {
        "inspection_id": "123",
        "match_status": "needs_review",
        "bbox": None,
        "confidence": 0.61,
    }

    try:
        InspectionMatchStatusResponse.model_validate(payload)
        raised = False
    except Exception:
        raised = True

    assert raised is True


def test_drawing_overlay_response_strips_internal_scores_from_meta() -> None:
    response = DrawingOverlayResponse.model_validate(
        {
            "id": 1,
            "master_drawing_id": 2,
            "inspection_run_id": 3,
            "geometry": {"type": "point", "x": 0.0, "y": 0.0, "page": 1},
            "status": "unknown",
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "meta": {
                "match_status": "needs_review",
                "confidence": 0.91,
                "score": 0.88,
                "classification_confidence": 0.75,
                "match_score": 0.82,
            },
        }
    )

    dumped = response.model_dump(mode="json")
    assert dumped["meta"] == {"match_status": "needs_review"}
    assert contains_forbidden_frontend_score_fields(dumped) == []


def test_forbidden_score_key_list_covers_match_pipeline_fields() -> None:
    assert "confidence" in FORBIDDEN_FRONTEND_SCORE_KEYS
    assert "score" in FORBIDDEN_FRONTEND_SCORE_KEYS
    assert "classification_confidence" in FORBIDDEN_FRONTEND_SCORE_KEYS
    assert "match_score" in FORBIDDEN_FRONTEND_SCORE_KEYS
