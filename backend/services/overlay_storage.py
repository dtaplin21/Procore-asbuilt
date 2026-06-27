"""
Persistence layer for inspection_mapping.py's output. Two functions,
matching the names used in IMPLEMENTATION_GUIDE.md's route snippet:

  - create_drawing_overlay(db, overlay): persists one DrawingOverlayRecord
  - flag_unresolved_evidence(db, unresolved): persists one or more
    UnresolvedEvidenceRecord, for a reviewer to follow up on

Both take the dataclasses inspection_mapping.py already produces
(DrawingOverlayRecord, UnresolvedEvidenceRecord) and convert them to the
ORM rows defined in models/drawing_overlay.py. Called directly from
api.routes.evidence after map_document_to_overlays().

Reconciled with this codebase: integer PKs/FKs, master_drawing_id,
geometry JSON (not separate bbox columns), tags_json as JSON dict,
created_at as upload timestamp (not a separate uploaded_at column).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ai.pipelines.inspection_mapping import DrawingOverlayRecord, UnresolvedEvidenceRecord
from models.drawing_overlay import DrawingOverlay, UnresolvedEvidence
from models.models import EvidenceRecord

# Per the region-visibility spec (§2): this derived classification is
# kept ONLY for analytics/filters on the drawing_overlays.status column.
# It must NEVER drive region bold styling or stroke color on the
# Objects viewer (bold is status-agnostic) — the hover tooltip's status
# line uses the full vocab string from tags_json.inspectionStatuses[0]
# instead (see region_inspection_summary.py's _inspection_status_display).
_PASS_STATUSES = {"Approved", "Approved As Noted", "Passed", "Completed", "Closed"}
_FAIL_STATUSES = {"Rejected", "Failed"}


def _derive_pass_fail_status(inspection_statuses: list[str]) -> str:
    """pass | fail | unknown, derived from the full vocab status list.

    Fail takes priority over pass if a document somehow carries both
    (e.g. a re-inspection note correcting an earlier "Approved" mention).
    """
    statuses = set(inspection_statuses)
    if statuses & _FAIL_STATUSES:
        return "fail"
    if statuses & _PASS_STATUSES:
        return "pass"
    return "unknown"


def _bbox_to_geometry(
    bbox: tuple[float, float, float, float],
    *,
    label: str,
) -> dict[str, Any]:
    x0, y0, x1, y1 = bbox
    return {
        "page": 1,
        "type": "rect",
        "x": x0,
        "y": y0,
        "width": x1 - x0,
        "height": y1 - y0,
        "label": label,
    }


def _build_overlay_row(record: DrawingOverlayRecord) -> DrawingOverlay:
    if record.bbox is None:
        raise ValueError(
            f"DrawingOverlayRecord {record.id!r} has no bbox — only call "
            f"create_drawing_overlay for resolved overlays. Unresolved "
            f"evidence belongs in flag_unresolved_evidence instead."
        )

    tags_dict = record.tags.to_dict()
    meta: dict[str, Any] = {
        "label": record.label,
        "severity": record.severity,
        "pipelineOverlayId": record.id,
        **tags_dict,
    }
    region_id: int | None = None
    if record.region_id is not None and str(record.region_id).strip().isdigit():
        region_id = int(record.region_id)

    return DrawingOverlay(
        master_drawing_id=int(record.drawing_id),
        inspection_run_id=int(record.inspection_run_id),
        region_id=region_id,
        geometry=_bbox_to_geometry(record.bbox, label=record.label),
        status=_derive_pass_fail_status(record.tags.inspection_statuses or []),
        meta=meta,
        label=record.label,
        severity=record.severity,
        confidence_label=record.tags.confidence_label,
        inspection_date=record.inspection_date,
        tags_json=tags_dict,
    )


def create_drawing_overlay(db: Session, overlay: DrawingOverlayRecord) -> DrawingOverlay:
    """Persist one resolved overlay. Returns the saved ORM row (with its id)."""
    row = _build_overlay_row(overlay)
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return row


def create_drawing_overlays(
    db: Session,
    overlays: list[DrawingOverlayRecord],
) -> list[DrawingOverlay]:
    """Batch convenience wrapper — one commit for the whole batch."""
    rows = [_build_overlay_row(overlay) for overlay in overlays]
    if not rows:
        return []

    db.add_all(rows)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    for row in rows:
        db.refresh(row)
    return rows


def _mirror_unresolved_to_evidence_meta(
    db: Session,
    unresolved: list[UnresolvedEvidenceRecord],
) -> None:
    """Keep evidence.meta in sync for callers that still read the legacy field."""
    payloads_by_evidence: dict[int, list[dict[str, Any]]] = {}
    for item in unresolved:
        evidence_id = int(item.evidence_id)
        payloads_by_evidence.setdefault(evidence_id, []).append(item.to_dict())

    if not payloads_by_evidence:
        return

    for evidence_id, payloads in payloads_by_evidence.items():
        evidence = db.query(EvidenceRecord).filter(EvidenceRecord.id == evidence_id).first()
        if evidence is None:
            continue
        meta = dict(getattr(evidence, "meta", None) or {})
        meta["documentPipelineUnresolved"] = payloads
        setattr(evidence, "meta", meta)

    db.commit()


def flag_unresolved_evidence(
    db: Session,
    unresolved: list[UnresolvedEvidenceRecord],
) -> list[UnresolvedEvidence]:
    """Persist evidence that couldn't be auto-placed, for human review."""
    rows: list[UnresolvedEvidence] = []
    for record in unresolved:
        rows.append(
            UnresolvedEvidence(
                evidence_id=int(record.evidence_id),
                inspection_run_id=int(record.inspection_run_id),
                master_drawing_id=int(record.master_drawing_id),
                reason=record.reason,
                extracted_terms_json=[term.to_dict() for term in record.extracted_terms],
                resolved_by_human=False,
            )
        )

    if rows:
        db.add_all(rows)
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
        for row in rows:
            db.refresh(row)
        _mirror_unresolved_to_evidence_meta(db, unresolved)

    return rows


def list_unresolved_evidence(
    db: Session,
    master_drawing_id: int | str,
    *,
    include_resolved: bool = False,
) -> list[UnresolvedEvidence]:
    """Unresolved placements for a master drawing (default: still needs review)."""
    query = db.query(UnresolvedEvidence).filter(
        UnresolvedEvidence.master_drawing_id == int(master_drawing_id)
    )
    if not include_resolved:
        query = query.filter(UnresolvedEvidence.resolved_by_human.is_(False))
    return query.order_by(UnresolvedEvidence.created_at.desc()).all()
