"""Tests for inspection run progress updates."""

from __future__ import annotations

import uuid
from typing import cast

from sqlalchemy.orm import Session

from models.inspection_run import InspectionRun
from models.models import Drawing, EvidenceRecord, Project
from services.inspection_run_progress import (
    InspectionProgressHandle,
    get_run_progress,
)


def _seed_run(db: Session, project: Project) -> InspectionRun:
    suffix = uuid.uuid4().hex[:8]
    project_id = cast(int, project.id)
    drawing = Drawing(
        project_id=project_id,
        source="upload",
        name="Master",
        storage_key=f"drawings/{suffix}.pdf",
    )
    db.add(drawing)
    db.flush()
    evidence = EvidenceRecord(
        project_id=project_id,
        type="inspection_doc",
        title="Inspection",
        storage_key=f"evidence/{suffix}.pdf",
    )
    db.add(evidence)
    db.flush()
    run = InspectionRun(
        project_id=project_id,
        master_drawing_id=drawing.id,
        evidence_id=evidence.id,
        status="processing",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def test_progress_reading_page_updates_json(db_session: Session, project: Project) -> None:
    run = _seed_run(db_session, project)
    handle = InspectionProgressHandle(
        db_session,
        run_id=cast(int, run.id),
        job_id=99,
        mode="index",
    )
    handle.start()
    handle.set_reading_page(3, 12)

    payload = get_run_progress(
        db_session,
        project_id=cast(int, project.id),
        run_id=cast(int, run.id),
    )
    assert payload is not None
    assert payload["current"]["page"] == 3
    assert payload["current"]["page_total"] == 12
    assert "Reading page 3 of 12" in payload["current"]["label"]


def test_index_finish_label_is_indexed(db_session: Session, project: Project) -> None:
    run = _seed_run(db_session, project)
    handle = InspectionProgressHandle(
        db_session,
        run_id=cast(int, run.id),
        job_id=407,
        mode="index",
    )
    handle.finish()
    payload = get_run_progress(
        db_session,
        project_id=cast(int, project.id),
        run_id=cast(int, run.id),
    )
    assert payload is not None
    assert payload["current"]["label"] == "Indexed"
    assert payload["mode"] == "index"
