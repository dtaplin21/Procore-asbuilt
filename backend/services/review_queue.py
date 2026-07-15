"""Persist files that need human review after classification or extraction failures."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from models.review_queue_item import ReviewQueueItem


def add_to_review_queue(
    session: Session,
    file_id: str,
    reason: str,
    document_type_guess: Optional[str] = None,
    confidence: Optional[float] = None,
    *,
    commit: bool = True,
) -> ReviewQueueItem:
    item = ReviewQueueItem(
        file_id=file_id,
        reason=reason,
        document_type_guess=document_type_guess,
        classification_confidence=confidence,
    )

    session.add(item)
    if commit:
        session.commit()
        session.refresh(item)
    else:
        session.flush()
        session.refresh(item)

    return item
