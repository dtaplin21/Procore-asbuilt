"""Route test: inspection-run evidence upload wires loader → pipeline → persistence."""

from __future__ import annotations

from io import BytesIO
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ai.pipelines import document_text_extraction as dte
from ai.pipelines.document_text_extraction import (
    BoundingBox,
    ExtractedDocument,
    PositionedWord,
    SourceFormat,
)
from ai.pipelines.drawing_location_resolver import MasterRegion
from models.models import Drawing
from services.region_index_loader import RegionIndexLoadResult
from services.storage import StorageService


def _master_region(master_drawing_id: int) -> MasterRegion:
    return MasterRegion(
        region_id="1",
        master_drawing_id=str(master_drawing_id),
        inspection_types=("Underground Fire Water Rough In",),
        location_labels=("Utility MR",),
        bbox_on_master=BoundingBox(
            x=0.05,
            y=0.06,
            width=0.08,
            height=0.09,
            page_width=1.0,
            page_height=1.0,
        ),
    )


@pytest.fixture
def master_drawing(db_session: Session, project) -> Drawing:
    drawing = Drawing(
        project_id=project.id,
        source="upload",
        name="master.pdf",
        storage_key=None,
        content_type="application/pdf",
    )
    db_session.add(drawing)
    db_session.commit()
    db_session.refresh(drawing)
    return drawing


def test_upload_inspection_run_evidence_maps_and_persists(
    client: TestClient,
    db_session: Session,
    project,
    master_drawing: Drawing,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = StorageService(db_session)
    run = storage.create_inspection_run(
        project_id=cast(int, project.id),
        master_drawing_id=cast(int, master_drawing.id),
        evidence_id=None,
        inspection_type="fire_protection",
    )
    master_id = cast(int, master_drawing.id)

    def _fake_build_region_index(db, drawing_id, *, include_untagged=False):
        return RegionIndexLoadResult(
            regions=[_master_region(master_id)],
            total_region_count=1,
            untagged_region_count=0,
        )

    monkeypatch.setattr(
        "api.routes.evidence.build_region_index",
        _fake_build_region_index,
    )

    words = [
        PositionedWord(
            text=w,
            bbox=BoundingBox(
                x=i * 80,
                y=100,
                width=10 * len(w),
                height=14,
                page_width=1000,
                page_height=1000,
            ),
            page_index=0,
        )
        for i, w in enumerate(
            [
                "Underground",
                "Fire",
                "Water",
                "Rough",
                "In",
                "at",
                "Utility",
                "MR",
                "Status",
                "Rejected",
            ]
        )
    ]
    fake_doc = ExtractedDocument(
        source_format=SourceFormat.NATIVE_PDF,
        page_count=1,
        words=words,
    )
    monkeypatch.setattr(dte, "_pdf_has_text_layer", lambda p: True)
    monkeypatch.setattr(dte, "_pdf_text_layer", lambda p: fake_doc)

    response = client.post(
        f"/api/projects/{project.id}/inspections/runs/{run.id}/evidence",
        files={"file": ("report.pdf", BytesIO(b"%PDF-1.4 minimal"), "application/pdf")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["overlays_created"] == 1
    assert body["unresolved_count"] == 0
    assert len(body["overlay_ids"]) == 1

    overlays = storage.list_drawing_overlays(master_id, inspection_run_id=cast(int, run.id))
    assert len(overlays) == 1
    geometry = cast(dict[str, Any], overlays[0].geometry)
    assert float(geometry["x"]) == pytest.approx(0.05)
