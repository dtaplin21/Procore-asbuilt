"""
Normalized writeback contract builder.

The contract is the canonical snapshot of everything we know about an inspection
run before translating it into a Procore payload. It stitches together project,
run, evidence, overlays, and findings so downstream integrations have one shape
to reason about.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from models.models import Company, InspectionResult
from services.storage import StorageService

CONTRACT_VERSION = "2025-02-27"


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _safe_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _text_excerpt(text: Optional[str], limit: int = 600) -> Optional[str]:
    if not text:
        return None
    trimmed = text.strip()
    if not trimmed:
        return None
    return trimmed[:limit]


class ProjectContext(BaseModel):
    id: int
    name: str
    company_id: int
    procore_project_id: str
    procore_company_id: Optional[str] = None


class InspectionRunContext(BaseModel):
    id: int
    project_id: int
    master_drawing_id: int
    evidence_id: Optional[int] = None
    inspection_type: Optional[str] = None
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    error_message: Optional[str] = None


class MasterDrawingContext(BaseModel):
    id: int
    name: str
    source: str
    page_count: Optional[int] = None
    content_type: Optional[str] = None
    storage_key: Optional[str] = None
    file_url: Optional[str] = None


class EvidenceContext(BaseModel):
    id: int
    type: str
    title: str
    trade: Optional[str] = None
    spec_section: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)
    text_excerpt: Optional[str] = None
    storage_key: Optional[str] = None


class InspectionResultContext(BaseModel):
    id: int
    outcome: str
    notes: Optional[str] = None
    created_at: datetime


class OverlayContext(BaseModel):
    id: int
    status: str
    geometry: Dict[str, Any]
    meta: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class FindingContext(BaseModel):
    id: int
    type: str
    severity: str
    title: str
    description: str
    affected_items: List[str] = Field(default_factory=list)
    resolved: bool = False
    created_at: datetime


class WritebackContract(BaseModel):
    version: str = Field(default=CONTRACT_VERSION)
    project: ProjectContext
    inspection_run: InspectionRunContext
    inspection_result: Optional[InspectionResultContext] = None
    master_drawing: MasterDrawingContext
    evidence: Optional[EvidenceContext] = None
    overlays: List[OverlayContext] = Field(default_factory=list)
    finding: Optional[FindingContext] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


def build_writeback_contract(
    db: Session,
    project_id: int,
    inspection_run_id: int,
) -> WritebackContract:
    """
    Assemble the normalized writeback contract for a given inspection_run.

    Raises ValueError when required records are missing (project, run, drawing).
    """
    storage = StorageService(db)
    project = storage.get_project(project_id)
    if project is None:
        raise ValueError("Project not found")

    project_procore_id = getattr(project, "procore_project_id", None)
    if not project_procore_id:
        raise ValueError("Project has no procore_project_id; sync project from Procore first")

    run = storage.get_inspection_run(project_id, inspection_run_id)
    if run is None:
        raise ValueError("Inspection run not found")

    master_drawing_id = getattr(run, "master_drawing_id", None)
    if master_drawing_id is None:
        raise ValueError("Inspection run has no master_drawing_id")
    master_drawing = storage.get_drawing(project_id, int(master_drawing_id))
    if master_drawing is None:
        raise ValueError("Master drawing not found")

    evidence = None
    if getattr(run, "evidence_id", None) is not None:
        evidence = storage.get_evidence_record(project_id, int(getattr(run, "evidence_id")))

    result = (
        db.query(InspectionResult)
        .filter(InspectionResult.inspection_run_id == int(getattr(run, "id")))
        .order_by(InspectionResult.created_at.desc())
        .first()
    )

    overlays = storage.list_drawing_overlays(
        int(getattr(master_drawing, "id", 0)),
        inspection_run_id=int(getattr(run, "id", 0)),
    )

    company = (
        db.query(Company)
        .filter(Company.id == int(getattr(project, "company_id", 0)))
        .first()
    )

    project_ctx = ProjectContext(
        id=int(getattr(project, "id", 0)),
        name=str(project.name),
        company_id=int(getattr(project, "company_id", 0)),
        procore_project_id=str(project_procore_id),
        procore_company_id=str(getattr(company, "procore_company_id", "") or "") or None,
    )

    inspection_run_ctx = InspectionRunContext(
        id=int(getattr(run, "id", 0)),
        project_id=int(getattr(run, "project_id", 0)),
        master_drawing_id=int(getattr(run, "master_drawing_id", 0)),
        evidence_id=int(getattr(run, "evidence_id", 0)) if getattr(run, "evidence_id", None) is not None else None,
        inspection_type=(getattr(run, "inspection_type", None) or None),
        status=str(getattr(run, "status", "queued")),
        started_at=_ensure_utc(getattr(run, "started_at", None)),
        completed_at=_ensure_utc(getattr(run, "completed_at", None)),
        created_at=_ensure_utc(getattr(run, "created_at", None)),
        updated_at=_ensure_utc(getattr(run, "updated_at", None)),
        error_message=getattr(run, "error_message", None),
    )

    master_drawing_ctx = MasterDrawingContext(
        id=int(getattr(master_drawing, "id", 0)),
        name=str(master_drawing.name),
        source=str(master_drawing.source),
        page_count=getattr(master_drawing, "page_count", None),
        content_type=getattr(master_drawing, "content_type", None),
        storage_key=getattr(master_drawing, "storage_key", None),
        file_url=getattr(master_drawing, "file_url", None),
    )

    evidence_ctx: Optional[EvidenceContext] = None
    if evidence is not None:
        evidence_ctx = EvidenceContext(
            id=int(getattr(evidence, "id", 0)),
            type=str(evidence.type),
            title=str(evidence.title),
            trade=(getattr(evidence, "trade", None) or None),
            spec_section=(getattr(evidence, "spec_section", None) or None),
            meta=_safe_dict(getattr(evidence, "meta", None)),
            text_excerpt=_text_excerpt(getattr(evidence, "text_content", None)),
            storage_key=getattr(evidence, "storage_key", None),
        )

    inspection_result_ctx: Optional[InspectionResultContext] = None
    if result is not None:
        inspection_result_ctx = InspectionResultContext(
            id=int(getattr(result, "id", 0)),
            outcome=str(getattr(result, "outcome", "unknown") or "unknown"),
            notes=getattr(result, "notes", None),
            created_at=_ensure_utc(getattr(result, "created_at", None)) or datetime.now(timezone.utc),
        )

    overlay_contexts: List[OverlayContext] = []
    for overlay in overlays:
            overlay_contexts.append(
            OverlayContext(
                id=int(getattr(overlay, "id", 0)),
                status=str(getattr(overlay, "status", "unknown") or "unknown"),
                geometry=_safe_dict(getattr(overlay, "geometry", None)),
                meta=_safe_dict(getattr(overlay, "meta", None)),
                created_at=_ensure_utc(getattr(overlay, "created_at", None)) or datetime.now(timezone.utc),
            )
        )

    finding_ctx: Optional[FindingContext] = None
    finding_id: Optional[int] = None
    for overlay in overlay_contexts:
        meta = overlay.meta
        candidate = meta.get("finding_id")
        if isinstance(candidate, int):
            finding_id = candidate
            break

    if finding_id is not None:
        finding = storage.get_finding(finding_id, project_id=project_id)
        if finding is not None:
            finding_ctx = FindingContext(
                id=int(getattr(finding, "id", 0)),
                type=str(finding.type),
                severity=str(finding.severity),
                title=str(finding.title),
                description=str(finding.description),
                affected_items=list(getattr(finding, "affected_items", []) or []),
                resolved=bool(getattr(finding, "resolved", False)),
                created_at=_ensure_utc(getattr(finding, "created_at", None)) or datetime.now(timezone.utc),
            )

    pages: Set[int] = set()
    for overlay in overlay_contexts:
        page = overlay.geometry.get("page")
        if isinstance(page, (int, float)):
            pages.add(int(page))

    meta: Dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "overlay_count": len(overlay_contexts),
        "has_finding": finding_ctx is not None,
        "outcome": (
            inspection_result_ctx.outcome
            if inspection_result_ctx is not None
            else "unknown"
        ),
        "inspector": {
            "name": "AI Platform",
            "entity": "QC/QA",
        },
        "dry_run_supported": True,
    }
    if pages:
        meta["pages"] = sorted(pages)
    if evidence_ctx is not None:
        meta["evidence_type"] = evidence_ctx.type

    return WritebackContract(
        project=project_ctx,
        inspection_run=inspection_run_ctx,
        inspection_result=inspection_result_ctx,
        master_drawing=master_drawing_ctx,
        evidence=evidence_ctx,
        overlays=overlay_contexts,
        finding=finding_ctx,
        meta=meta,
    )


__all__ = ["WritebackContract", "build_writeback_contract", "CONTRACT_VERSION"]
