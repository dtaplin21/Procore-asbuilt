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


def test_build_fallback_identity_transform_shape(db: Session) -> None:
    svc = DrawingComparisonService(db)
    t = svc.build_fallback_identity_transform(page=2)
    assert t["type"] == "identity"
    assert t["matrix"] == [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
    assert t["confidence"] == 0.0
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
    assert result["type"] == "identity"
    assert result["confidence"] == 0.0


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
    assert "master_drawing" in result
    assert "sub_drawing" in result
    assert "alignment" in result
    assert "diffs" in result
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

    assert result["alignment"].id == alignment.id
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
