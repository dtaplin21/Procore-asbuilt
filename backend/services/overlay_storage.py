"""Persist document-pipeline overlay records and unresolved evidence flags."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ai.pipelines.inspection_mapping import DrawingOverlayRecord, UnresolvedEvidenceRecord
from models.models import DrawingOverlay, UnresolvedEvidence
from services.storage import StorageService


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


def create_drawing_overlays(
    db: Session,
    overlays: list[DrawingOverlayRecord],
) -> list[DrawingOverlay]:
    """Persist illustrative pipeline overlays as ``drawing_overlays`` rows."""
    storage = StorageService(db)
    saved: list[DrawingOverlay] = []

    for record in overlays:
        if record.bbox is None:
            continue

        tags_dict = record.tags.to_dict()
        meta: dict[str, Any] = {
            "label": record.label,
            "severity": record.severity,
            "pipelineOverlayId": record.id,
            **tags_dict,
        }
        overlay = storage.create_drawing_overlay(
            int(record.drawing_id),
            _bbox_to_geometry(record.bbox, label=record.label),
            _overlay_status_from_tags(record.tags),
            meta=meta,
            inspection_run_id=int(record.inspection_run_id),
            label=record.label,
            severity=record.severity,
            confidence_label=record.tags.confidence_label,
            inspection_date=record.inspection_date,
            tags_json=tags_dict,
        )
        saved.append(overlay)

    return saved


def flag_unresolved_evidence(
    db: Session,
    unresolved: list[UnresolvedEvidenceRecord],
    *,
    evidence_id: int,
    project_id: int,
) -> list[UnresolvedEvidence]:
    """Persist unresolved document placements for reviewer follow-up."""
    if not unresolved:
        return []

    storage = StorageService(db)
    evidence = storage.get_evidence_record(project_id, evidence_id)
    if evidence is None:
        return []

    saved: list[UnresolvedEvidence] = []
    for item in unresolved:
        row = UnresolvedEvidence(
            evidence_id=evidence_id,
            inspection_run_id=int(item.inspection_run_id),
            master_drawing_id=int(item.master_drawing_id),
            reason=item.reason,
            extracted_terms_json=[term.to_dict() for term in item.extracted_terms],
            resolved_by_human=False,
        )
        db.add(row)
        saved.append(row)

    meta = dict(getattr(evidence, "meta", None) or {})
    meta["documentPipelineUnresolved"] = [item.to_dict() for item in unresolved]
    setattr(evidence, "meta", meta)

    db.commit()
    for row in saved:
        db.refresh(row)
    db.refresh(evidence)
    return saved
