"""Shared pytest fixtures for backend tests."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from database import SessionLocal
from models.models import Company, Drawing, Project
from services.storage import (
    UPLOAD_ROOT,
    build_drawing_source_storage_key,
    ensure_parent_dir,
)


def _unique_id() -> str:
    return uuid.uuid4().hex[:12]


@pytest.fixture
def db_session() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def company(db_session: Session) -> Company:
    c = Company(name="Test Co", procore_company_id=f"pc-{_unique_id()}")
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


@pytest.fixture
def project(db_session: Session, company: Company) -> Project:
    p = Project(
        company_id=company.id,
        name="Test Project",
        procore_project_id=f"pp-{_unique_id()}",
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


def _create_minimal_pdf() -> bytes:
    """Create a minimal valid PDF using PyMuPDF."""
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    page.insert_text((50, 100), "Test PDF")
    pdf_bytes = doc.write_tobytes()
    doc.close()
    return pdf_bytes


@pytest.fixture
def sample_pdf_drawing(db_session: Session, project: Project) -> Drawing:
    """Create a drawing with a real PDF file on disk for unit tests."""
    drawing = Drawing(
        project_id=project.id,
        source="upload",
        name="sample.pdf",
        storage_key=None,
        content_type="application/pdf",
        processing_status="pending",
    )
    db_session.add(drawing)
    db_session.commit()
    db_session.refresh(drawing)

    storage_key = build_drawing_source_storage_key(
        project.id, drawing.id, "sample.pdf"
    )
    abs_path = UPLOAD_ROOT / storage_key
    ensure_parent_dir(abs_path)
    pdf_bytes = _create_minimal_pdf()
    abs_path.write_bytes(pdf_bytes)

    drawing.storage_key = storage_key
    db_session.add(drawing)
    db_session.commit()
    db_session.refresh(drawing)

    return drawing


@pytest.fixture
def seeded_ready_pdf_drawing(
    db_session: Session, project: Project, sample_pdf_drawing: Drawing
) -> Drawing:
    """Drawing with renditions already rendered (for integration tests)."""
    from services.drawing_rendering import DrawingRenderingService

    service = DrawingRenderingService(db_session)
    service.render_drawing_pages(sample_pdf_drawing.id)

    db_session.refresh(sample_pdf_drawing)
    return sample_pdf_drawing


@pytest.fixture
def client():
    """FastAPI TestClient for integration tests."""
    from fastapi.testclient import TestClient

    from main import app

    return TestClient(app)
