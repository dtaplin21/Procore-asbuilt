"""Vision confirmation integration for inspection matching.

Vision models may compute internal scores, but only match_status and optional bbox
are written to frontend-facing overlay state.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from services.inspection_match_persistence import (
    InternalMatchCandidate,
    MatchStatus,
    finalize_inspection_match_from_internal_candidate,
)


def apply_vision_confirmation_result(
    session: Session,
    *,
    inspection_id: str,
    drawing_id: str | int,
    internal_score: float,
    bbox: tuple[float, float, float, float] | None,
    page: int = 1,
    region_id: int | None = None,
) -> MatchStatus:
    """Persist vision score internally and update frontend-safe overlay match state."""
    return finalize_inspection_match_from_internal_candidate(
        session,
        inspection_id=inspection_id,
        drawing_id=drawing_id,
        candidate=InternalMatchCandidate(
            score=internal_score,
            bbox=bbox,
            page=page,
            region_id=region_id,
            source="vision_confirmation",
        ),
    )
