"""Tests for drawing inspection reviews (alignment and inspection-run scope)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import cast

import pytest
from sqlalchemy.orm import Session

from database import SessionLocal
from models.models import (
    Company,
    Drawing,
    DrawingRegion,
    EvidenceRecord,
    InspectionRun,
    Project,
)
from services.storage import StorageService


def _unique_id() -> str:
    return uuid.uuid4().hex[:12]


@pytest.fixture
def db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def company(db: Session) -> Company:
    row = Company(name="Test Co", procore_company_id=f"pc-{_unique_id()}")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def project(db: Session, company: Company) -> Project:
    row = Project(
        company_id=company.id,
        name="Test Project",
        procore_project_id=f"pp-{_unique_id()}",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def master_drawing(db: Session, project: Project) -> Drawing:
    row = Drawing(
        project_id=project.id,
        source="upload",
        name="master.pdf",
        storage_key=None,
        content_type="application/pdf",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def drawing_region(db: Session, master_drawing: Drawing) -> DrawingRegion:
    row = DrawingRegion(
        master_drawing_id=master_drawing.id,
        label="Zone A",
        page=1,
        geometry={"type": "rect", "x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def evidence_record(db: Session, project: Project) -> EvidenceRecord:
    row = EvidenceRecord(
        project_id=project.id,
        type="inspection_doc",
        title="Inspection doc",
        trade="hvac",
        storage_key=None,
        content_type="application/pdf",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def inspection_run(
    db: Session,
    project: Project,
    master_drawing: Drawing,
    evidence_record: EvidenceRecord,
) -> InspectionRun:
    storage = StorageService(db)
    return storage.create_inspection_run(
        project_id=cast(int, project.id),
        master_drawing_id=cast(int, master_drawing.id),
        evidence_id=cast(int, evidence_record.id),
        inspection_type=None,
    )


def test_create_and_list_review_for_inspection_run(
    db: Session,
    project: Project,
    inspection_run: InspectionRun,
    drawing_region: DrawingRegion,
) -> None:
    storage = StorageService(db)
    project_id = cast(int, project.id)
    run_id = cast(int, inspection_run.id)

    row = storage.create_drawing_inspection_review(
        project_id=project_id,
        inspection_run_id=run_id,
        outcome="passed",
        region_id=cast(int, drawing_region.id),
        notes="Looks good",
    )

    assert row.alignment_id is None
    assert cast(int, row.inspection_run_id) == run_id
    assert row.status == "passed"

    rows = storage.list_drawing_inspection_reviews(
        project_id=project_id,
        inspection_run_id=run_id,
    )
    assert len(rows) == 1
    assert cast(int, rows[0].id) == cast(int, row.id)


def test_create_review_rejects_wrong_project_run(
    db: Session,
    project: Project,
    inspection_run: InspectionRun,
) -> None:
    storage = StorageService(db)
    other = Project(
        company_id=project.company_id,
        name="Other",
        procore_project_id=f"pp-{_unique_id()}",
    )
    db.add(other)
    db.commit()
    db.refresh(other)

    with pytest.raises(ValueError, match="Inspection run not found"):
        storage.create_drawing_inspection_review(
            project_id=cast(int, other.id),
            inspection_run_id=cast(int, inspection_run.id),
            outcome="failed",
        )


def test_create_review_requires_exactly_one_scope(db: Session, project: Project) -> None:
    storage = StorageService(db)
    with pytest.raises(ValueError, match="Exactly one"):
        storage.create_drawing_inspection_review(
            project_id=cast(int, project.id),
            outcome="passed",
        )
