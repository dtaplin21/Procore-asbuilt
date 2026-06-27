"""
Tests for PR2 region CRUD: POST/GET/PATCH/DELETE on
api/routes/drawing_regions.py, backed by region_storage.py — exercised
through the real FastAPI TestClient and Postgres (via conftest fixtures).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, cast

import pytest

from models.drawing_overlay import DrawingOverlay
from models.drawing_region import DrawingRegion
from models.models import Drawing, EvidenceRecord
from services.region_storage import get_drawing_region
from services.storage import StorageService


def _regions_base(project_id: int, master_drawing_id: int) -> str:
    return f"/api/projects/{project_id}/drawings/{master_drawing_id}/regions"


def _create_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "label": "Roof",
        "page": 1,
        "geometry": {"type": "rect", "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
        "inspection_type_tags": ["Final"],
        "location_tags": ["Roof"],
    }
    payload.update(overrides)
    return payload


def _post_region(client, url: str, payload: dict[str, Any]) -> Any:
    return client.post(
        url,
        json=payload,
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )


class TestCreateRegion:
    def test_create_returns_201_with_persisted_fields(
        self, client, db_session, project, sample_pdf_drawing
    ) -> None:
        project_id = cast(int, project.id)
        master_id = cast(int, sample_pdf_drawing.id)
        url = _regions_base(project_id, master_id)

        response = _post_region(client, url, _create_payload())
        assert response.status_code == 201
        body = response.json()
        assert body["master_drawing_id"] == master_id
        assert body["label"] == "Roof"
        assert body["geometry"]["x"] == pytest.approx(0.1)
        assert body["inspection_type_tags"] == ["Final"]
        assert body["location_tags"] == ["Roof"]
        assert body["polygon_points"] is None

        row = db_session.query(DrawingRegion).filter_by(id=body["id"]).one()
        assert row.master_drawing_id == master_id

    def test_create_with_polygon_points(
        self, client, project, sample_pdf_drawing
    ) -> None:
        project_id = cast(int, project.id)
        master_id = cast(int, sample_pdf_drawing.id)
        payload = _create_payload(
            polygon_points=[[0.1, 0.2], [0.4, 0.2], [0.4, 0.5], [0.1, 0.5]],
        )

        response = _post_region(client, _regions_base(project_id, master_id), payload)
        assert response.status_code == 201
        assert response.json()["polygon_points"] == [
            [0.1, 0.2],
            [0.4, 0.2],
            [0.4, 0.5],
            [0.1, 0.5],
        ]

    def test_create_rejects_non_positive_width(
        self, client, project, sample_pdf_drawing
    ) -> None:
        project_id = cast(int, project.id)
        master_id = cast(int, sample_pdf_drawing.id)
        payload = _create_payload(
            geometry={"type": "rect", "x": 0.1, "y": 0.2, "width": 0, "height": 0.4},
        )

        response = _post_region(client, _regions_base(project_id, master_id), payload)
        assert response.status_code == 400

    def test_create_rejects_polygon_points_with_fewer_than_3_points(
        self, client, project, sample_pdf_drawing
    ) -> None:
        project_id = cast(int, project.id)
        master_id = cast(int, sample_pdf_drawing.id)
        payload = _create_payload(polygon_points=[[0.1, 0.2], [0.2, 0.3]])

        response = _post_region(client, _regions_base(project_id, master_id), payload)
        assert response.status_code == 400

    def test_create_requires_idempotency_key(
        self, client, project, sample_pdf_drawing
    ) -> None:
        project_id = cast(int, project.id)
        master_id = cast(int, sample_pdf_drawing.id)
        response = client.post(
            _regions_base(project_id, master_id),
            json=_create_payload(),
        )
        assert response.status_code == 400


class TestListRegions:
    def test_list_returns_only_regions_for_requested_drawing(
        self, client, db_session, project, sample_pdf_drawing
    ) -> None:
        project_id = cast(int, project.id)
        master_a = cast(int, sample_pdf_drawing.id)
        other = Drawing(
            project_id=project_id,
            source="upload",
            name="other.pdf",
            storage_key=None,
            content_type="application/pdf",
        )
        db_session.add(other)
        db_session.commit()
        db_session.refresh(other)
        master_b = cast(int, other.id)

        _post_region(client, _regions_base(project_id, master_a), _create_payload(label="A"))
        _post_region(client, _regions_base(project_id, master_b), _create_payload(label="B"))

        response = client.get(_regions_base(project_id, master_a))
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["master_drawing_id"] == master_a
        assert body[0]["label"] == "A"

    def test_list_empty_drawing_returns_empty_list(
        self, client, project, sample_pdf_drawing
    ) -> None:
        project_id = cast(int, project.id)
        master_id = cast(int, sample_pdf_drawing.id)
        response = client.get(_regions_base(project_id, master_id))
        assert response.status_code == 200
        assert response.json() == []


class TestPatchRegion:
    def test_patch_geometry_only_leaves_tags_unchanged(
        self, client, project, sample_pdf_drawing
    ) -> None:
        project_id = cast(int, project.id)
        master_id = cast(int, sample_pdf_drawing.id)
        base = _regions_base(project_id, master_id)
        created = _post_region(client, base, _create_payload()).json()

        response = client.patch(
            f"{base}/{created['id']}",
            json={"geometry": {"type": "rect", "x": 0.2, "y": 0.3, "width": 0.1, "height": 0.1}},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["geometry"]["x"] == pytest.approx(0.2)
        assert body["inspection_type_tags"] == ["Final"]

    def test_patch_tags_only_leaves_geometry_unchanged(
        self, client, project, sample_pdf_drawing
    ) -> None:
        project_id = cast(int, project.id)
        master_id = cast(int, sample_pdf_drawing.id)
        base = _regions_base(project_id, master_id)
        created = _post_region(client, base, _create_payload()).json()

        response = client.patch(
            f"{base}/{created['id']}",
            json={
                "inspection_type_tags": ["Flush"],
                "location_tags": ["Yard"],
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["geometry"] == created["geometry"]
        assert body["inspection_type_tags"] == ["Flush"]
        assert body["location_tags"] == ["Yard"]

    def test_patch_updates_updated_at_timestamp(
        self, client, project, sample_pdf_drawing
    ) -> None:
        project_id = cast(int, project.id)
        master_id = cast(int, sample_pdf_drawing.id)
        base = _regions_base(project_id, master_id)
        created = _post_region(client, base, _create_payload()).json()

        response = client.patch(
            f"{base}/{created['id']}",
            json={"inspection_type_tags": ["Flush"], "location_tags": []},
        )
        assert response.json()["updated_at"] >= created["updated_at"]

    def test_patch_nonexistent_region_returns_404(
        self, client, project, sample_pdf_drawing
    ) -> None:
        project_id = cast(int, project.id)
        master_id = cast(int, sample_pdf_drawing.id)
        response = client.patch(
            f"{_regions_base(project_id, master_id)}/999999",
            json={"location_tags": ["Nowhere"]},
        )
        assert response.status_code == 404

    def test_patch_with_invalid_geometry_returns_400(
        self, client, project, sample_pdf_drawing
    ) -> None:
        project_id = cast(int, project.id)
        master_id = cast(int, sample_pdf_drawing.id)
        base = _regions_base(project_id, master_id)
        created = _post_region(client, base, _create_payload()).json()

        response = client.patch(
            f"{base}/{created['id']}",
            json={
                "geometry": {"type": "rect", "x": 0.1, "y": 0.2, "width": 0, "height": 0.4},
                "polygon_points": [[0.1, 0.2], [0.2, 0.3]],
            },
        )
        assert response.status_code == 400


class TestDeleteRegion:
    def test_delete_returns_204_and_removes_region(
        self, client, db_session, project, sample_pdf_drawing
    ) -> None:
        project_id = cast(int, project.id)
        master_id = cast(int, sample_pdf_drawing.id)
        base = _regions_base(project_id, master_id)
        created = _post_region(client, base, _create_payload()).json()

        response = client.delete(f"{base}/{created['id']}")
        assert response.status_code == 204
        assert get_drawing_region(db_session, master_id, created["id"]) is None

    def test_delete_nonexistent_region_returns_404(
        self, client, project, sample_pdf_drawing
    ) -> None:
        project_id = cast(int, project.id)
        master_id = cast(int, sample_pdf_drawing.id)
        response = client.delete(f"{_regions_base(project_id, master_id)}/999999")
        assert response.status_code == 404

    def test_delete_sets_overlay_region_id_to_null_not_cascade_delete(
        self, client, db_session, project, sample_pdf_drawing
    ) -> None:
        project_id = cast(int, project.id)
        master_id = cast(int, sample_pdf_drawing.id)
        base = _regions_base(project_id, master_id)
        created = _post_region(client, base, _create_payload()).json()
        region_id = cast(int, created["id"])

        evidence = EvidenceRecord(
            project_id=project_id,
            type="inspection_doc",
            title="Report",
            storage_key=None,
            content_type="application/pdf",
        )
        db_session.add(evidence)
        db_session.commit()
        db_session.refresh(evidence)

        storage = StorageService(db_session)
        run = storage.create_inspection_run(
            project_id=project_id,
            master_drawing_id=master_id,
            evidence_id=cast(int, evidence.id),
        )

        overlay = DrawingOverlay(
            master_drawing_id=master_id,
            inspection_run_id=cast(int, run.id),
            region_id=region_id,
            geometry={"type": "rect", "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
            status="unknown",
            label="Final — Roof",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        db_session.add(overlay)
        db_session.commit()
        db_session.refresh(overlay)
        overlay_id = cast(int, overlay.id)

        response = client.delete(f"{base}/{region_id}")
        assert response.status_code == 204

        db_session.refresh(overlay)
        assert overlay.region_id is None
        assert overlay.label == "Final — Roof"
        assert db_session.query(DrawingOverlay).filter_by(id=overlay_id).one() is overlay
