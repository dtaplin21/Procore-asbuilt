"""Tests for region_storage CRUD and PATCH/DELETE routes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

import pytest

from models.drawing_overlay import DrawingOverlay
from models.models import EvidenceRecord
from services.region_storage import (
    create_drawing_region,
    delete_drawing_region,
    get_drawing_region,
    update_drawing_region,
    validate_region_geometry,
)
from services.storage import StorageService


def _rect_geometry(
    x: float = 0.1,
    y: float = 0.2,
    width: float = 0.3,
    height: float = 0.4,
) -> dict:
    return {"type": "rect", "x": x, "y": y, "width": width, "height": height}


def test_validate_region_geometry_rejects_zero_width() -> None:
    with pytest.raises(ValueError, match="positive width"):
        validate_region_geometry(
            {"type": "rect", "x": 0.1, "y": 0.2, "width": 0, "height": 0.4}
        )


def test_validate_region_geometry_rejects_short_polygon() -> None:
    with pytest.raises(ValueError, match="at least 3 points"):
        validate_region_geometry(
            {"type": "polygon", "points": [[0.1, 0.2], [0.2, 0.3]]}
        )


def test_create_and_get_region(db_session, sample_pdf_drawing) -> None:
    master_id = cast(int, sample_pdf_drawing.id)
    region = create_drawing_region(
        db_session,
        master_id,
        label="Zone A",
        geometry=_rect_geometry(),
        location_tags=["North"],
        inspection_type_tags=["HVAC"],
    )

    assert region.id is not None
    fetched = get_drawing_region(db_session, master_id, cast(int, region.id))
    assert fetched is not None
    assert fetched.label == "Zone A"
    assert fetched.location_tags == ["North"]


def test_update_region_partial_tags_only(db_session, sample_pdf_drawing) -> None:
    master_id = cast(int, sample_pdf_drawing.id)
    region = create_drawing_region(
        db_session,
        master_id,
        label="Zone A",
        geometry=_rect_geometry(),
        location_tags=["Old"],
    )
    region_id = cast(int, region.id)

    updated = update_drawing_region(
        db_session,
        master_id,
        region_id,
        location_tags=["New Wing"],
    )
    assert updated is not None
    assert updated.location_tags == ["New Wing"]
    assert updated.geometry == _rect_geometry()


def test_update_region_geometry(db_session, sample_pdf_drawing) -> None:
    master_id = cast(int, sample_pdf_drawing.id)
    region = create_drawing_region(
        db_session,
        master_id,
        label="Zone A",
        geometry=_rect_geometry(),
    )
    region_id = cast(int, region.id)
    new_geometry = _rect_geometry(x=0.2, y=0.3, width=0.1, height=0.1)

    updated = update_drawing_region(
        db_session,
        master_id,
        region_id,
        geometry=new_geometry,
    )
    assert updated is not None
    assert updated.geometry == new_geometry


def test_update_missing_region_returns_none(db_session, sample_pdf_drawing) -> None:
    master_id = cast(int, sample_pdf_drawing.id)
    assert update_drawing_region(db_session, master_id, 999999, label="nope") is None


def test_delete_region_clears_overlay_region_id(
    db_session,
    project,
    sample_pdf_drawing,
) -> None:
    master_id = cast(int, sample_pdf_drawing.id)
    project_id = cast(int, project.id)
    region = create_drawing_region(
        db_session,
        master_id,
        label="Zone A",
        geometry=_rect_geometry(),
    )
    region_id = cast(int, region.id)

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
        geometry=_rect_geometry(),
        status="unknown",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    db_session.add(overlay)
    db_session.commit()
    db_session.refresh(overlay)
    overlay_id = cast(int, overlay.id)

    assert delete_drawing_region(db_session, master_id, region_id) is True
    db_session.refresh(overlay)
    assert overlay.region_id is None
    assert db_session.query(DrawingOverlay).filter_by(id=overlay_id).one() is overlay


def test_patch_route_updates_region(
    client,
    db_session,
    project,
    sample_pdf_drawing,
) -> None:
    master_id = cast(int, sample_pdf_drawing.id)
    project_id = cast(int, project.id)
    region = create_drawing_region(
        db_session,
        master_id,
        label="Before",
        geometry=_rect_geometry(),
    )
    region_id = cast(int, region.id)

    resp = client.patch(
        f"/api/projects/{project_id}/drawings/{master_id}/regions/{region_id}",
        json={"label": "After", "location_tags": ["East"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["label"] == "After"
    assert body["location_tags"] == ["East"]


def test_delete_route_returns_204(
    client,
    db_session,
    project,
    sample_pdf_drawing,
) -> None:
    master_id = cast(int, sample_pdf_drawing.id)
    project_id = cast(int, project.id)
    region = create_drawing_region(
        db_session,
        master_id,
        label="Temp",
        geometry=_rect_geometry(),
    )
    region_id = cast(int, region.id)

    resp = client.delete(
        f"/api/projects/{project_id}/drawings/{master_id}/regions/{region_id}"
    )
    assert resp.status_code == 204
    assert get_drawing_region(db_session, master_id, region_id) is None


def test_delete_route_404_for_missing_region(client, project, sample_pdf_drawing) -> None:
    project_id = cast(int, project.id)
    master_id = cast(int, sample_pdf_drawing.id)
    resp = client.delete(
        f"/api/projects/{project_id}/drawings/{master_id}/regions/999999"
    )
    assert resp.status_code == 404
