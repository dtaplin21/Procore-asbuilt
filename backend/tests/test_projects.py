from typing import cast

from fastapi.testclient import TestClient

"""Basic API tests for project-related endpoints.

Importing ``app`` requires ensuring the ``backend`` package is on sys.path.  The
most reliable way in a pytest environment is to import via the package
namespace rather than relying on the current working directory.
"""

from models.models import Project
from services.storage import StorageService


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
