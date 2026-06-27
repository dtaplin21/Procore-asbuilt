"""Persistence layer for inspection_mapping.py pipeline output.

Converts ``DrawingOverlayRecord`` / ``UnresolvedEvidenceRecord`` dataclasses
into ORM rows on ``drawing_overlays`` and ``unresolved_evidence``. Called
directly from ``api.routes.evidence`` after ``map_document_to_overlays()``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ai.pipelines.inspection_mapping import DrawingOverlayRecord, UnresolvedEvidenceRecord
from models.drawing_overlay import DrawingOverlay, UnresolvedEvidence
from models.models import EvidenceRecord


def _overlay_status_from_tags(tags: Any) -> str:
    statuses = getattr(tags, "inspection_statuses", None) or []
    if any(s in {"Passed", "Approved"} for s in statuses):
        return "pass"
    if any(s in {"Rejected", "Failed"} for s in statuses):
        return "fail"
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
        status=_overlay_status_from_tags(record.tags),
        meta=meta,
        label=record.label,
        severity=record.severity,
        confidence_label=record.tags.confidence_label,
        inspection_date=record.inspection_date,
        tags_json=tags_dict,
    )


def create_drawing_overlay(db: Session, overlay: DrawingOverlayRecord) -> DrawingOverlay:
    """Persist one resolved overlay and return the saved ORM row."""
    row = _build_overlay_row(overlay)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def create_drawing_overlays(
    db: Session,
    overlays: list[DrawingOverlayRecord],
) -> list[DrawingOverlay]:
    """Batch persist — one commit for the whole upload."""
    rows: list[DrawingOverlay] = []
    for overlay in overlays:
        if overlay.bbox is None:
            continue
        rows.append(_build_overlay_row(overlay))

    if not rows:
        return []

    db.add_all(rows)
    db.commit()
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
    """Persist evidence that could not be auto-placed for reviewer follow-up."""
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
        db.commit()
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
