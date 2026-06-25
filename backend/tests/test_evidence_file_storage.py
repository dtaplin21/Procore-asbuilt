"""Tests for services.evidence_file_storage."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.evidence_file_storage import (
    UnsupportedEvidenceFileType,
    delete_upload,
    save_upload,
)


def test_save_upload_writes_uuid_file(tmp_path: Path) -> None:
    saved = save_upload("report.PDF", b"%PDF-1.4", storage_root=tmp_path)
    assert saved.parent == tmp_path
    assert saved.suffix == ".pdf"
    assert saved.read_bytes() == b"%PDF-1.4"


def test_save_upload_rejects_unknown_extension(tmp_path: Path) -> None:
    with pytest.raises(UnsupportedEvidenceFileType):
        save_upload("notes.txt", b"hello", storage_root=tmp_path)


def test_save_upload_rejects_empty_bytes(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="empty"):
        save_upload("report.pdf", b"", storage_root=tmp_path)


def test_delete_upload_is_best_effort(tmp_path: Path) -> None:
    saved = save_upload("photo.jpg", b"jpg", storage_root=tmp_path)
    delete_upload(saved)
    assert not saved.exists()
    delete_upload(saved)
