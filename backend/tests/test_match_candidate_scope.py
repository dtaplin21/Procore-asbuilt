"""Tests for sheet-ref match scope narrowing."""

from __future__ import annotations

from typing import cast

import pytest
from sqlalchemy.orm import Session

from models.models import Drawing, EvidenceRecord
from services.match_candidate_scope import build_match_scope


@pytest.fixture
def master_drawing(db_session: Session, project) -> Drawing:
    drawing = Drawing(
        project_id=project.id,
        source="upload",
        name="Master.pdf",
        storage_key=None,
        content_type="application/pdf",
    )
    db_session.add(drawing)
    db_session.commit()
    db_session.refresh(drawing)
    return drawing


@pytest.fixture
def auxiliary_c420_drawing(db_session: Session, project) -> Drawing:
    drawing = Drawing(
        project_id=project.id,
        source="upload",
        name="U1.C4.20.pdf",
        storage_key=None,
        content_type="application/pdf",
    )
    db_session.add(drawing)
    db_session.commit()
    db_session.refresh(drawing)
    return drawing


def test_build_match_scope_resolves_c420_from_linked_supplemental_text(
    db_session: Session,
    project,
    master_drawing: Drawing,
    auxiliary_c420_drawing: Drawing,
) -> None:
    supplemental = "Install sheet U1.C4.20 sanitary sewer corridor coordinates."
    base = "Inspection report header only."
    evidence = EvidenceRecord(
        project_id=project.id,
        type="inspection_doc",
        title="inspection.pdf",
        text_content=f"{supplemental}\n{base}",
    )
    db_session.add(evidence)
    db_session.commit()
    db_session.refresh(evidence)

    scope = build_match_scope(
        db_session,
        evidence_id=cast(int, evidence.id),
        master_drawing_id=cast(int, master_drawing.id),
    )

    assert "C4.20" in scope.sheet_refs or "U1.C4.20" in scope.sheet_refs
    assert cast(int, auxiliary_c420_drawing.id) in scope.auxiliary_drawing_ids
    assert scope.master_drawing_id == cast(int, master_drawing.id)


def test_build_match_scope_finds_sheet_ref_after_char_2000(
    db_session: Session,
    project,
    master_drawing: Drawing,
    auxiliary_c420_drawing: Drawing,
) -> None:
    padding = "x" * 2100
    evidence = EvidenceRecord(
        project_id=project.id,
        type="inspection_doc",
        title="inspection.pdf",
        text_content=f"{padding} SEE SHEET U1.C4.20 FOR LOCATION",
    )
    db_session.add(evidence)
    db_session.commit()
    db_session.refresh(evidence)

    scope = build_match_scope(
        db_session,
        evidence_id=cast(int, evidence.id),
        master_drawing_id=cast(int, master_drawing.id),
    )

    assert any("C4.20" in ref for ref in scope.sheet_refs)
    assert cast(int, auxiliary_c420_drawing.id) in scope.auxiliary_drawing_ids


def test_build_match_scope_empty_when_no_sheet_refs(
    db_session: Session,
    project,
    master_drawing: Drawing,
) -> None:
    evidence = EvidenceRecord(
        project_id=project.id,
        type="inspection_doc",
        title="photo.jpg",
        text_content="Field photo with no sheet references.",
    )
    db_session.add(evidence)
    db_session.commit()
    db_session.refresh(evidence)

    scope = build_match_scope(
        db_session,
        evidence_id=cast(int, evidence.id),
        master_drawing_id=cast(int, master_drawing.id),
    )

    assert scope.sheet_refs == ()
    assert scope.auxiliary_drawing_ids == ()
