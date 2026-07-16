"""Tests for backend-only document review queue."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import cast

import pytest
from sqlalchemy.orm import Session

from database import SessionLocal
from models.review_queue_item import ReviewQueueItem
from services.review_queue import add_to_review_queue


def _unique_file_id() -> str:
    return f"evidence-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def test_add_to_review_queue_persists_row(db: Session) -> None:
    file_id = _unique_file_id()

    item = add_to_review_queue(
        db,
        file_id=file_id,
        reason="low_confidence_classification",
        document_type_guess="inspection_report",
        confidence=0.42,
    )

    assert item.id is not None
    assert cast(str, item.file_id) == file_id
    assert cast(str, item.reason) == "low_confidence_classification"
    assert cast(str | None, item.document_type_guess) == "inspection_report"
    assert cast(float | None, item.classification_confidence) == 0.42
    assert cast(bool, item.resolved) is False
    assert item.created_at is not None

    stored = db.query(ReviewQueueItem).filter_by(id=cast(int, item.id)).one()
    assert cast(str, stored.file_id) == file_id


def test_add_to_review_queue_without_commit_uses_flush(db: Session) -> None:
    file_id = _unique_file_id()

    item = add_to_review_queue(
        db,
        file_id=file_id,
        reason="extraction_validation_failed",
        commit=False,
    )

    assert item.id is not None
    pending = db.query(ReviewQueueItem).filter_by(id=cast(int, item.id)).one()
    assert cast(str, pending.reason) == "extraction_validation_failed"
