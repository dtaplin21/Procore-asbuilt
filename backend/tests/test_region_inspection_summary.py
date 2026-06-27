"""
Tests for services/region_inspection_summary.py (join logic) and
api/routes/drawing_regions.py GET .../region-inspection-summary (PR1).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import cast

import pytest

from models.drawing_overlay import DrawingOverlay
from models.drawing_region import DrawingRegion
from models.models import EvidenceRecord, InspectionRun
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
    run: InspectionRun = storage.create_inspection_run(
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
    status: str = "unknown",
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


class TestBuildRegionInspectionSummary:
    def test_no_regions_at_all_returns_empty_list(
        self, db_session, sample_pdf_drawing
    ) -> None:
        master_id = cast(int, sample_pdf_drawing.id)
        assert build_region_inspection_summary(db_session, master_id) == []

    def test_region_with_no_overlay_is_hidden(
        self, db_session, sample_pdf_drawing
    ) -> None:
        master_id = cast(int, sample_pdf_drawing.id)
        _create_region(db_session, master_id, location_tags=["Roof"])

        entries = build_region_inspection_summary(db_session, master_id)
        assert len(entries) == 1
        assert entries[0].state == RegionViewerState.HIDDEN
        assert entries[0].inspection_status_display is None

    def test_region_with_linked_overlay_is_inspected(
        self, db_session, project, sample_pdf_drawing
    ) -> None:
        master_id = cast(int, sample_pdf_drawing.id)
        project_id = cast(int, project.id)
        region = _create_region(
            db_session,
            master_id,
            inspection_type_tags=["Final"],
            location_tags=["Roof"],
        )
        run = _create_run(db_session, project_id, master_id)
        overlay = _create_overlay(
            db_session,
            master_drawing_id=master_id,
            inspection_run_id=cast(int, run.id),
            region_id=cast(int, region.id),
            created_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            tags_json={"inspectionStatuses": ["Approved As Noted"]},
        )

        entry = build_region_inspection_summary(db_session, master_id)[0]
        assert entry.state == RegionViewerState.INSPECTED
        assert entry.inspection_status_display == "Approved As Noted"
        assert entry.latest_overlay_id == cast(int, overlay.id)
        assert entry.latest_inspection_run_id == cast(int, run.id)

    def test_status_display_uses_full_vocab_string_not_derived_status(
        self, db_session, project, sample_pdf_drawing
    ) -> None:
        master_id = cast(int, sample_pdf_drawing.id)
        project_id = cast(int, project.id)
        region = _create_region(db_session, master_id, location_tags=["Roof"])
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

    def test_latest_overlay_by_uploaded_at_wins_when_region_has_multiple(
        self, db_session, project, sample_pdf_drawing
    ) -> None:
        master_id = cast(int, sample_pdf_drawing.id)
        project_id = cast(int, project.id)
        region = _create_region(db_session, master_id, location_tags=["Roof"])
        region_id = cast(int, region.id)
        run1 = _create_run(db_session, project_id, master_id)
        run2 = _create_run(db_session, project_id, master_id)

        _create_overlay(
            db_session,
            master_drawing_id=master_id,
            inspection_run_id=cast(int, run1.id),
            region_id=region_id,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            tags_json={"inspectionStatuses": ["Approved"]},
        )
        latest = _create_overlay(
            db_session,
            master_drawing_id=master_id,
            inspection_run_id=cast(int, run2.id),
            region_id=region_id,
            created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            tags_json={"inspectionStatuses": ["Rejected"]},
        )

        entry = build_region_inspection_summary(db_session, master_id)[0]
        assert entry.latest_overlay_id == cast(int, latest.id)
        assert entry.inspection_status_display == "Rejected"

    def test_procore_inspection_id_included_when_run_is_synced(
        self, db_session, project, sample_pdf_drawing
    ) -> None:
        master_id = cast(int, sample_pdf_drawing.id)
        project_id = cast(int, project.id)
        region = _create_region(db_session, master_id, location_tags=["Roof"])
        run = _create_run(
            db_session, project_id, master_id, procore_inspection_id="PROCORE-123"
        )
        _create_overlay(
            db_session,
            master_drawing_id=master_id,
            inspection_run_id=cast(int, run.id),
            region_id=cast(int, region.id),
            created_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            tags_json={"inspectionStatuses": ["Approved"]},
        )

        entry = build_region_inspection_summary(db_session, master_id)[0]
        assert entry.procore_inspection_id == "PROCORE-123"

    def test_procore_inspection_id_is_none_when_run_not_synced(
        self, db_session, project, sample_pdf_drawing
    ) -> None:
        master_id = cast(int, sample_pdf_drawing.id)
        project_id = cast(int, project.id)
        region = _create_region(db_session, master_id, location_tags=["Roof"])
        run = _create_run(db_session, project_id, master_id, procore_inspection_id=None)
        _create_overlay(
            db_session,
            master_drawing_id=master_id,
            inspection_run_id=cast(int, run.id),
            region_id=cast(int, region.id),
            created_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            tags_json={"inspectionStatuses": ["Approved"]},
        )

        entry = build_region_inspection_summary(db_session, master_id)[0]
        assert entry.procore_inspection_id is None

    def test_overlays_with_no_region_id_are_ignored(
        self, db_session, project, sample_pdf_drawing
    ) -> None:
        master_id = cast(int, sample_pdf_drawing.id)
        project_id = cast(int, project.id)
        _create_region(db_session, master_id, location_tags=["Roof"])
        run = _create_run(db_session, project_id, master_id)
        _create_overlay(
            db_session,
            master_drawing_id=master_id,
            inspection_run_id=cast(int, run.id),
            region_id=None,
            created_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            tags_json={"inspectionStatuses": ["Approved"]},
        )

        entry = build_region_inspection_summary(db_session, master_id)[0]
        assert entry.state == RegionViewerState.HIDDEN

    def test_multiple_regions_mixed_states(
        self, db_session, project, sample_pdf_drawing
    ) -> None:
        master_id = cast(int, sample_pdf_drawing.id)
        project_id = cast(int, project.id)
        r1 = _create_region(db_session, master_id, label="Roof", location_tags=["Roof"])
        _create_region(db_session, master_id, label="Yard", location_tags=["Yard"])
        run = _create_run(db_session, project_id, master_id)
        _create_overlay(
            db_session,
            master_drawing_id=master_id,
            inspection_run_id=cast(int, run.id),
            region_id=cast(int, r1.id),
            created_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            tags_json={"inspectionStatuses": ["Passed"]},
        )

        by_id = {
            e.region_id: e for e in build_region_inspection_summary(db_session, master_id)
        }
        assert by_id[cast(int, r1.id)].state == RegionViewerState.INSPECTED
        assert len(by_id) == 2
        hidden = [e for e in by_id.values() if e.state == RegionViewerState.HIDDEN]
        assert len(hidden) == 1

    def test_inspection_date_included_when_present(
        self, db_session, project, sample_pdf_drawing
    ) -> None:
        master_id = cast(int, sample_pdf_drawing.id)
        project_id = cast(int, project.id)
        region = _create_region(db_session, master_id, location_tags=["Roof"])
        run = _create_run(db_session, project_id, master_id)
        _create_overlay(
            db_session,
            master_drawing_id=master_id,
            inspection_run_id=cast(int, run.id),
            region_id=cast(int, region.id),
            created_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            inspection_date=date(2026, 6, 24),
            tags_json={"inspectionStatuses": ["Approved"]},
        )

        entry = build_region_inspection_summary(db_session, master_id)[0]
        assert entry.inspection_date == date(2026, 6, 24)

    def test_bbox_is_fractional(self, db_session, sample_pdf_drawing) -> None:
        master_id = cast(int, sample_pdf_drawing.id)
        _create_region(
            db_session,
            master_id,
            geometry={"type": "rect", "x": 0.1, "y": 0.2, "width": 0.05, "height": 0.05},
            location_tags=["Roof"],
        )

        x0, y0, x1, y1 = build_region_inspection_summary(db_session, master_id)[0].bbox
        assert x0 == pytest.approx(0.1)
        assert y0 == pytest.approx(0.2)
        assert x1 == pytest.approx(0.15)
        assert y1 == pytest.approx(0.25)


class TestRegionInspectionSummaryRoute:
    def test_route_returns_empty_items_for_drawing_with_no_regions(
        self, client, project, sample_pdf_drawing
    ) -> None:
        project_id = cast(int, project.id)
        master_id = cast(int, sample_pdf_drawing.id)

        response = client.get(
            f"/api/projects/{project_id}/drawings/{master_id}/region-inspection-summary"
        )
        assert response.status_code == 200
        assert response.json() == {"items": []}

    def test_route_returns_hidden_and_inspected_states(
        self, client, db_session, project, sample_pdf_drawing
    ) -> None:
        project_id = cast(int, project.id)
        master_id = cast(int, sample_pdf_drawing.id)
        r1 = _create_region(
            db_session,
            master_id,
            label="Roof",
            inspection_type_tags=["Final"],
            location_tags=["Roof"],
        )
        _create_region(db_session, master_id, label="Yard", location_tags=["Yard"])
        run = _create_run(db_session, project_id, master_id)
        _create_overlay(
            db_session,
            master_drawing_id=master_id,
            inspection_run_id=cast(int, run.id),
            region_id=cast(int, r1.id),
            created_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            tags_json={"inspectionStatuses": ["Approved As Noted"]},
        )

        response = client.get(
            f"/api/projects/{project_id}/drawings/{master_id}/region-inspection-summary"
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 2

        by_id = {entry["regionId"]: entry for entry in items}
        assert by_id[cast(int, r1.id)]["state"] == "inspected"
        assert by_id[cast(int, r1.id)]["inspectionStatusDisplay"] == "Approved As Noted"
        hidden = [entry for entry in items if entry["state"] == "hidden"]
        assert len(hidden) == 1
        assert hidden[0]["inspectionStatusDisplay"] is None

    def test_route_404_for_missing_drawing(self, client, project) -> None:
        project_id = cast(int, project.id)
        response = client.get(
            f"/api/projects/{project_id}/drawings/999999/region-inspection-summary"
        )
        assert response.status_code == 404
