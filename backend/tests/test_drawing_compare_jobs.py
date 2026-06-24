"""Tests for drawing_compare JobQueue enqueue helper."""

from __future__ import annotations

from typing import cast

import fitz
from sqlalchemy.orm import Session

from models.models import Drawing, JobQueue, Project
from services.drawing_rendering import DrawingRenderingService
from services.storage import StorageService, UPLOAD_ROOT
from services.drawing_compare_jobs import (
    DRAWING_COMPARE_JOB_TYPE,
    enqueue_drawing_compare_job,
)


def _minimal_pdf_bytes() -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    page.insert_text((50, 100), "x")
    out = doc.tobytes()
    doc.close()
    return out


def _insert_legacy_sub_drawing(
    db_session: Session,
    project_id: int,
    *,
    name: str,
    storage_key: str,
) -> Drawing:
    drawing = Drawing(
        project_id=project_id,
        source="upload",
        name=name,
        storage_key=storage_key,
        content_type="application/pdf",
        upload_intent="sub",
    )
    db_session.add(drawing)
    db_session.commit()
    db_session.refresh(drawing)
    return drawing


def test_enqueue_compare_returns_none_when_sub_id_is_master_row(
    db_session: Session, project: Project
) -> None:
    storage = StorageService(db_session)
    pid = cast(int, project.id)
    master = storage.create_drawing(
        pid,
        source="upload",
        name="m.pdf",
        storage_key=f"drawings/test/{pid}/m.pdf",
        content_type="application/pdf",
    )
    assert (
        enqueue_drawing_compare_job(
            db_session, project_id=pid, sub_drawing_id=cast(int, master.id)
        )
        is None
    )


def test_enqueue_compare_returns_none_without_canonical_master(
    db_session: Session, project: Project
) -> None:
    """Legacy sub row with no project master FK → no enqueue."""
    pid = cast(int, project.id)
    sub = _insert_legacy_sub_drawing(
        db_session,
        pid,
        name="s.pdf",
        storage_key=f"drawings/test/{pid}/s.pdf",
    )
    db_session.refresh(project)
    assert project.master_drawing_id is None
    assert (
        enqueue_drawing_compare_job(
            db_session, project_id=pid, sub_drawing_id=cast(int, sub.id)
        )
        is None
    )


def test_enqueue_compare_returns_none_when_renditions_not_ready(
    db_session: Session, project: Project
) -> None:
    storage = StorageService(db_session)
    pid = cast(int, project.id)
    storage.create_drawing(
        pid,
        source="upload",
        name="m.pdf",
        storage_key=f"drawings/test/{pid}/m2.pdf",
        content_type="application/pdf",
    )
    sub = _insert_legacy_sub_drawing(
        db_session,
        pid,
        name="s2.pdf",
        storage_key=f"drawings/test/{pid}/s2.pdf",
    )
    assert (
        enqueue_drawing_compare_job(
            db_session, project_id=pid, sub_drawing_id=cast(int, sub.id)
        )
        is None
    )


def test_enqueue_compare_creates_job_when_renditions_ready(
    db_session: Session, project: Project, company
) -> None:
    """After page-1 renditions exist for master and sub, job is queued with int input_data only."""
    # JobQueue requires a user in the same company as the project
    from models.models import User, UserCompany

    user = User(email=f"compare-test-{project.id}@example.com")
    db_session.add(user)
    db_session.flush()
    db_session.add(
        UserCompany(user_id=cast(int, user.id), company_id=cast(int, company.id))
    )
    db_session.commit()

    storage = StorageService(db_session)
    pid = cast(int, project.id)
    pdf = _minimal_pdf_bytes()
    for name, key_suffix in (
        ("m.pdf", "mrend.pdf"),
        ("s.pdf", "srend.pdf"),
    ):
        path = f"drawings/test/{pid}/{key_suffix}"
        abs_path = UPLOAD_ROOT / path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(pdf)

    master_d = storage.create_drawing(
        pid,
        source="upload",
        name="m.pdf",
        storage_key=f"drawings/test/{pid}/mrend.pdf",
        content_type="application/pdf",
    )
    sub_d = _insert_legacy_sub_drawing(
        db_session,
        pid,
        name="s.pdf",
        storage_key=f"drawings/test/{pid}/srend.pdf",
    )
    assert cast(str | None, master_d.upload_intent) == "master"
    assert cast(str | None, sub_d.upload_intent) == "sub"

    render = DrawingRenderingService(db_session)
    render.render_drawing_pages(cast(int, master_d.id))
    render.render_drawing_pages(cast(int, sub_d.id))

    job = enqueue_drawing_compare_job(
        db_session, project_id=pid, sub_drawing_id=cast(int, sub_d.id)
    )
    assert job is not None
    assert cast(str, job.job_type) == DRAWING_COMPARE_JOB_TYPE
    assert cast(str, job.status) == "pending"
    data = cast(dict, job.input_data)
    assert data["project_id"] == pid
    assert data["master_drawing_id"] == master_d.id
    assert data["sub_drawing_id"] == sub_d.id
    assert data["renditions_ready"] is True


def test_enqueue_compare_idempotent_pending(
    db_session: Session, project: Project, company
) -> None:
    from models.models import User, UserCompany

    user = User(email=f"compare-idem-{project.id}@example.com")
    db_session.add(user)
    db_session.flush()
    db_session.add(
        UserCompany(user_id=cast(int, user.id), company_id=cast(int, company.id))
    )
    db_session.commit()

    storage = StorageService(db_session)
    pid = cast(int, project.id)
    pdf = _minimal_pdf_bytes()
    for key_suffix in ("midem.pdf", "sidem.pdf"):
        path = f"drawings/test/{pid}/{key_suffix}"
        abs_path = UPLOAD_ROOT / path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(pdf)

    master_d = storage.create_drawing(
        pid,
        source="upload",
        name="m.pdf",
        storage_key=f"drawings/test/{pid}/midem.pdf",
        content_type="application/pdf",
    )
    sub_d = _insert_legacy_sub_drawing(
        db_session,
        pid,
        name="s.pdf",
        storage_key=f"drawings/test/{pid}/sidem.pdf",
    )
    render = DrawingRenderingService(db_session)
    render.render_drawing_pages(cast(int, master_d.id))
    render.render_drawing_pages(cast(int, sub_d.id))

    j1 = enqueue_drawing_compare_job(
        db_session, project_id=pid, sub_drawing_id=cast(int, sub_d.id)
    )
    j2 = enqueue_drawing_compare_job(
        db_session, project_id=pid, sub_drawing_id=cast(int, sub_d.id)
    )
    assert j1 is not None and j2 is not None
    assert cast(int, j1.id) == cast(int, j2.id)


def test_render_complete_does_not_auto_enqueue_compare(
    db_session: Session, project: Project, company
) -> None:
    """Upload/render path no longer chains into drawing_compare (PR 4.3)."""
    from models.models import User, UserCompany

    user = User(email=f"compare-nchain-{project.id}@example.com")
    db_session.add(user)
    db_session.flush()
    db_session.add(
        UserCompany(user_id=cast(int, user.id), company_id=cast(int, company.id))
    )
    db_session.commit()

    storage = StorageService(db_session)
    pid = cast(int, project.id)
    pdf = _minimal_pdf_bytes()
    for key_suffix in ("mfan.pdf", "sfan.pdf"):
        path = f"drawings/test/{pid}/{key_suffix}"
        abs_path = UPLOAD_ROOT / path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(pdf)

    master_d = storage.create_drawing(
        pid,
        source="upload",
        name="m.pdf",
        storage_key=f"drawings/test/{pid}/mfan.pdf",
        content_type="application/pdf",
    )
    sub_d = _insert_legacy_sub_drawing(
        db_session,
        pid,
        name="s.pdf",
        storage_key=f"drawings/test/{pid}/sfan.pdf",
    )
    render = DrawingRenderingService(db_session)
    render.render_drawing_pages(cast(int, sub_d.id))
    render.render_drawing_pages(cast(int, master_d.id))

    assert (
        db_session.query(JobQueue)
        .filter(
            JobQueue.project_id == pid,
            JobQueue.job_type == DRAWING_COMPARE_JOB_TYPE,
        )
        .count()
        == 0
    )
