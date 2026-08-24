"""End-to-end test of POST /api/projects/{project_id}/inspections/runs/{run_id}/evidence.

Inspection run upload is storage-only (PR-A): saves the file, enqueues location
match, and does not create provisional overlays via map_document_to_overlays.
"""

from __future__ import annotations

from io import BytesIO
from typing import cast

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
from models.drawing_overlay import DrawingOverlay
from models.models import Drawing, JobQueue
from services.inspection_matching_jobs import JOB_TYPE_INSPECTION_MATCH
from services.storage import StorageService


def _word(text: str, x: float, y: float = 100) -> PositionedWord:
    return PositionedWord(
        text=text,
        bbox=BoundingBox(
            x=x,
            y=y,
            width=10 * len(text),
            height=14,
            page_width=1000,
            page_height=1000,
        ),
        page_index=0,
    )


def _layout(words: list[str]) -> list[PositionedWord]:
    out: list[PositionedWord] = []
    x = 0.0
    for word in words:
        out.append(_word(word, x))
        x += 10 * len(word) + 5
    return out


def _rect_geometry(
    x: float = 0.05,
    y: float = 0.06,
    width: float = 0.08,
    height: float = 0.09,
) -> dict[str, float | str]:
    return {"type": "rect", "x": x, "y": y, "width": width, "height": height}


def _patch_pdf_text(monkeypatch: pytest.MonkeyPatch, words: list[str]) -> None:
    fake_doc = ExtractedDocument(
        source_format=SourceFormat.NATIVE_PDF,
        page_count=1,
        words=_layout(words),
    )
    monkeypatch.setattr(dte, "_pdf_has_text_layer", lambda p: True)
    monkeypatch.setattr(dte, "_pdf_text_layer", lambda p: fake_doc)


def _insert_region(
    storage: StorageService,
    master_drawing_id: int,
    label: str,
    *,
    inspection_type_tags: list[str] | None = None,
    location_tags: list[str] | None = None,
) -> None:
    storage.create_drawing_region(
        master_drawing_id,
        label=label,
        geometry=_rect_geometry(),
        inspection_type_tags=inspection_type_tags,
        location_tags=location_tags,
    )


@pytest.fixture
def master_drawing(db_session: Session, project) -> Drawing:
    drawing = Drawing(
        project_id=project.id,
        source="upload",
        name="master.pdf",
        storage_key=None,
        content_type="application/pdf",
        index_status="ready",
    )
    db_session.add(drawing)
    db_session.commit()
    db_session.refresh(drawing)
    return drawing


@pytest.fixture
def evidence_upload_setup(
    db_session: Session,
    project,
    master_drawing: Drawing,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    from services import evidence_file_storage

    monkeypatch.setattr(evidence_file_storage, "EVIDENCE_STORAGE_ROOT", tmp_path)

    storage = StorageService(db_session)
    run = storage.create_inspection_run(
        project_id=cast(int, project.id),
        master_drawing_id=cast(int, master_drawing.id),
        evidence_id=None,
        inspection_type="fire_protection",
    )
    return project, master_drawing, run, storage, db_session


def _upload_url(project_id: int, run_id: int) -> str:
    return f"/api/projects/{project_id}/inspections/runs/{run_id}/evidence"


class TestEvidenceUploadHappyPath:
    def test_upload_persists_evidence_and_enqueues_match_without_provisional_overlay(
        self,
        client: TestClient,
        evidence_upload_setup,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        project, master_drawing, run, storage, db_session = evidence_upload_setup
        master_id = cast(int, master_drawing.id)

        _insert_region(
            storage,
            master_id,
            "region_a",
            inspection_type_tags=["Underground Fire Water Rough In"],
            location_tags=["Utility MR"],
        )

        _patch_pdf_text(
            monkeypatch,
            [
                "Underground",
                "Fire",
                "Water",
                "Rough",
                "In",
                "at",
                "Utility",
                "MR",
            ],
        )

        response = client.post(
            _upload_url(cast(int, project.id), cast(int, run.id)),
            files={"file": ("report.pdf", BytesIO(b"%PDF-1.4 fake pdf bytes"), "application/pdf")},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["evidence_id"] > 0
        assert body["overlays_created"] == 0
        assert body["unresolved_count"] == 0
        assert body["overlay_ids"] == []

        db_session.refresh(run)
        assert run.status == "processing"
        assert run.evidence_id == body["evidence_id"]

        job = (
            db_session.query(JobQueue)
            .filter(JobQueue.job_type == JOB_TYPE_INSPECTION_MATCH)
            .order_by(JobQueue.id.desc())
            .first()
        )
        assert job is not None
        input_data = cast(dict, job.input_data)
        assert input_data["inspection_id"] == str(body["evidence_id"])
        assert input_data["drawing_id"] == str(master_id)
        assert input_data["inspection_run_id"] == cast(int, run.id)

        overlay_count = (
            db_session.query(DrawingOverlay)
            .filter_by(inspection_run_id=run.id)
            .count()
        )
        assert overlay_count == 0

    def test_response_reports_untagged_region_count(
        self,
        client: TestClient,
        evidence_upload_setup,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        project, master_drawing, run, storage, _db_session = evidence_upload_setup
        master_id = cast(int, master_drawing.id)

        _insert_region(
            storage,
            master_id,
            "tagged",
            inspection_type_tags=["Final"],
            location_tags=["Roof"],
        )
        storage.create_drawing_region(master_id, label="untagged_one", geometry=_rect_geometry())
        storage.create_drawing_region(master_id, label="untagged_two", geometry=_rect_geometry())

        _patch_pdf_text(monkeypatch, ["Final", "inspection", "Roof", "Passed"])

        response = client.post(
            _upload_url(cast(int, project.id), cast(int, run.id)),
            files={"file": ("report.pdf", BytesIO(b"fake"), "application/pdf")},
        )
        assert response.status_code == 200
        assert response.json()["untagged_region_count"] == 2


class TestEvidenceUploadValidation:
    def test_unsupported_file_type_returns_400(
        self,
        client: TestClient,
        evidence_upload_setup,
    ) -> None:
        project, _master_drawing, run, _storage, _db_session = evidence_upload_setup

        response = client.post(
            _upload_url(cast(int, project.id), cast(int, run.id)),
            files={
                "file": (
                    "notes.docx",
                    BytesIO(b"fake"),
                    "application/vnd.openxmlformats",
                )
            },
        )
        assert response.status_code == 400

    def test_empty_file_returns_400(
        self,
        client: TestClient,
        evidence_upload_setup,
    ) -> None:
        project, _master_drawing, run, _storage, db_session = evidence_upload_setup

        response = client.post(
            _upload_url(cast(int, project.id), cast(int, run.id)),
            files={"file": ("report.pdf", BytesIO(b""), "application/pdf")},
        )
        assert response.status_code == 400

        db_session.refresh(run)
        assert run.status == "failed"
        assert run.error_message is not None


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
