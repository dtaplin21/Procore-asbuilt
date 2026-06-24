"""Finding workspace deep links use inspection run + overlay query params."""

from __future__ import annotations

from typing import cast

from models.models import Drawing, DrawingOverlay, EvidenceRecord, Finding, InspectionRun
from services.findings import (
    build_finding_link,
    build_finding_workspace_link_metadata,
)
from services.storage import StorageService


def test_build_finding_link_resolves_overlay_and_inspection_run(
    db_session,
    project,
) -> None:
    project_id = cast(int, project.id)

    master = Drawing(
        project_id=project_id,
        source="upload",
        name="master.pdf",
        storage_key=None,
        content_type="application/pdf",
        upload_intent="master",
    )
    db_session.add(master)
    db_session.commit()
    db_session.refresh(master)
    master_id = cast(int, master.id)

    evidence = EvidenceRecord(
        project_id=project_id,
        type="inspection_doc",
        title="Field report",
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
    run_id = cast(int, run.id)

    finding = Finding(
        project_id=project_id,
        drawing_id=master_id,
        type="deviation",
        severity="high",
        title="Overlay mismatch",
        description="Detected during inspection mapping.",
        affected_items=[f"Inspection run #{run_id}"],
    )
    db_session.add(finding)
    db_session.commit()
    db_session.refresh(finding)
    finding_id = cast(int, finding.id)

    overlay = DrawingOverlay(
        master_drawing_id=master_id,
        inspection_run_id=run_id,
        geometry={"bbox": {"x": 0, "y": 0, "width": 10, "height": 10}},
        status="fail",
        meta={"finding_id": finding_id},
    )
    db_session.add(overlay)
    db_session.commit()
    db_session.refresh(overlay)
    overlay_id = cast(int, overlay.id)

    meta = build_finding_workspace_link_metadata(finding, db_session)
    assert meta is not None
    assert meta.project_id == project_id
    assert meta.master_drawing_id == master_id
    assert meta.inspection_run_id == run_id
    assert meta.overlay_id == overlay_id

    link = build_finding_link(finding, db_session)
    assert link == (
        f"/projects/{project_id}/drawings/{master_id}/workspace"
        f"?run={run_id}&overlay={overlay_id}"
    )


def test_findings_api_serializes_run_overlay_workspace_link(
    client,
    db_session,
    project,
) -> None:
    project_id = cast(int, project.id)

    master = Drawing(
        project_id=project_id,
        source="upload",
        name="sheet-a.pdf",
        storage_key=None,
        content_type="application/pdf",
        upload_intent="master",
    )
    db_session.add(master)
    db_session.commit()
    db_session.refresh(master)
    master_id = cast(int, master.id)

    run = InspectionRun(
        project_id=project_id,
        master_drawing_id=master_id,
        status="complete",
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    run_id = cast(int, run.id)

    finding = Finding(
        project_id=project_id,
        drawing_id=master_id,
        type="warning",
        severity="medium",
        title="Review required",
        description="Human review pending.",
    )
    db_session.add(finding)
    db_session.commit()
    db_session.refresh(finding)
    finding_id = cast(int, finding.id)

    overlay = DrawingOverlay(
        master_drawing_id=master_id,
        inspection_run_id=run_id,
        geometry={"bbox": {"x": 1, "y": 2, "width": 3, "height": 4}},
        status="unknown",
        meta={"finding_id": finding_id},
    )
    db_session.add(overlay)
    db_session.commit()

    response = client.get(f"/api/projects/{project_id}/findings?limit=10")
    assert response.status_code == 200
    payload = response.json()
    rows = payload["findings"]
    match = next(row for row in rows if row["id"] == finding_id)
    workspace_link = match["workspaceLink"]
    assert workspace_link is not None
    assert workspace_link["inspectionRunId"] == run_id
    assert workspace_link["overlayId"] == overlay.id
    assert "alignmentId" not in workspace_link
    assert "diffId" not in workspace_link
