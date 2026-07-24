"""Tests for inspection run id resolution when linking evidence to runs."""

from __future__ import annotations

import uuid
from typing import cast

import pytest
from sqlalchemy.orm import Session

from models.models import Company, Drawing, EvidenceRecord, Project
from models.inspection_run import InspectionRun
from services.inspection_match_persistence import resolve_inspection_run_id


def _unique() -> str:
    return uuid.uuid4().hex[:12]


@pytest.fixture
def db(db_session: Session) -> Session:
    return db_session


def _seed_collision(db: Session) -> tuple[int, int, int]:
    """Evidence id collides with an older inspection run id (different tables)."""
    target_id = 90000 + int(uuid.uuid4().hex[:4], 16) % 10000

    company = Company(name=f"Co {_unique()}", procore_company_id=f"pc-{_unique()}")
    db.add(company)
    db.flush()

    project = Project(
        company_id=company.id,
        procore_project_id=f"pp-{_unique()}",
        name="Collision Project",
    )
    db.add(project)
    db.flush()

    drawing = Drawing(
        project_id=project.id,
        source="upload",
        name="Site Plan",
        storage_key=f"drawings/{_unique()}.pdf",
    )
    db.add(drawing)
    db.flush()

    old_evidence = EvidenceRecord(
        project_id=project.id,
        type="inspection_doc",
        title="Old evidence",
        storage_key=f"evidence/{_unique()}.pdf",
    )
    db.add(old_evidence)
    db.flush()

    old_run = InspectionRun(
        id=target_id,
        project_id=project.id,
        master_drawing_id=drawing.id,
        evidence_id=old_evidence.id,
        status="complete",
    )
    db.add(old_run)
    db.flush()

    new_evidence = EvidenceRecord(
        id=target_id,
        project_id=project.id,
        type="inspection_doc",
        title="New evidence",
        storage_key=f"evidence/{_unique()}.pdf",
    )
    db.add(new_evidence)
    db.flush()

    new_run = InspectionRun(
        project_id=project.id,
        master_drawing_id=drawing.id,
        evidence_id=new_evidence.id,
        status="complete",
    )
    db.add(new_run)
    db.commit()

    return cast(int, old_run.id), cast(int, new_evidence.id), cast(int, new_run.id)


def test_resolve_prefers_evidence_owner_over_colliding_run_id(db: Session) -> None:
    old_run_id, evidence_id, new_run_id = _seed_collision(db)
    assert old_run_id == evidence_id

    resolved = resolve_inspection_run_id(db, str(evidence_id))
    assert resolved == new_run_id


def test_resolve_honors_explicit_inspection_run_id(db: Session) -> None:
    old_run_id, evidence_id, new_run_id = _seed_collision(db)

    resolved = resolve_inspection_run_id(
        db,
        str(evidence_id),
        inspection_run_id=new_run_id,
    )
    assert resolved == new_run_id

    resolved_old = resolve_inspection_run_id(
        db,
        str(evidence_id),
        inspection_run_id=old_run_id,
    )
    assert resolved_old == old_run_id


def test_resolve_run_id_directly(db: Session) -> None:
    _, _, new_run_id = _seed_collision(db)

    assert resolve_inspection_run_id(db, str(new_run_id)) == new_run_id
