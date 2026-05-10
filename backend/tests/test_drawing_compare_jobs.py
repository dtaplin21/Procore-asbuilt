"""Tests for drawing_compare JobQueue enqueue helper."""

from __future__ import annotations

from typing import cast

import fitz
from sqlalchemy.orm import Session

from models.models import Drawing, Project
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
        upload_intent="master",
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
    """Sole explicit sub upload does not set master; no fallback master row → no enqueue."""
    storage = StorageService(db_session)
    pid = cast(int, project.id)
    sub = storage.create_drawing(
        pid,
        source="upload",
        name="s.pdf",
        storage_key=f"drawings/test/{pid}/s.pdf",
        content_type="application/pdf",
        upload_intent="sub",
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
        upload_intent="master",
    )
    sub = storage.create_drawing(
        pid,
        source="upload",
        name="s2.pdf",
        storage_key=f"drawings/test/{pid}/s2.pdf",
        content_type="application/pdf",
        upload_intent="sub",
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
    for name, key_suffix, intent in (
        ("m.pdf", "mrend.pdf", "master"),
        ("s.pdf", "srend.pdf", "sub"),
    ):
        path = f"drawings/test/{pid}/{key_suffix}"
        abs_path = UPLOAD_ROOT / path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(pdf)
        storage.create_drawing(
            pid,
            source="upload",
            name=name,
            storage_key=path,
            content_type="application/pdf",
            upload_intent="sub" if intent == "sub" else "master",
        )

    drawings = (
        db_session.query(Drawing)
        .filter(Drawing.project_id == pid)
        .order_by(Drawing.id.asc())
        .all()
    )
    assert len(drawings) == 2
    master_d, sub_d = drawings[0], drawings[1]
    assert master_d.upload_intent == "master"
    assert sub_d.upload_intent == "sub"

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
    for name, key_suffix, intent in (
        ("m.pdf", "midem.pdf", "master"),
        ("s.pdf", "sidem.pdf", "sub"),
    ):
        path = f"drawings/test/{pid}/{key_suffix}"
        abs_path = UPLOAD_ROOT / path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(pdf)
        storage.create_drawing(
            pid,
            source="upload",
            name=name,
            storage_key=path,
            content_type="application/pdf",
            upload_intent="sub" if intent == "sub" else "master",
        )

    drawings = (
        db_session.query(Drawing)
        .filter(Drawing.project_id == pid)
        .order_by(Drawing.id.asc())
        .all()
    )
    master_d, sub_d = drawings[0], drawings[1]
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
    assert j1.id == j2.id
