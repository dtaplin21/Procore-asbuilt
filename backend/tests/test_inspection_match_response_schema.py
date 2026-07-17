"""Tests that inspection match API schemas stay frontend-safe."""

from api.schemas.inspection_match_response import InspectionMatchStatusResponse


def test_match_response_does_not_include_confidence() -> None:
    response = InspectionMatchStatusResponse(
        inspection_id="test-inspection",
        match_status="needs_review",
        bbox=None,
    )

    data = response.model_dump()

    assert "confidence" not in data
    assert "score" not in data
    assert "classification_confidence" not in data
    assert data["match_status"] == "needs_review"
