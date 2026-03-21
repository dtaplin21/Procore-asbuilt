"""Integration tests for workspace drawing endpoint (rendered file URL)."""


def test_workspace_returns_rendered_file_url(client, seeded_ready_pdf_drawing):
    """GET /api/projects/{id}/drawings/{id} returns rendition URL when ready."""
    drawing = seeded_ready_pdf_drawing

    response = client.get(
        f"/api/projects/{drawing.project_id}/drawings/{drawing.id}"
    )

    assert response.status_code == 200

    payload = response.json()
    assert "/pages/1/image" in payload["fileUrl"]
    assert payload["sourceFileUrl"].endswith("/file")
