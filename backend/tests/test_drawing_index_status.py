"""Tests for Drawing index job status columns (Phase 0c)."""

from __future__ import annotations

from datetime import datetime
from typing import cast

from models.models import Drawing
from services.storage import StorageService


def test_drawing_index_status_defaults_to_pending(db_session, project) -> None:
    storage = StorageService(db_session)
    drawing = storage.create_drawing(
        project_id=cast(int, project.id),
        source="upload",
        name="Master.pdf",
        storage_key="projects/2/drawings/master.pdf",
        content_type="application/pdf",
    )
    drawing_id = cast(int, drawing.id)

    loaded = db_session.get(Drawing, drawing_id)
    assert loaded is not None
    assert loaded.index_status == "pending"
    assert loaded.index_error is None
    assert loaded.indexed_at is None
    assert loaded.index_stats_json is None


def test_drawing_index_status_and_stats_persist(db_session, project) -> None:
    storage = StorageService(db_session)
    drawing = storage.create_drawing(
        project_id=cast(int, project.id),
        source="upload",
        name="Master.pdf",
        storage_key="projects/2/drawings/master.pdf",
        content_type="application/pdf",
    )
    drawing_id = cast(int, drawing.id)

    indexed_at = datetime(2026, 8, 5, 18, 13)
    index_stats_json = {
        "pages": 3,
        "text_elements": 8420,
        "regions": 156,
        "scale_found": True,
    }

    row = db_session.get(Drawing, drawing_id)
    assert row is not None
    setattr(row, "index_status", "ready")
    setattr(row, "index_error", None)
    setattr(row, "indexed_at", indexed_at)
    setattr(row, "index_stats_json", index_stats_json)
    db_session.commit()
    db_session.refresh(row)

    loaded = db_session.get(Drawing, drawing_id)
    assert loaded is not None
    assert loaded.index_status == "ready"
    assert loaded.index_error is None
    assert loaded.indexed_at == indexed_at
    assert loaded.index_stats_json == index_stats_json
    assert loaded.index_stats_json["text_elements"] == 8420
