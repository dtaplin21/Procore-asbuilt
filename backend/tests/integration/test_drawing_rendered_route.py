"""Integration tests for the rendered drawing page image route."""


def test_rendered_page_route_returns_png(client, seeded_ready_pdf_drawing):
    drawing = seeded_ready_pdf_drawing

    response = client.get(
        f"/api/projects/{drawing.project_id}/drawings/{drawing.id}/pages/1/image"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
