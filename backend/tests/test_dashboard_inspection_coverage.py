"""Dashboard inspection coverage KPI (replaces sub-drawing comparison progress)."""

from __future__ import annotations

from typing import cast

from models.models import InspectionRun
from services.dashboard import get_project_inspection_coverage
from services.storage import StorageService


def test_count_project_master_drawings_uses_canonical_fk(
    db_session,
    project,
) -> None:
    storage = StorageService(db_session)
    pid = cast(int, project.id)
    assert storage.count_project_master_drawings(pid) == 0

    storage.create_drawing(
        pid,
        source="upload",
        name="master.pdf",
        storage_key=f"drawings/test/{pid}/master.pdf",
        content_type="application/pdf",
    )
    assert storage.count_project_master_drawings(pid) == 1


def test_count_drawings_with_inspection_run_requires_complete_status(
    db_session,
    project,
) -> None:
    storage = StorageService(db_session)
    pid = cast(int, project.id)
    master = storage.create_drawing(
        pid,
        source="upload",
        name="master.pdf",
        storage_key=f"drawings/test/{pid}/master.pdf",
        content_type="application/pdf",
    )
    master_id = cast(int, master.id)

    assert storage.count_drawings_with_inspection_run(pid) == 0

    queued = storage.create_inspection_run(
        project_id=pid,
        master_drawing_id=master_id,
    )
    assert storage.count_drawings_with_inspection_run(pid) == 0

    run = db_session.query(InspectionRun).filter(InspectionRun.id == queued.id).first()
    assert run is not None
    run.status = "complete"  # type: ignore[assignment]
    db_session.commit()

    assert storage.count_drawings_with_inspection_run(pid) == 1


def test_get_project_inspection_coverage_label(db_session, project) -> None:
    pid = cast(int, project.id)
    empty = get_project_inspection_coverage(db_session, pid)
    assert empty["total_masters_count"] == 0
    assert empty["inspected_count"] == 0
    assert "Upload a master drawing" in empty["label"]

    storage = StorageService(db_session)
    master = storage.create_drawing(
        pid,
        source="upload",
        name="master.pdf",
        storage_key=f"drawings/test/{pid}/master.pdf",
        content_type="application/pdf",
    )
    run = storage.create_inspection_run(
        project_id=pid,
        master_drawing_id=cast(int, master.id),
    )
    row = db_session.query(InspectionRun).filter(InspectionRun.id == run.id).first()
    assert row is not None
    row.status = "complete"  # type: ignore[assignment]
    db_session.commit()

    covered = get_project_inspection_coverage(db_session, pid)
    assert covered == {
        "inspected_count": 1,
        "total_masters_count": 1,
        "label": "1 of 1 master drawing(s) have been inspected for this project.",
    }


def test_dashboard_summary_exposes_inspection_coverage(
    client,
    db_session,
    project,
) -> None:
    storage = StorageService(db_session)
    pid = cast(int, project.id)
    master = storage.create_drawing(
        pid,
        source="upload",
        name="master.pdf",
        storage_key=f"drawings/test/{pid}/master.pdf",
        content_type="application/pdf",
    )
    run = storage.create_inspection_run(
        project_id=pid,
        master_drawing_id=cast(int, master.id),
    )
    row = db_session.query(InspectionRun).filter(InspectionRun.id == run.id).first()
    assert row is not None
    row.status = "complete"  # type: ignore[assignment]
    db_session.commit()

    response = client.get(f"/api/projects/{pid}/dashboard/summary")
    assert response.status_code == 200
    kpis = response.json()["kpis"]
    assert "comparisonProgress" not in kpis
    coverage = kpis["inspectionCoverage"]
    assert coverage["inspectedCount"] == 1
    assert coverage["totalMastersCount"] == 1
    assert "master drawing" in coverage["label"].lower()
