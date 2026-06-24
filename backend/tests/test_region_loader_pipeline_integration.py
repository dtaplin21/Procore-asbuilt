"""Proves build_region_index() output plugs directly into map_document_to_overlays().

Closes the loop: tagged drawing_regions rows → loader → DocumentEvidenceInput
→ full document pipeline, with no adapter between loader output and resolver input.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ai.pipelines import document_text_extraction as dte
from ai.pipelines.document_text_extraction import (
    BoundingBox,
    ExtractedDocument,
    PositionedWord,
    SourceFormat,
)
from ai.pipelines.inspection_mapping import DocumentEvidenceInput, map_document_to_overlays
from services import region_index_loader as loader_module
from services.region_index_loader import build_region_index
from tests.test_region_index_loader import (
    DrawingRegionSQLite,
    SQLiteModelBase,
    _insert_region,
    _rect_geometry,
)


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


@pytest.fixture
def db_session(monkeypatch: pytest.MonkeyPatch):
    engine = create_engine("sqlite:///:memory:")
    SQLiteModelBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    monkeypatch.setattr(loader_module, "DrawingRegion", DrawingRegionSQLite)
    yield session
    session.close()


class TestRegionLoaderFeedsPipelineDirectly:
    def test_loaded_region_resolves_a_real_uploaded_document(
        self,
        db_session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _insert_region(
            db_session,
            label="region_a",
            inspection_type_tags=["Underground Fire Water Rough In"],
            location_tags=["Utility MR"],
            geometry=_rect_geometry(0.05, 0.06, 0.08, 0.09),
        )

        load_result = build_region_index(db_session, 1)
        assert load_result.has_any_usable_regions

        words = _layout(
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
        fake_doc = ExtractedDocument(
            source_format=SourceFormat.NATIVE_PDF,
            page_count=1,
            words=words,
        )
        monkeypatch.setattr(dte, "_pdf_has_text_layer", lambda p: True)
        monkeypatch.setattr(dte, "_pdf_text_layer", lambda p: fake_doc)

        evidence = DocumentEvidenceInput(
            evidence_id="ev1",
            inspection_run_id="run1",
            master_drawing_id="1",
            file_path="report.pdf",
            region_index=load_result.regions,
        )

        overlays, unresolved = map_document_to_overlays(evidence)

        assert unresolved == []
        assert len(overlays) == 1
        overlay = overlays[0]
        assert overlay.bbox is not None
        assert overlay.bbox == pytest.approx((0.05, 0.06, 0.13, 0.15))
        assert "Rejected" in overlay.tags.inspection_statuses

    def test_untagged_regions_dont_create_false_matches(
        self,
        db_session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _insert_region(db_session, label="untagged_region")

        load_result = build_region_index(db_session, 1)
        assert load_result.regions == []
        assert load_result.untagged_region_count == 1

        words = _layout(["Final", "inspection", "at", "Roof"])
        fake_doc = ExtractedDocument(
            source_format=SourceFormat.NATIVE_PDF,
            page_count=1,
            words=words,
        )
        monkeypatch.setattr(dte, "_pdf_has_text_layer", lambda p: True)
        monkeypatch.setattr(dte, "_pdf_text_layer", lambda p: fake_doc)

        evidence = DocumentEvidenceInput(
            evidence_id="ev2",
            inspection_run_id="run1",
            master_drawing_id="1",
            file_path="report.pdf",
            region_index=load_result.regions,
        )

        overlays, unresolved = map_document_to_overlays(evidence)
        assert overlays == []
        assert len(unresolved) == 1
