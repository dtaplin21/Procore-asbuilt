"""
Normalized writeback contract builder.

The contract is the canonical snapshot of everything we know about an inspection
run before translating it into a Procore payload. It stitches together project,
run, evidence, overlays, and findings so downstream integrations have one shape
to reason about.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Set, Union

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from models.models import Company, InspectionResult
from services.storage import StorageService

if TYPE_CHECKING:
    from models.models import DrawingOverlay

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


_TITLE_KEYS = ("title", "label", "issue", "problem", "summary", "name")
_DESCRIPTION_KEYS = ("description", "notes", "note", "detail", "message", "summary", "text", "reason")
_SEVERITY_KEYS = ("severity", "priority", "impact", "status", "level")
_LOCATION_KEYS = ("location", "region", "region_label", "region_name", "area", "coordinates")
_ISSUE_LIST_KEYS = ("issues", "problems", "findings", "items", "anomalies")
_SEVERITY_ALIASES = {
    "critical": "critical",
    "high": "high",
    "med": "medium",
    "medium": "medium",
    "moderate": "medium",
    "warning": "medium",
    "low": "low",
    "minor": "low",
    "pass": "low",
    "fail": "high",
    "severe": "high",
    "alert": "high",
}


def _pick_first_str(meta: Dict[str, Any], keys: Sequence[str]) -> Optional[str]:
    for key in keys:
        value = meta.get(key)
        if isinstance(value, str):
            trimmed = value.strip()
            if trimmed:
                return trimmed
    return None


def _normalize_severity(raw: Any, status: str) -> str:
    default = "high" if status == "fail" else "medium" if status == "unknown" else "low"
    if raw is None:
        return default
    if isinstance(raw, (int, float)):
        if raw >= 0.85:
            return "critical"
        if raw >= 0.6:
            return "high"
        if raw >= 0.35:
            return "medium"
        return "low"
    value = str(raw).strip().lower()
    if not value:
        return default
    if value in _SEVERITY_ALIASES:
        return _SEVERITY_ALIASES[value]
    if value.startswith("crit"):
        return "critical"
    if value.startswith("hi"):
        return "high"
    if value.startswith("med"):
        return "medium"
    if value.startswith("low"):
        return "low"
    if value in ("mixed", "unknown"):
        return "medium"
    return default


def _build_location(meta: Dict[str, Any], geometry: Dict[str, Any]) -> Dict[str, Any]:
    location: Dict[str, Any] = {}
    for key in _LOCATION_KEYS:
        value = meta.get(key)
        if isinstance(value, dict):
            location.update(value)
        elif isinstance(value, str) and value.strip():
            field = "label" if key in ("location", "region_label", "region_name") else key
            if field not in location:
                location[field] = value.strip()
    page = meta.get("page")
    if isinstance(page, (int, float)):
        location.setdefault("page", int(page))
    if geometry:
        location.setdefault("geometry", geometry)
    return location


def _coerce_overlay_payload(overlay: Union[Dict[str, Any], "DrawingOverlay"]) -> Dict[str, Any]:
    if isinstance(overlay, dict):
        return {
            "id": overlay.get("id"),
            "status": str(overlay.get("status", "unknown") or "unknown").lower(),
            "geometry": _safe_dict(overlay.get("geometry")),
            "meta": _safe_dict(overlay.get("meta")),
        }
    return {
        "id": getattr(overlay, "id", None),
        "status": str(getattr(overlay, "status", "unknown") or "unknown").lower(),
        "geometry": _safe_dict(getattr(overlay, "geometry", None)),
        "meta": _safe_dict(getattr(overlay, "meta", None)),
    }


def extract_findings_from_overlays(
    overlays: Sequence[Union[Dict[str, Any], "DrawingOverlay"]],
) -> List[Dict[str, Any]]:
    """
    Derive lightweight finding summaries from overlay metadata.
    Returns list of dicts with title/description/severity/location.
    """
    findings: List[Dict[str, Any]] = []
    for overlay in overlays:
        payload = _coerce_overlay_payload(overlay)
        meta = payload["meta"]
        geometry = payload["geometry"]
        status = payload["status"]

        issue_candidates: List[Dict[str, Any]] = []
        for key in _ISSUE_LIST_KEYS:
            value = meta.get(key)
            if isinstance(value, list):
                issue_candidates.extend([item for item in value if isinstance(item, dict)])
        if not issue_candidates:
            issue_candidates = [meta]

        for candidate in issue_candidates:
            title = _pick_first_str(candidate, _TITLE_KEYS) or _pick_first_str(meta, _TITLE_KEYS)
            description = _pick_first_str(candidate, _DESCRIPTION_KEYS) or _pick_first_str(
                meta, _DESCRIPTION_KEYS
            )
            severity_value = candidate.get("severity") or _pick_first_str(candidate, _SEVERITY_KEYS)
            if severity_value is None:
                for key in _SEVERITY_KEYS:
                    if key in meta:
                        severity_value = meta[key]
                        break
            severity = _normalize_severity(severity_value, status)
            location = _build_location(candidate, geometry)
            if not location:
                location = _build_location(meta, geometry)

            if not any([title, description, location]):
                continue

            findings.append(
                {
                    "overlay_id": payload.get("id"),
                    "status": status,
                    "title": title or f"Overlay issue ({status})",
                    "description": description,
                    "severity": severity,
                    "location": location or ({"geometry": geometry} if geometry else {}),
                }
            )
    return findings


def _normalize_overlay(overlay: Any) -> Dict[str, Any]:
    """
    Normalize a DrawingOverlay ORM instance into a portable dict shape
    for the writeback layer. Keeps only id, status, geometry, meta.
    """
    return {
        "id": int(getattr(overlay, "id", 0)),
        "status": str(getattr(overlay, "status", "unknown") or "unknown"),
        "geometry": _safe_dict(getattr(overlay, "geometry", None)),
        "meta": _safe_dict(getattr(overlay, "meta", None)),
    }


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
    """Portable overlay shape for the writeback layer (id, status, geometry, meta)."""
    id: int
    status: str
    geometry: Dict[str, Any]
    meta: Dict[str, Any] = Field(default_factory=dict)


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


def gather_writeback_raw_records(
    db: Session,
    project_id: int,
    inspection_run_id: int,
) -> Dict[str, Any]:
    """
    Load and return the raw records needed for writeback.

    Returns a dict with keys:
        - run: InspectionRun
        - project: Project
        - master_drawing: Drawing
        - evidence: EvidenceRecord | None
        - inspection_result/result: latest InspectionResult | None
        - overlays: list of normalized overlay dicts (id, status, geometry, meta)
        - raw_overlays: ORM instances (pre-normalization)
        - findings: List[Finding] associated with the run

    Raises ValueError if the inspection run is not found.
    """
    storage = StorageService(db)
    details = storage.get_inspection_run_with_details(project_id, inspection_run_id)
    if details is None:
        raise ValueError("Inspection run not found")

    run = details["run"]
    project = details["project"]
    master_drawing = details["master_drawing"]
    evidence = details["evidence"]
    inspection_result = details["inspection_result"]
    overlays = details["overlays"]
    findings = details["findings"]

    normalized_overlays = [_normalize_overlay(o) for o in overlays]

    return {
        "run": run,
        "project": project,
        "master_drawing": master_drawing,
        "evidence": evidence,
        "inspection_result": inspection_result,
        "result": inspection_result,
        "overlays": normalized_overlays,
        "raw_overlays": overlays,
        "findings": findings,
    }


def build_writeback_contract(
    db: Session,
    project_id: int,
    inspection_run_id: int,
) -> Dict[str, Any]:
    """
    Assemble the normalized writeback contract for a given inspection_run.

    Raises ValueError when required records are missing (project, run, drawing).
    """
    raw = gather_writeback_raw_records(db, project_id, inspection_run_id)
    run = raw["run"]
    result = raw.get("inspection_result") or raw.get("result")
    overlays = raw["overlays"]

    storage = StorageService(db)
    project = raw.get("project")
    if project is None:
        raise ValueError("Project not found")

    project_procore_id = getattr(project, "procore_project_id", None)
    if not project_procore_id:
        raise ValueError("Project has no procore_project_id; sync project from Procore first")

    master_drawing = raw.get("master_drawing")
    if master_drawing is None:
        raise ValueError("Master drawing not found")

    evidence = raw.get("evidence")

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

    overlay_contexts: List[OverlayContext] = [
        OverlayContext(**o) for o in overlays
    ]
    overlay_findings = extract_findings_from_overlays(overlays)

    findings_lookup = {
        int(getattr(f, "id", 0)): f
        for f in (raw.get("findings") or [])
        if getattr(f, "id", None) is not None
    }

    finding_ctx: Optional[FindingContext] = None
    finding_id: Optional[int] = None
    for overlay in overlay_contexts:
        meta = overlay.meta
        candidate = meta.get("finding_id")
        if isinstance(candidate, int):
            finding_id = candidate
            break

    if finding_id is not None:
        finding = findings_lookup.get(finding_id)
        if finding is None:
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
    if overlay_findings:
        meta["overlay_findings"] = overlay_findings
    if pages:
        meta["pages"] = sorted(pages)
    if evidence_ctx is not None:
        meta["evidence_type"] = evidence_ctx.type

    contract = WritebackContract(
        project=project_ctx,
        inspection_run=inspection_run_ctx,
        inspection_result=inspection_result_ctx,
        master_drawing=master_drawing_ctx,
        evidence=evidence_ctx,
        overlays=overlay_contexts,
        finding=finding_ctx,
        meta=meta,
    )
    return contract.model_dump(mode="python")


def build_inspection_item_contract(contract: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Build normalized checklist items from the writeback contract.

    Derives items from:
      - meta.overlay_findings: rich items (title, description, severity, location, status)
      - overlays: overlays that did not produce overlay_findings get minimal items
      - inspection_result: one summary item (outcome + notes)

    Returns a list of dicts with: overlay_id?, status, title, description, severity, location, source.
    """
    items: List[Dict[str, Any]] = []
    overlays = contract.get("overlays") or []
    overlay_findings = (contract.get("meta") or {}).get("overlay_findings") or []
    inspection_result = contract.get("inspection_result") or {}

    overlay_ids_with_findings: Set[int] = set()
    for f in overlay_findings:
        oid = f.get("overlay_id")
        if oid is not None and oid != 0:
            overlay_ids_with_findings.add(int(oid))
        items.append({
            "overlay_id": oid,
            "status": str(f.get("status", "unknown") or "unknown"),
            "title": str(f.get("title", "") or ""),
            "description": str(f.get("description", "") or ""),
            "severity": str(f.get("severity", "") or "medium"),
            "location": _safe_dict(f.get("location")),
            "source": "overlay_finding",
        })

    for ov in overlays:
        oid = ov.get("id") if isinstance(ov, dict) else getattr(ov, "id", None)
        if oid is None:
            continue
        oid_int = int(oid)
        if oid_int in overlay_ids_with_findings:
            continue
        status = "unknown"
        if isinstance(ov, dict):
            status = str(ov.get("status", "unknown") or "unknown")
        else:
            status = str(getattr(ov, "status", "unknown") or "unknown")
        geometry = _safe_dict(ov.get("geometry") if isinstance(ov, dict) else getattr(ov, "geometry", None))
        items.append({
            "overlay_id": oid_int,
            "status": status,
            "title": f"Overlay {oid_int}",
            "description": "",
            "severity": "high" if status == "fail" else "medium" if status == "unknown" else "low",
            "location": {"geometry": geometry} if geometry else {},
            "source": "overlay",
        })

    outcome = str(inspection_result.get("outcome", "unknown") or "unknown")
    notes = str(inspection_result.get("notes", "") or "").strip()
    if outcome or notes:
        items.append({
            "overlay_id": None,
            "status": outcome,
            "title": "Inspection result",
            "description": notes or f"Overall outcome: {outcome}",
            "severity": "high" if outcome == "fail" else "medium" if outcome == "mixed" else "low",
            "location": {},
            "source": "inspection_result",
        })

    return items


__all__ = [
    "WritebackContract",
    "build_writeback_contract",
    "build_inspection_item_contract",
    "gather_writeback_raw_records",
    "extract_findings_from_overlays",
    "CONTRACT_VERSION",
]
