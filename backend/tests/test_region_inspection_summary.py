"""Tests for region inspection summary service and API route."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import cast

import pytest

from models.drawing_overlay import DrawingOverlay
from models.drawing_region import DrawingRegion
from models.models import Drawing, EvidenceRecord, InspectionRun, Project
from services.region_inspection_summary import (
    RegionViewerState,
    build_region_inspection_summary,
)
from services.storage import StorageService


def _create_region(
    db_session,
    master_drawing_id: int,
    *,
    label: str = "Zone A",
    geometry: dict | None = None,
    location_tags: list[str] | None = None,
    inspection_type_tags: list[str] | None = None,
) -> DrawingRegion:
    row = DrawingRegion(
        master_drawing_id=master_drawing_id,
        label=label,
        page=1,
        geometry=geometry
        or {"type": "rect", "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
        location_tags=location_tags or ["North Wing"],
        inspection_type_tags=inspection_type_tags or ["HVAC"],
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _create_run(
    db_session,
    project_id: int,
    master_drawing_id: int,
    *,
    inspection_type: str | None = "Mechanical QA",
    procore_inspection_id: str | None = None,
) -> InspectionRun:
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
        master_drawing_id=master_drawing_id,
        evidence_id=cast(int, evidence.id),
        inspection_type=inspection_type,
    )
    if procore_inspection_id is not None:
        run.procore_inspection_id = procore_inspection_id  # type: ignore[assignment]
        db_session.add(run)
        db_session.commit()
        db_session.refresh(run)
    return run


def _create_overlay(
    db_session,
    *,
    master_drawing_id: int,
    inspection_run_id: int,
    region_id: int | None,
    created_at: datetime,
    inspection_date: date | None = None,
    status: str = "pass",
    tags_json: dict | None = None,
) -> DrawingOverlay:
    row = DrawingOverlay(
        master_drawing_id=master_drawing_id,
        inspection_run_id=inspection_run_id,
        region_id=region_id,
        geometry={"type": "rect", "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
        status=status,
        inspection_date=inspection_date,
        tags_json=tags_json,
        created_at=created_at,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def test_summary_empty_when_no_regions(db_session, project, sample_pdf_drawing) -> None:
    master_id = cast(int, sample_pdf_drawing.id)
    entries = build_region_inspection_summary(db_session, master_id)
    assert entries == []


def test_hidden_region_without_linked_overlay(
    db_session,
    project,
    sample_pdf_drawing,
) -> None:
    master_id = cast(int, sample_pdf_drawing.id)
    region = _create_region(db_session, master_id)

    entries = build_region_inspection_summary(db_session, master_id)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.region_id == cast(int, region.id)
    assert entry.state == RegionViewerState.HIDDEN
    assert entry.bbox == pytest.approx((0.1, 0.2, 0.4, 0.6))
    assert entry.location_tags == ("North Wing",)
    assert entry.latest_overlay_id is None
    assert entry.inspection_status_display is None


def test_inspected_region_uses_latest_overlay_by_upload_time(
    db_session,
    project,
    sample_pdf_drawing,
) -> None:
    master_id = cast(int, sample_pdf_drawing.id)
    project_id = cast(int, project.id)
    region = _create_region(db_session, master_id)
    region_id = cast(int, region.id)

    run_old = _create_run(
        db_session,
        project_id,
        master_id,
        procore_inspection_id="PROC-111",
    )
    run_new = _create_run(
        db_session,
        project_id,
        master_id,
        procore_inspection_id="PROC-222",
    )

    _create_overlay(
        db_session,
        master_drawing_id=master_id,
        inspection_run_id=cast(int, run_old.id),
        region_id=region_id,
        created_at=datetime(2026, 1, 10, tzinfo=timezone.utc),
        inspection_date=date(2026, 1, 5),
        status="fail",
        tags_json={"inspectionStatuses": ["Rejected"]},
    )
    latest = _create_overlay(
        db_session,
        master_drawing_id=master_id,
        inspection_run_id=cast(int, run_new.id),
        region_id=region_id,
        created_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
        inspection_date=date(2025, 12, 1),
        status="pass",
        tags_json={"inspectionStatuses": ["Approved As Noted"]},
    )

    entries = build_region_inspection_summary(db_session, master_id)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.state == RegionViewerState.INSPECTED
    assert entry.latest_overlay_id == cast(int, latest.id)
    assert entry.latest_inspection_run_id == cast(int, run_new.id)
    assert entry.inspection_status_display == "Approved As Noted"
    assert entry.inspection_date == date(2025, 12, 1)
    assert entry.procore_inspection_id == "PROC-222"
    assert entry.inspection_type == "Mechanical QA"


def test_status_display_ignores_pass_fail_column(
    db_session,
    project,
    sample_pdf_drawing,
) -> None:
    master_id = cast(int, sample_pdf_drawing.id)
    project_id = cast(int, project.id)
    region = _create_region(db_session, master_id)
    run = _create_run(db_session, project_id, master_id)

    _create_overlay(
        db_session,
        master_drawing_id=master_id,
        inspection_run_id=cast(int, run.id),
        region_id=cast(int, region.id),
        created_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        status="pass",
        tags_json={"inspectionStatuses": ["Rejected"]},
    )

    entry = build_region_inspection_summary(db_session, master_id)[0]
    assert entry.inspection_status_display == "Rejected"


def test_api_route_returns_summary(
    client,
    db_session,
    project,
    sample_pdf_drawing,
) -> None:
    master_id = cast(int, sample_pdf_drawing.id)
    project_id = cast(int, project.id)
    region = _create_region(db_session, master_id, label="Roof")
    run = _create_run(db_session, project_id, master_id, procore_inspection_id="PROC-99")
    overlay = _create_overlay(
        db_session,
        master_drawing_id=master_id,
        inspection_run_id=cast(int, run.id),
        region_id=cast(int, region.id),
        created_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        tags_json={"inspectionStatuses": ["Closed"]},
    )

    resp = client.get(
        f"/api/projects/{project_id}/drawings/{master_id}/region-inspection-summary"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["regionId"] == cast(int, region.id)
    assert item["state"] == "inspected"
    assert item["label"] == "Roof"
    assert item["latestOverlayId"] == cast(int, overlay.id)
    assert item["inspectionStatusDisplay"] == "Closed"
    assert item["procoreInspectionId"] == "PROC-99"


def test_api_route_404_for_missing_drawing(client, project) -> None:
    project_id = cast(int, project.id)
    resp = client.get(
        f"/api/projects/{project_id}/drawings/999999/region-inspection-summary"
    )
    assert resp.status_code == 404
