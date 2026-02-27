from fastapi.testclient import TestClient

"""Basic API tests for project-related endpoints.

Importing ``app`` requires ensuring the ``backend`` package is on sys.path.  The
most reliable way in a pytest environment is to import via the package
namespace rather than relying on the current working directory.
"""

from backend.main import app

client = TestClient(app)


def test_dashboard_summary_returns_404_when_missing():
    # use a project id that is extremely unlikely to exist
    response = client.get("/api/projects/999999/dashboard/summary")
    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found"}
