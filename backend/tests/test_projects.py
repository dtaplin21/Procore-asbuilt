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

from api.upload_intent_form import drawing_has_sub_upload_intent
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
        upload_intent="master",
    )
    response = client.get(f"/api/projects/{pid}/dashboard/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["project"]["masterDrawingId"] == master.id
    assert data["masterDrawing"] is not None
    assert data["masterDrawing"]["id"] == master.id
    assert data["masterDrawing"]["name"] == "master.pdf"


def test_storage_create_drawing_persists_upload_intent_sub(
    db_session, project: Project
) -> None:
    """Explicit sub intent is stored on the drawing row (nullable for legacy)."""
    storage = StorageService(db_session)
    pid = cast(int, project.id)
    drawing = storage.create_drawing(
        pid,
        source="upload",
        name="sub.pdf",
        storage_key=f"drawings/test/{pid}/sub.pdf",
        content_type="application/pdf",
        upload_intent="sub",
    )
    row = (
        db_session.query(Drawing)
        .filter(Drawing.id == cast(int, drawing.id))
        .first()
    )
    assert row is not None
    assert row.upload_intent == "sub"
    assert drawing_has_sub_upload_intent(row) is True


def test_drawing_has_sub_upload_intent_only_matches_literal_sub(project: Project) -> None:
    d_none = Drawing(
        project_id=cast(int, project.id),
        source="upload",
        name="legacy.pdf",
        storage_key="k",
        content_type="application/pdf",
        upload_intent=None,
    )
    d_master = Drawing(
        project_id=cast(int, project.id),
        source="upload",
        name="m.pdf",
        storage_key="k2",
        content_type="application/pdf",
        upload_intent="master",
    )
    assert drawing_has_sub_upload_intent(d_none) is False
    assert drawing_has_sub_upload_intent(d_master) is False


def test_projects_router_upload_persists_upload_intent_sub(
    client: TestClient, project: Project
) -> None:
    """POST /api/projects/{id}/drawings with upload_intent=sub persists sub."""
    pid = cast(int, project.id)
    pdf = _minimal_pdf_bytes()
    files = {"file": ("sub_sheet.pdf", io.BytesIO(pdf), "application/pdf")}
    data = {"upload_intent": "sub"}
    response = client.post(f"/api/projects/{pid}/drawings", files=files, data=data)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("upload_intent") == "sub"


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
        upload_intent="master",
    )
    db_session.refresh(project)
    assert project.master_drawing_id == master.id

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
        name="old-master.pdf",
        storage_key=f"drawings/test/{pid}/old.pdf",
        content_type="application/pdf",
        upload_intent="master",
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
