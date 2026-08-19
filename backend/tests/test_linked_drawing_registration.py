"""Tests for linked install-sheet PDF registration."""

from __future__ import annotations

from typing import cast

import pytest
from sqlalchemy.orm import Session

from ai.pipelines.pdf_link_follower import FetchedLinkedPdf, LinkFollowResult
from models.models import Drawing, EvidenceDrawingLink, EvidenceRecord, InspectionRun, JobQueue
from services.drawing_render_jobs import DRAWING_RENDER_JOB_TYPE
from services.evidence_linking import replace_evidence_drawing_links
from services.linked_drawing_registration import register_linked_pdfs_as_auxiliary_drawings
from services.match_candidate_scope import build_match_scope
from services.storage import StorageService


def _c420_pdf_bytes() -> bytes:
    return b"%PDF-1.4 minimal"


def _link_result() -> LinkFollowResult:
    return LinkFollowResult(
        supplemental_text="N 2131764.84 E 6051541.82",
        fetched_pdfs=[
            FetchedLinkedPdf(
                url="https://app.procore.com/doc.pdf",
                filename="7.20-7.24 U1.C4.20 6.00 Sanitary Sewer Install.pdf",
                body=_c420_pdf_bytes(),
                pages=1,
                content_type="application/pdf",
                text="Sheet U1.C4.20 Northing 2131764.84 Easting 6051541.82",
            )
        ],
    )


def test_register_linked_pdf_creates_auxiliary_drawing(
    db_session: Session,
    project,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services import file_storage

    monkeypatch.setattr(file_storage, "BASE_UPLOAD_DIR", tmp_path)

    master = Drawing(
        project_id=project.id,
        source="upload",
        name="Master.pdf",
        storage_key="drawings/master.pdf",
        content_type="application/pdf",
    )
    db_session.add(master)
    db_session.commit()
    db_session.refresh(master)
    StorageService(db_session).set_project_master(cast(int, project.id), cast(int, master.id))

    drawing_ids = register_linked_pdfs_as_auxiliary_drawings(
        db_session,
        project_id=cast(int, project.id),
        link_result=_link_result(),
    )

    assert len(drawing_ids) == 1
    auxiliary = db_session.get(Drawing, drawing_ids[0])
    assert auxiliary is not None
    assert auxiliary.original_filename == "7.20-7.24 U1.C4.20 6.00 Sanitary Sewer Install.pdf"
    assert auxiliary.source == "linked_evidence"
    assert cast(int, project.master_drawing_id) == cast(int, master.id)

    render_jobs = (
        db_session.query(JobQueue)
        .filter(
            JobQueue.project_id == project.id,
            JobQueue.job_type == DRAWING_RENDER_JOB_TYPE,
        )
        .all()
    )
    assert len(render_jobs) == 1


def test_register_linked_pdf_dedupes_existing_drawing(
    db_session: Session,
    project,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services import file_storage

    monkeypatch.setattr(file_storage, "BASE_UPLOAD_DIR", tmp_path)

    existing = Drawing(
        project_id=project.id,
        source="upload",
        name="U1.C4.20.pdf",
        original_filename="7.20-7.24 U1.C4.20 6.00 Sanitary Sewer Install.pdf",
        storage_key="drawings/c420.pdf",
        content_type="application/pdf",
    )
    db_session.add(existing)
    db_session.commit()
    db_session.refresh(existing)

    drawing_ids = register_linked_pdfs_as_auxiliary_drawings(
        db_session,
        project_id=cast(int, project.id),
        link_result=_link_result(),
    )

    assert drawing_ids == [cast(int, existing.id)]
    assert db_session.query(Drawing).filter(Drawing.project_id == project.id).count() == 1


def test_linked_registration_enables_match_scope(
    db_session: Session,
    project,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services import file_storage

    monkeypatch.setattr(file_storage, "BASE_UPLOAD_DIR", tmp_path)

    master = Drawing(
        project_id=project.id,
        source="upload",
        name="Master.pdf",
        storage_key="drawings/master.pdf",
        content_type="application/pdf",
    )
    db_session.add(master)
    db_session.commit()
    db_session.refresh(master)
    StorageService(db_session).set_project_master(cast(int, project.id), cast(int, master.id))

    evidence = EvidenceRecord(
        project_id=project.id,
        type="inspection_doc",
        title="inspection.pdf",
        text_content="See U1.C4.20 for coordinates.",
    )
    db_session.add(evidence)
    db_session.commit()
    db_session.refresh(evidence)

    register_linked_pdfs_as_auxiliary_drawings(
        db_session,
        project_id=cast(int, project.id),
        link_result=_link_result(),
    )
    replace_evidence_drawing_links(db_session, evidence, commit=True)

    scope = build_match_scope(
        db_session,
        evidence_id=cast(int, evidence.id),
        master_drawing_id=cast(int, master.id),
    )

    assert scope.auxiliary_drawing_ids
    links = (
        db_session.query(EvidenceDrawingLink)
        .filter(EvidenceDrawingLink.evidence_id == evidence.id)
        .all()
    )
    assert len(links) >= 1
