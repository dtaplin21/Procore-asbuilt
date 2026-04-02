"""
Unit and integration tests for drawing comparison service.

Unit tests: validation, fallback transform, feature extraction, matching,
transform estimation, validation rules.

Integration tests: compare flow with DB, alignment lifecycle, reuse.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from database import SessionLocal
from models.models import Company, Drawing, Project
from services.drawing_comparison import (
    DrawingComparisonService,
    compare_sub_drawing_to_master,
    run_alignment_lifecycle,
)
from services.storage import StorageService


def _unique_id() -> str:
    return uuid.uuid4().hex[:12]


@pytest.fixture
def db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def company(db: Session) -> Company:
    company = Company(name="Test Co", procore_company_id=f"pc-{_unique_id()}")
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


@pytest.fixture
def project(db: Session, company: Company) -> Project:
    proj = Project(
        company_id=company.id,
        name="Test Project",
        procore_project_id=f"pp-{_unique_id()}",
    )
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return proj


@pytest.fixture
def master_drawing(db: Session, project: Project) -> Drawing:
    drawing = Drawing(
        project_id=project.id,
        source="upload",
        name="master.pdf",
        storage_key=None,
        content_type="application/pdf",
    )
    db.add(drawing)
    db.commit()
    db.refresh(drawing)
    return drawing


@pytest.fixture
def sub_drawing(db: Session, project: Project) -> Drawing:
    drawing = Drawing(
        project_id=project.id,
        source="upload",
        name="sub.pdf",
        storage_key=None,
        content_type="application/pdf",
    )
    db.add(drawing)
    db.commit()
    db.refresh(drawing)
    return drawing


# ---------------------------------------------------------------------------
# Unit tests — build_fallback_identity_transform
# ---------------------------------------------------------------------------


def test_build_identity_transform_shape() -> None:
    from services.drawing_comparison import build_identity_transform

    t = build_identity_transform()
    assert t["type"] == "affine"
    assert t["matrix"] == [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    assert t["confidence"] == 1.0
    assert t["meta"]["note"] == "Identity transform for MVP overlay behavior"


def test_parse_alignment_transform_overlay_accepts_json_string() -> None:
    import json

    from services.drawing_comparison import (
        build_identity_transform,
        parse_alignment_transform_for_overlay,
    )

    raw = json.dumps(build_identity_transform())
    out = parse_alignment_transform_for_overlay(raw)
    assert out is not None
    assert out.type == "affine"
    assert len(out.matrix) == 9
    assert out.matrix == [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]


def test_build_fallback_identity_transform_shape(db: Session) -> None:
    svc = DrawingComparisonService(db)
    t = svc.build_fallback_identity_transform(page=2)
    assert t["type"] == "affine"
    assert t["matrix"] == [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    assert t["confidence"] == 1.0
    assert t["meta"]["note"] == "Identity transform for MVP overlay behavior"
    assert t["residual_error"] is None
    assert t["page"] == 2


# ---------------------------------------------------------------------------
# Unit tests — _validate_project_drawings
# ---------------------------------------------------------------------------


def test_validate_project_drawings_raises_when_master_not_found(
    db: Session, project: Project, sub_drawing: Drawing
) -> None:
    svc = DrawingComparisonService(db)
    with pytest.raises(ValueError, match="Master drawing 99999 not found"):
        svc._validate_project_drawings(project.id, 99999, sub_drawing.id)


def test_validate_project_drawings_raises_when_sub_not_found(
    db: Session, project: Project, master_drawing: Drawing
) -> None:
    svc = DrawingComparisonService(db)
    with pytest.raises(ValueError, match="Sub drawing 99999 not found"):
        svc._validate_project_drawings(project.id, master_drawing.id, 99999)


def test_validate_project_drawings_raises_when_master_equals_sub(
    db: Session, project: Project, master_drawing: Drawing
) -> None:
    svc = DrawingComparisonService(db)
    with pytest.raises(ValueError, match="Master drawing and sub drawing must be different"):
        svc._validate_project_drawings(project.id, master_drawing.id, master_drawing.id)


def test_validate_project_drawings_returns_master_sub_when_valid(
    db: Session, project: Project, master_drawing: Drawing, sub_drawing: Drawing
) -> None:
    svc = DrawingComparisonService(db)
    master, sub = svc._validate_project_drawings(
        project.id, master_drawing.id, sub_drawing.id
    )
    assert master.id == master_drawing.id
    assert sub.id == sub_drawing.id


# ---------------------------------------------------------------------------
# Unit tests — extract_features, match, estimate (with mocks)
# ---------------------------------------------------------------------------


def test_extract_features_returns_empty_when_image_none(db: Session) -> None:
    svc = DrawingComparisonService(db)
    result = svc.extract_features(None)
    assert result == {}


def test_match_alignment_features_returns_empty_when_insufficient(
    db: Session,
) -> None:
    svc = DrawingComparisonService(db)
    master_feat = {"descriptors": None, "keypoints": [], "shape": [100, 100]}
    sub_feat = {"descriptors": None, "keypoints": [], "shape": [100, 100]}
    result = svc.match_alignment_features(master_feat, sub_feat)
    assert result["source_points"] == []
    assert result["target_points"] == []


def test_estimate_transform_returns_fallback_when_insufficient_matches(
    db: Session,
) -> None:
    svc = DrawingComparisonService(db)
    matches = {"source_points": [{"x": 0, "y": 0}], "target_points": [{"x": 0, "y": 0}]}
    result = svc.estimate_transform(matches)
    assert result["type"] == "affine"
    assert result["confidence"] == 1.0


# ---------------------------------------------------------------------------
# Unit tests — validate_transform
# ---------------------------------------------------------------------------


def test_validate_transform_raises_when_missing_transform(db: Session) -> None:
    svc = DrawingComparisonService(db)
    with pytest.raises(ValueError, match="Missing transform"):
        svc.validate_transform({})


def test_validate_transform_raises_when_missing_matrix(db: Session) -> None:
    svc = DrawingComparisonService(db)
    with pytest.raises(ValueError, match="Missing or invalid transform matrix"):
        svc.validate_transform({"matrix": None, "source_points": [], "target_points": []})


def test_validate_transform_raises_when_insufficient_points(db: Session) -> None:
    svc = DrawingComparisonService(db)
    with pytest.raises(ValueError, match="Insufficient matched points"):
        svc.validate_transform(
            {
                "matrix": [1, 0, 0, 0, 1, 0, 0, 0, 1],
                "source_points": [{"x": 0, "y": 0}],
                "target_points": [{"x": 0, "y": 0}],
                "confidence": 0.9,
            }
        )


def test_validate_transform_raises_when_low_confidence(db: Session) -> None:
    svc = DrawingComparisonService(db)
    pts = [{"x": float(i), "y": float(i)} for i in range(5)]
    with pytest.raises(ValueError, match="Alignment confidence.*below threshold"):
        svc.validate_transform(
            {
                "matrix": [1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0],
                "source_points": pts,
                "target_points": pts,
                "confidence": 0.5,
            }
        )


# ---------------------------------------------------------------------------
# Integration tests — storage get_reusable_alignment
# ---------------------------------------------------------------------------


def test_get_reusable_alignment_returns_none_when_no_alignment(
    db: Session, master_drawing: Drawing, sub_drawing: Drawing
) -> None:
    storage = StorageService(db)
    result = storage.get_reusable_alignment(master_drawing.id, sub_drawing.id)
    assert result is None


def test_get_reusable_alignment_returns_none_when_queued(
    db: Session, master_drawing: Drawing, sub_drawing: Drawing
) -> None:
    storage = StorageService(db)
    alignment = storage.create_drawing_alignment(
        master_drawing.id, sub_drawing.id, "feature_match"
    )
    result = storage.get_reusable_alignment(master_drawing.id, sub_drawing.id)
    assert result is None  # queued, no transform


def test_get_reusable_alignment_returns_alignment_when_complete_with_transform(
    db: Session, master_drawing: Drawing, sub_drawing: Drawing
) -> None:
    storage = StorageService(db)
    alignment = storage.create_drawing_alignment(
        master_drawing.id, sub_drawing.id, "manual"
    )
    result = storage.get_reusable_alignment(master_drawing.id, sub_drawing.id)
    assert result is not None
    assert result.id == alignment.id
    assert getattr(result, "transform", None) is not None


# ---------------------------------------------------------------------------
# Integration tests — compare flow
# ---------------------------------------------------------------------------


@patch("services.drawing_comparison.run_drawing_diff")
@patch("services.drawing_comparison.run_alignment_lifecycle")
def test_compare_creates_alignment_and_runs_lifecycle_when_feature_match(
    mock_lifecycle: MagicMock,
    mock_diff: MagicMock,
    db: Session,
    project: Project,
) -> None:
    """When drawings have storage_key, creates feature_match alignment and runs lifecycle."""
    master = Drawing(
        project_id=project.id,
        source="upload",
        name="master.pdf",
        storage_key="drawings/fake-master.pdf",
        content_type="application/pdf",
    )
    sub = Drawing(
        project_id=project.id,
        source="upload",
        name="sub.pdf",
        storage_key="drawings/fake-sub.pdf",
        content_type="application/pdf",
    )
    db.add(master)
    db.add(sub)
    db.commit()
    db.refresh(master)
    db.refresh(sub)

    mock_diff.return_value = []
    result = compare_sub_drawing_to_master(
        db,
        project_id=project.id,
        master_drawing_id=master.id,
        sub_drawing_id=sub.id,
    )
    assert result.master_drawing is not None
    assert result.sub_drawing is not None
    assert result.alignment is not None
    assert result.diffs is not None
    mock_lifecycle.assert_called_once()
    mock_diff.assert_called_once()


@patch("services.drawing_comparison.run_drawing_diff")
def test_compare_reuses_existing_alignment_when_transform_valid(
    mock_diff: MagicMock,
    db: Session,
    project: Project,
    master_drawing: Drawing,
    sub_drawing: Drawing,
) -> None:
    storage = StorageService(db)
    alignment = storage.create_drawing_alignment(
        master_drawing.id, sub_drawing.id, "manual"
    )
    mock_diff.return_value = []

    with patch("services.drawing_comparison.run_alignment_lifecycle") as mock_lifecycle:
        result = compare_sub_drawing_to_master(
            db,
            project_id=project.id,
            master_drawing_id=master_drawing.id,
            sub_drawing_id=sub_drawing.id,
        )
        mock_lifecycle.assert_not_called()

    assert result.alignment.id == alignment.id
    mock_diff.assert_called_once()


@patch("services.drawing_comparison.run_drawing_diff")
def test_compare_raises_when_master_not_found(
    mock_diff: MagicMock,
    db: Session,
    project: Project,
    sub_drawing: Drawing,
) -> None:
    with pytest.raises(ValueError, match="Master drawing 99999 not found"):
        compare_sub_drawing_to_master(
            db,
            project_id=project.id,
            master_drawing_id=99999,
            sub_drawing_id=sub_drawing.id,
        )
    mock_diff.assert_not_called()


@patch("services.drawing_comparison.run_drawing_diff")
def test_compare_force_recompute_runs_lifecycle_even_with_existing(
    mock_diff: MagicMock,
    db: Session,
    project: Project,
    master_drawing: Drawing,
    sub_drawing: Drawing,
) -> None:
    storage = StorageService(db)
    storage.create_drawing_alignment(master_drawing.id, sub_drawing.id, "manual")
    mock_diff.return_value = []

    with patch("services.drawing_comparison.run_alignment_lifecycle") as mock_lifecycle:
        compare_sub_drawing_to_master(
            db,
            project_id=project.id,
            master_drawing_id=master_drawing.id,
            sub_drawing_id=sub_drawing.id,
            force_recompute=True,
        )
        mock_lifecycle.assert_called_once()


# ---------------------------------------------------------------------------
# Integration tests — run_alignment_lifecycle
# ---------------------------------------------------------------------------


@patch("services.drawing_comparison.DrawingComparisonService.compute_alignment_transform")
def test_run_alignment_lifecycle_updates_to_complete_on_success(
    mock_compute: MagicMock,
    db: Session,
    project: Project,
    master_drawing: Drawing,
    sub_drawing: Drawing,
) -> None:
    mock_compute.return_value = {
        "type": "homography",
        "matrix": [1, 0, 0, 0, 1, 0, 0, 0, 1],
        "confidence": 0.9,
        "residual_error": 0.01,
        "page": 1,
    }
    storage = StorageService(db)
    alignment = storage.create_drawing_alignment(
        master_drawing.id, sub_drawing.id, "feature_match"
    )

    run_alignment_lifecycle(db, alignment, master_drawing, sub_drawing)

    db.refresh(alignment)
    assert getattr(alignment, "status", None) == "complete"
    assert getattr(alignment, "transform", None) is not None


@patch("services.drawing_comparison.DrawingComparisonService.compute_alignment_transform")
def test_run_alignment_lifecycle_updates_to_failed_on_error(
    mock_compute: MagicMock,
    db: Session,
    project: Project,
    master_drawing: Drawing,
    sub_drawing: Drawing,
) -> None:
    mock_compute.side_effect = RuntimeError("Compute failed")
    storage = StorageService(db)
    alignment = storage.create_drawing_alignment(
        master_drawing.id, sub_drawing.id, "feature_match"
    )

    with pytest.raises(RuntimeError, match="Compute failed"):
        run_alignment_lifecycle(db, alignment, master_drawing, sub_drawing)

    db.refresh(alignment)
    assert getattr(alignment, "status", None) == "failed"
    assert "Compute failed" in str(getattr(alignment, "error_message", "") or "")


# ---------------------------------------------------------------------------
# Integration tests — alignments history
# ---------------------------------------------------------------------------


def test_list_alignments_returns_newest_first_with_sub_drawing(
    db: Session,
    project: Project,
    master_drawing: Drawing,
    sub_drawing: Drawing,
) -> None:
    """Alignments history: newest first, subDrawing.id and subDrawing.name included."""
    storage = StorageService(db)
    a1 = storage.create_drawing_alignment(
        master_drawing.id, sub_drawing.id, "manual"
    )
    db.refresh(a1)

    svc = DrawingComparisonService(db)
    result = svc.list_alignments(project.id, master_drawing.id)

    assert "alignments" in result
    alignments = result["alignments"]
    assert len(alignments) >= 1
    first = alignments[0]
    assert first.id == a1.id
    assert first.project_id == project.id
    assert first.master_drawing_id == master_drawing.id
    assert first.sub_drawing_id == sub_drawing.id
    assert first.sub_drawing is not None
    assert first.sub_drawing.id == sub_drawing.id
    assert first.sub_drawing.name == sub_drawing.name


def test_list_alignments_raises_when_master_not_found(
    db: Session, project: Project
) -> None:
    svc = DrawingComparisonService(db)
    with pytest.raises(ValueError, match="Master drawing 99999 not found"):
        svc.list_alignments(project.id, 99999)


# ---------------------------------------------------------------------------
# Integration tests — diffs history
# ---------------------------------------------------------------------------


def test_list_diffs_returns_newest_first_with_required_fields(
    db: Session,
    project: Project,
    master_drawing: Drawing,
    sub_drawing: Drawing,
) -> None:
    """Diffs history: newest first, includes summary, severity, createdAt, diffRegions."""
    storage = StorageService(db)
    alignment = storage.create_drawing_alignment(
        master_drawing.id, sub_drawing.id, "manual"
    )
    diff = storage.create_drawing_diff(
        alignment.id,
        summary="Three differences detected",
        severity="medium",
        diff_regions=[
            {
                "page": 1,
                "bbox": {"x": 120, "y": 300, "width": 42, "height": 25},
                "changeType": "added_markup",
                "note": "New inspection symbol",
            }
        ],
    )
    db.refresh(diff)

    svc = DrawingComparisonService(db)
    result = svc.list_diffs(project.id, master_drawing.id)

    assert "diffs" in result
    diffs = result["diffs"]
    assert len(diffs) >= 1
    first = diffs[0]
    assert first.id == diff.id
    assert first.alignment_id == alignment.id
    assert first.summary == "Three differences detected"
    assert first.severity == "medium"
    assert first.created_at is not None
    assert len(first.diff_regions) == 1
    assert first.diff_regions[0].page == 1
    assert first.diff_regions[0].change_type == "added_markup"
    assert first.diff_regions[0].note == "New inspection symbol"


def test_list_diffs_filtered_by_alignment_id(
    db: Session,
    project: Project,
    master_drawing: Drawing,
    sub_drawing: Drawing,
) -> None:
    """Diffs filtered to one alignment only returns diffs from that alignment."""
    storage = StorageService(db)
    a1 = storage.create_drawing_alignment(
        master_drawing.id, sub_drawing.id, "manual"
    )
    sub2 = Drawing(
        project_id=project.id,
        source="upload",
        name="sub2.pdf",
        storage_key=None,
        content_type="application/pdf",
    )
    db.add(sub2)
    db.commit()
    db.refresh(sub2)
    a2 = storage.create_drawing_alignment(master_drawing.id, sub2.id, "manual")

    storage.create_drawing_diff(
        a1.id,
        summary="Diff for alignment 1",
        severity="low",
        diff_regions=[{"page": 1, "bbox": {"x": 0, "y": 0, "width": 10, "height": 10}}],
    )
    storage.create_drawing_diff(
        a2.id,
        summary="Diff for alignment 2",
        severity="high",
        diff_regions=[{"page": 1, "bbox": {"x": 0, "y": 0, "width": 20, "height": 20}}],
    )

    svc = DrawingComparisonService(db)
    result = svc.list_diffs(project.id, master_drawing.id, alignment_id=a1.id)

    assert "diffs" in result
    diffs = result["diffs"]
    assert len(diffs) == 1
    assert diffs[0].alignment_id == a1.id
    assert diffs[0].summary == "Diff for alignment 1"
    assert diffs[0].severity == "low"


def test_list_diffs_raises_when_master_not_found(
    db: Session, project: Project
) -> None:
    svc = DrawingComparisonService(db)
    with pytest.raises(ValueError, match="Master drawing 99999 not found"):
        svc.list_diffs(project.id, 99999)
