import io
from typing import cast

from datetime import datetime, timezone

import fitz
from fastapi.testclient import TestClient

"""Basic API tests for project-related endpoints.

Importing ``app`` requires ensuring the ``backend`` package is on sys.path.  The
most reliable way in a pytest environment is to import via the package
namespace rather than relying on the current working directory.
"""

from models.models import Drawing, Project
from services.storage import StorageService, get_project_master_drawing


def _minimal_pdf_bytes() -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    page.insert_text((50, 100), "P0")
    out = doc.tobytes()
    doc.close()
    return out


def test_dashboard_summary_returns_404_when_missing(client: TestClient) -> None:
    # use a project id that is extremely unlikely to exist
    response = client.get("/api/projects/999999/dashboard/summary")
    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found"}


def test_dashboard_summary_includes_master_drawing_id(
    client: TestClient, db_session, project: Project
) -> None:
    """GET /dashboard/summary exposes canonical master as project.masterDrawingId and masterDrawing."""
    storage = StorageService(db_session)
    pid = cast(int, project.id)
    master = storage.create_drawing(
        pid,
        source="upload",
        name="master.pdf",
        storage_key=f"drawings/test/{pid}/master.pdf",
        content_type="application/pdf",
    )
    response = client.get(f"/api/projects/{pid}/dashboard/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["project"]["masterDrawingId"] == master.id
    assert data["masterDrawing"] is not None
    assert data["masterDrawing"]["id"] == master.id
    assert data["masterDrawing"]["name"] == "master.pdf"


def test_create_drawing_always_sets_upload_intent_master(
    db_session, project: Project
) -> None:
    storage = StorageService(db_session)
    pid = cast(int, project.id)
    drawing = storage.create_drawing(
        pid,
        source="upload",
        name="sheet.pdf",
        storage_key=f"drawings/test/{pid}/sheet.pdf",
        content_type="application/pdf",
    )
    row = (
        db_session.query(Drawing)
        .filter(Drawing.id == cast(int, drawing.id))
        .first()
    )
    assert row is not None
    assert cast(str | None, row.upload_intent) == "master"
    db_session.refresh(project)
    assert cast(int | None, project.master_drawing_id) == cast(int, drawing.id)


def test_projects_router_upload_always_sets_master(
    client: TestClient, db_session, project: Project
) -> None:
    """POST /api/projects/{id}/drawings always creates a master drawing (upload_intent ignored)."""
    pid = cast(int, project.id)
    pdf = _minimal_pdf_bytes()
    files = {"file": ("sub_sheet.pdf", io.BytesIO(pdf), "application/pdf")}
    data = {"upload_intent": "sub"}
    response = client.post(f"/api/projects/{pid}/drawings", files=files, data=data)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("upload_intent") == "master"
    db_session.refresh(project)
    assert cast(int | None, project.master_drawing_id) == body["id"]


def test_get_project_master_drawing_prefers_project_master_drawing_id(
    db_session, project: Project
) -> None:
    """Canonical master is ``projects.master_drawing_id`` when set."""
    storage = StorageService(db_session)
    pid = cast(int, project.id)
    master = storage.create_drawing(
        pid,
        source="upload",
        name="master.pdf",
        storage_key=f"drawings/test/{pid}/m1.pdf",
        content_type="application/pdf",
    )
    db_session.refresh(project)
    assert cast(int | None, project.master_drawing_id) == cast(int, master.id)

    got = storage.get_project_master_drawing(pid)
    assert got is not None and cast(int, got.id) == cast(int, master.id)

    got_fn = get_project_master_drawing(db_session, pid)
    assert got_fn is not None and cast(int, got_fn.id) == cast(int, master.id)


def test_get_project_master_drawing_fallback_newest_upload_intent_master(
    db_session, project: Project
) -> None:
    """When FK is unset, use ``upload_intent == 'master'`` (newest ``updated_at``)."""
    pid = cast(int, project.id)
    older = Drawing(
        project_id=pid,
        source="upload",
        name="old-sheet.pdf",
        storage_key=f"drawings/test/{pid}/old.pdf",
        content_type="application/pdf",
        upload_intent=None,
        processing_status="pending",
        updated_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    newer = Drawing(
        project_id=pid,
        source="upload",
        name="new-master.pdf",
        storage_key=f"drawings/test/{pid}/new.pdf",
        content_type="application/pdf",
        upload_intent="master",
        processing_status="pending",
        updated_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
    )
    db_session.add_all([older, newer])
    db_session.commit()
    db_session.refresh(project)
    assert project.master_drawing_id is None

    storage = StorageService(db_session)
    got = storage.get_project_master_drawing(pid)
    assert got is not None
    assert cast(int, got.id) == cast(int, newer.id)
