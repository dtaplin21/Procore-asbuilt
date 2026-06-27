"""
Tests for services/overlay_storage.py — PR1 additions: region_id persistence
and the derived pass/fail/unknown status column (analytics only per the
region-visibility spec — not used for bold styling or hover-tooltip text).

Uses Postgres via conftest fixtures (real DrawingRegion FK targets).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

import pytest
from sqlalchemy.orm import Session

from ai.pipelines.inspection_mapping import (
    DrawingOverlayRecord,
    EvidenceInput,
    NormalizedEvidenceTags,
    UnresolvedEvidenceRecord,
    map_evidence_to_overlay,
)
from ai.pipelines.positioned_term_extractor import PositionedTerm
from ai.pipelines.term_extractor import ConfidenceLabel, ExtractedTerm
from models.drawing_overlay import DrawingOverlay, UnresolvedEvidence
from models.models import Drawing
from services.inspection_vocabulary import VocabCategory
from services.overlay_storage import (
    _derive_pass_fail_status,
    create_drawing_overlay,
    create_drawing_overlays,
    flag_unresolved_evidence,
    list_unresolved_evidence,
)
from services.storage import StorageService


def _tags(statuses: list[str] | None = None) -> NormalizedEvidenceTags:
    return NormalizedEvidenceTags(
        inspection_types=["Final"],
        inspection_statuses=statuses or [],
        locations=["Roof"],
        trades=[],
        field_conditions=[],
        actions=[],
        markup_terms=[],
        confidence_label="High Confidence",
    )


def _overlay_record(
    *,
    master_drawing_id: int,
    inspection_run_id: int,
    record_id: str = "overlay_1",
    bbox: tuple[float, float, float, float] = (0.1, 0.1, 0.2, 0.2),
    region_id: str | None = None,
    tags: NormalizedEvidenceTags | None = None,
) -> DrawingOverlayRecord:
    return DrawingOverlayRecord(
        id=record_id,
        drawing_id=str(master_drawing_id),
        inspection_run_id=str(inspection_run_id),
        bbox=bbox,
        label="Final — Roof",
        severity="info",
        tags=tags or _tags(),
        inspection_date=None,
        uploaded_at=datetime.now(timezone.utc),
        region_id=region_id,
    )


def _positioned(canonical: str, category: VocabCategory) -> PositionedTerm:
    from ai.pipelines.document_text_extraction import BoundingBox

    return PositionedTerm(
        term=ExtractedTerm(
            category=category,
            canonical=canonical,
            matched_text=canonical,
            start=0,
            end=len(canonical),
            confidence_score=0.9,
            confidence_label=ConfidenceLabel.HIGH,
        ),
        page_index=0,
        bbox=BoundingBox(0, 0, 10, 10, 100, 100),
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
def inspection_run(db_session: Session, project, master_drawing: Drawing):
    storage = StorageService(db_session)
    return storage.create_inspection_run(
        project_id=cast(int, project.id),
        master_drawing_id=cast(int, master_drawing.id),
        evidence_id=None,
        inspection_type="general",
    )


class TestRegionIdPersistence:
    def test_create_drawing_overlay_persists_region_id(
        self,
        db_session: Session,
        master_drawing: Drawing,
        inspection_run,
    ) -> None:
        storage = StorageService(db_session)
        region = storage.create_drawing_region(
            cast(int, master_drawing.id),
            label="Roof",
            page=1,
            geometry={"type": "rect", "x": 0.1, "y": 0.2, "width": 0.2, "height": 0.2},
        )
        record = _overlay_record(
            master_drawing_id=cast(int, master_drawing.id),
            inspection_run_id=cast(int, inspection_run.id),
            region_id=str(region.id),
        )

        row = create_drawing_overlay(db_session, record)
        region_id = cast(int, region.id)
        assert cast(int | None, row.region_id) == region_id

        reloaded = db_session.query(DrawingOverlay).filter_by(id=row.id).one()
        assert cast(int | None, reloaded.region_id) == region_id

    def test_create_drawing_overlay_allows_null_region_id(
        self,
        db_session: Session,
        master_drawing: Drawing,
        inspection_run,
    ) -> None:
        record = _overlay_record(
            master_drawing_id=cast(int, master_drawing.id),
            inspection_run_id=cast(int, inspection_run.id),
            region_id=None,
        )
        row = create_drawing_overlay(db_session, record)
        assert cast(int | None, row.region_id) is None

    def test_create_drawing_overlays_batch_persists_region_id_per_row(
        self,
        db_session: Session,
        project,
        master_drawing: Drawing,
        inspection_run,
    ) -> None:
        storage = StorageService(db_session)
        master_id = cast(int, master_drawing.id)
        region_a = storage.create_drawing_region(
            master_id,
            label="A",
            page=1,
            geometry={"type": "rect", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
        )
        region_b = storage.create_drawing_region(
            master_id,
            label="B",
            page=1,
            geometry={"type": "rect", "x": 0.2, "y": 0.2, "width": 0.1, "height": 0.1},
        )
        run_id = cast(int, inspection_run.id)
        records = [
            _overlay_record(
                master_drawing_id=master_id,
                inspection_run_id=run_id,
                record_id="o1",
                region_id=str(region_a.id),
            ),
            _overlay_record(
                master_drawing_id=master_id,
                inspection_run_id=run_id,
                record_id="o2",
                region_id=str(region_b.id),
            ),
            _overlay_record(
                master_drawing_id=master_id,
                inspection_run_id=run_id,
                record_id="o3",
                region_id=None,
            ),
        ]
        rows = create_drawing_overlays(db_session, records)

        by_region_id = {cast(int | None, r.region_id): r for r in rows}
        assert cast(int | None, by_region_id[cast(int, region_a.id)].region_id) == cast(
            int, region_a.id
        )
        assert cast(int | None, by_region_id[cast(int, region_b.id)].region_id) == cast(
            int, region_b.id
        )
        assert None in by_region_id


class TestDerivedStatusColumn:
    @pytest.mark.parametrize(
        ("statuses", "expected"),
        [
            (["Approved"], "pass"),
            (["Approved As Noted"], "pass"),
            (["Passed"], "pass"),
            (["Completed"], "pass"),
            (["Closed"], "pass"),
            (["Rejected"], "fail"),
            (["Failed"], "fail"),
            ([], "unknown"),
            (["Pending"], "unknown"),
            (["Scheduled"], "unknown"),
        ],
    )
    def test_derive_pass_fail_status(self, statuses: list[str], expected: str) -> None:
        assert _derive_pass_fail_status(statuses) == expected

    def test_fail_takes_priority_over_pass_when_both_present(self) -> None:
        assert _derive_pass_fail_status(["Approved", "Rejected"]) == "fail"

    def test_status_column_persisted_from_tags(
        self,
        db_session: Session,
        master_drawing: Drawing,
        inspection_run,
    ) -> None:
        record = _overlay_record(
            master_drawing_id=cast(int, master_drawing.id),
            inspection_run_id=cast(int, inspection_run.id),
            tags=_tags(["Rejected"]),
        )
        row = create_drawing_overlay(db_session, record)
        assert str(getattr(row, "status")) == "fail"

    def test_status_column_is_unknown_when_no_status_extracted(
        self,
        db_session: Session,
        master_drawing: Drawing,
        inspection_run,
    ) -> None:
        record = _overlay_record(
            master_drawing_id=cast(int, master_drawing.id),
            inspection_run_id=cast(int, inspection_run.id),
            tags=_tags([]),
        )
        row = create_drawing_overlay(db_session, record)
        assert str(getattr(row, "status")) == "unknown"


class TestOverlayStorageExtras:
    def test_create_drawing_overlays_persists_geometry_and_meta(
        self,
        db_session: Session,
        master_drawing: Drawing,
        inspection_run,
    ) -> None:
        record = _overlay_record(
            master_drawing_id=cast(int, master_drawing.id),
            inspection_run_id=cast(int, inspection_run.id),
            bbox=(0.1, 0.2, 0.4, 0.5),
            tags=_tags(["Rejected"]),
        )
        saved = create_drawing_overlays(db_session, [record])
        overlay = saved[0]
        geometry = cast(dict[str, Any], overlay.geometry)
        assert float(geometry["x"]) == pytest.approx(0.1)
        assert float(geometry["width"]) == pytest.approx(0.3)
        assert str(getattr(overlay, "status")) == "fail"
        assert getattr(overlay, "tags_json") is not None

    def test_create_drawing_overlay_raises_without_bbox(
        self,
        db_session: Session,
        master_drawing: Drawing,
        inspection_run,
    ) -> None:
        record = map_evidence_to_overlay(
            EvidenceInput(
                evidence_id="unresolved",
                inspection_run_id=str(inspection_run.id),
                drawing_id=str(master_drawing.id),
                note_text="",
                bbox=None,
            )
        )
        with pytest.raises(ValueError, match="no bbox"):
            create_drawing_overlay(db_session, record)

    def test_flag_unresolved_evidence_writes_table_and_meta(
        self,
        db_session: Session,
        project,
        master_drawing: Drawing,
        inspection_run,
    ) -> None:
        storage = StorageService(db_session)
        evidence = storage.create_evidence_record(
            project_id=cast(int, project.id),
            type="inspection_doc",
            trade=None,
            spec_section=None,
            title="report.pdf",
            storage_key="projects/1/evidence/test.pdf",
            content_type="application/pdf",
        )
        flag_unresolved_evidence(
            db_session,
            [
                UnresolvedEvidenceRecord(
                    evidence_id=str(evidence.id),
                    inspection_run_id=str(inspection_run.id),
                    master_drawing_id=str(master_drawing.id),
                    reason="No match",
                    extracted_terms=[_positioned("Roof", VocabCategory.LOCATION_TERM)],
                )
            ],
        )
        rows = (
            db_session.query(UnresolvedEvidence)
            .filter(UnresolvedEvidence.evidence_id == evidence.id)
            .all()
        )
        assert len(rows) == 1
        db_session.refresh(evidence)
        assert "documentPipelineUnresolved" in cast(dict[str, Any], evidence.meta)

    def test_list_unresolved_evidence_excludes_resolved_by_default(
        self,
        db_session: Session,
        project,
        master_drawing: Drawing,
        inspection_run,
    ) -> None:
        storage = StorageService(db_session)
        evidence = storage.create_evidence_record(
            project_id=cast(int, project.id),
            type="inspection_doc",
            trade=None,
            spec_section=None,
            title="report.pdf",
            storage_key="projects/1/evidence/test.pdf",
            content_type="application/pdf",
        )
        flag_unresolved_evidence(
            db_session,
            [
                UnresolvedEvidenceRecord(
                    evidence_id=str(evidence.id),
                    inspection_run_id=str(inspection_run.id),
                    master_drawing_id=str(master_drawing.id),
                    reason="Needs review",
                    extracted_terms=[_positioned("Roof", VocabCategory.LOCATION_TERM)],
                )
            ],
        )
        master_id = cast(int, master_drawing.id)
        open_items = list_unresolved_evidence(db_session, master_id)
        assert len(open_items) == 1
        open_items[0].resolved_by_human = True  # type: ignore[assignment]
        db_session.commit()
        assert list_unresolved_evidence(db_session, master_id) == []
        assert len(
            list_unresolved_evidence(db_session, master_id, include_resolved=True)
        ) == 1
