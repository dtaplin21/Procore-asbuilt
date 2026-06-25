"""End-to-end test of POST .../inspections/runs/{run_id}/evidence.

Multipart upload hits the real FastAPI route (via TestClient), which runs the
real region loader → map_document_to_overlays() → overlay/unresolved
persistence. Only PDF text-layer extraction is monkeypatched — the same seam
as the rest of this suite.
"""

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
from models.models import Drawing, DrawingOverlay, UnresolvedEvidence
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
    def test_pdf_naming_known_type_and_location_creates_overlay(
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
                "Status",
                "Rejected",
                "Repair",
                "required",
            ],
        )

        response = client.post(
            _upload_url(cast(int, project.id), cast(int, run.id)),
            files={"file": ("report.pdf", BytesIO(b"%PDF-1.4 fake pdf bytes"), "application/pdf")},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["overlays_created"] == 1
        assert body["unresolved_count"] == 0
        assert len(body["overlay_ids"]) == 1

        db_session.expire_all()
        saved = db_session.query(DrawingOverlay).filter_by(id=body["overlay_ids"][0]).one()
        assert saved.master_drawing_id == master_id
        assert saved.inspection_run_id == run.id
        assert saved.severity == "high"
        tags = cast(dict[str, Any], saved.tags_json)
        assert "Rejected" in tags.get("inspectionStatuses", [])
        assert "Repair" in tags.get("fieldConditions", [])

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


class TestEvidenceUploadUnresolvedPath:
    def test_unmatched_document_persists_unresolved_record_not_an_error(
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
            inspection_type_tags=["Flush"],
            location_tags=["Yard"],
        )

        _patch_pdf_text(monkeypatch, ["Final", "inspection", "at", "Roof"])

        response = client.post(
            _upload_url(cast(int, project.id), cast(int, run.id)),
            files={"file": ("report.pdf", BytesIO(b"fake"), "application/pdf")},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["overlays_created"] == 0
        assert body["unresolved_count"] == 1

        db_session.expire_all()
        rows = db_session.query(UnresolvedEvidence).filter_by(inspection_run_id=run.id).all()
        assert len(rows) == 1
        assert "Final" in rows[0].reason or "Roof" in rows[0].reason

    def test_document_with_no_vocabulary_is_unresolved_not_an_error(
        self,
        client: TestClient,
        evidence_upload_setup,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        project, master_drawing, run, _storage, _db_session = evidence_upload_setup

        _patch_pdf_text(monkeypatch, ["the", "quick", "brown", "fox"])

        response = client.post(
            _upload_url(cast(int, project.id), cast(int, run.id)),
            files={"file": ("irrelevant.pdf", BytesIO(b"fake"), "application/pdf")},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["overlays_created"] == 0
        assert body["unresolved_count"] == 1


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
        project, _master_drawing, run, _storage, _db_session = evidence_upload_setup

        response = client.post(
            _upload_url(cast(int, project.id), cast(int, run.id)),
            files={"file": ("report.pdf", BytesIO(b""), "application/pdf")},
        )
        assert response.status_code == 400


class TestEvidenceUploadMultiOverlay:
    def test_document_naming_two_findings_resolves_to_first_unambiguous_match(
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
            inspection_type_tags=["Final"],
            location_tags=["Roof"],
        )
        _insert_region(
            storage,
            master_id,
            "region_b",
            inspection_type_tags=["Flush"],
            location_tags=["Yard"],
        )

        _patch_pdf_text(
            monkeypatch,
            ["Final", "Roof", "Approved", "Flush", "Yard", "Rejected"],
        )

        response = client.post(
            _upload_url(cast(int, project.id), cast(int, run.id)),
            files={"file": ("report.pdf", BytesIO(b"fake"), "application/pdf")},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["overlays_created"] == 1

        db_session.expire_all()
        saved_rows = (
            db_session.query(DrawingOverlay)
            .filter_by(inspection_run_id=run.id)
            .all()
        )
        assert len(saved_rows) == 1


class TestTimestampDisambiguation:
    """Two separate uploads for the same finding are distinguished by created_at
    (when the system received each upload). inspection_date is parsed from the
    document text and tracked independently.
    """

    def test_two_uploads_get_distinct_created_at_timestamps(
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
            inspection_type_tags=["Final"],
            location_tags=["Roof"],
        )

        _patch_pdf_text(monkeypatch, ["Final", "inspection", "Roof", "Rejected"])

        r1 = client.post(
            _upload_url(cast(int, project.id), cast(int, run.id)),
            files={"file": ("report1.pdf", BytesIO(b"fake1"), "application/pdf")},
        )
        r2 = client.post(
            _upload_url(cast(int, project.id), cast(int, run.id)),
            files={"file": ("report2.pdf", BytesIO(b"fake2"), "application/pdf")},
        )
        assert r1.status_code == 200 and r2.status_code == 200

        db_session.expire_all()
        rows = (
            db_session.query(DrawingOverlay)
            .filter_by(inspection_run_id=run.id)
            .order_by(DrawingOverlay.created_at)
            .all()
        )
        assert len(rows) == 2
        assert rows[0].id != rows[1].id
        assert rows[0].created_at is not None
        assert rows[1].created_at is not None

    def test_inspection_date_extracted_from_document_text(
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
            inspection_type_tags=["Final"],
            location_tags=["Roof"],
        )

        _patch_pdf_text(
            monkeypatch,
            ["Inspection", "date:", "06/24/2026", "Final", "inspection", "Roof", "Approved"],
        )

        response = client.post(
            _upload_url(cast(int, project.id), cast(int, run.id)),
            files={"file": ("report.pdf", BytesIO(b"fake"), "application/pdf")},
        )
        assert response.status_code == 200
        overlay_id = response.json()["overlay_ids"][0]

        db_session.expire_all()
        row = db_session.query(DrawingOverlay).filter_by(id=overlay_id).one()
        assert row.inspection_date is not None
        assert row.inspection_date.isoformat() == "2026-06-24"

    def test_inspection_date_is_none_when_document_states_no_date(
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
            inspection_type_tags=["Final"],
            location_tags=["Roof"],
        )

        _patch_pdf_text(monkeypatch, ["Final", "inspection", "Roof", "Approved"])

        response = client.post(
            _upload_url(cast(int, project.id), cast(int, run.id)),
            files={"file": ("report.pdf", BytesIO(b"fake"), "application/pdf")},
        )
        overlay_id = response.json()["overlay_ids"][0]

        db_session.expire_all()
        row = db_session.query(DrawingOverlay).filter_by(id=overlay_id).one()
        assert row.inspection_date is None

    def test_inspection_date_and_created_at_are_independent(
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
            inspection_type_tags=["Final"],
            location_tags=["Roof"],
        )

        _patch_pdf_text(
            monkeypatch,
            ["Inspection", "date:", "2020-01-15", "Final", "Roof", "Approved"],
        )

        response = client.post(
            _upload_url(cast(int, project.id), cast(int, run.id)),
            files={"file": ("report.pdf", BytesIO(b"fake"), "application/pdf")},
        )
        overlay_id = response.json()["overlay_ids"][0]

        db_session.expire_all()
        row = db_session.query(DrawingOverlay).filter_by(id=overlay_id).one()
        assert row.inspection_date is not None
        assert row.inspection_date.isoformat() == "2020-01-15"
        assert row.created_at.year >= 2026
