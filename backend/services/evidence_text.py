"""Evidence text helpers for full-document scans."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.models import EvidenceRecord


def build_full_evidence_text(evidence: EvidenceRecord) -> str:
    """Return merged evidence text without truncation."""
    return (evidence.text_content or "").strip()
