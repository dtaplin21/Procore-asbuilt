"""
Procore writeback service.

Builds inspection payloads from inspection runs and pushes to Procore.
Supports dry_run (return payload only) and commit (call Procore API).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from services.procore_writeback_contract import build_writeback_contract

logger = logging.getLogger(__name__)

# Optional mapping: our inspection_type -> Procore inspection_type_id (if required).
# Set via env or config; if unset, we pass inspection_type as string.
INSPECTION_TYPE_TO_TEMPLATE_ID: Dict[str, int] = {}


def build_inspection_payload(
    db: Session,
    project_id: int,
    inspection_run_id: int,
) -> tuple[Dict[str, Any], Optional[str]]:
    """
    Build Procore inspection payload from inspection_run, inspection_result, overlays.

    Returns (payload, error_message). If error_message is set, payload may be partial.
    Uses Project.procore_project_id for Procore API calls.
    """
    try:
        contract = build_writeback_contract(db, project_id, inspection_run_id)
    except ValueError as exc:
        return {}, str(exc)

    # Use completed_at or created_at for date
    run_ctx = contract.inspection_run
    dt = (
        run_ctx.completed_at
        or run_ctx.started_at
        or run_ctx.created_at
        or datetime.now(timezone.utc)
    )
    if dt is None:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    date_str = dt.strftime("%Y-%m-%d")
    datetime_str = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    hour = dt.hour
    minute = dt.minute

    inspection_result = contract.inspection_result
    inspection_type = (run_ctx.inspection_type or "").strip() or "Inspection"
    outcome = (
        inspection_result.outcome if inspection_result is not None else "unknown"
    )
    notes = (inspection_result.notes if inspection_result is not None else "") or ""

    comments = f"Outcome: {outcome}. {notes}".strip()

    # Procore Inspection Logs API shape (inspection_log wrapper).
    # Inspections product may use different schema; adjust if API returns 400.
    inspection_log: Dict[str, Any] = {
        "date": date_str,
        "datetime": datetime_str,
        "inspection_type": inspection_type,
        "comments": comments or "(No notes)",
        "start_hour": hour,
        "start_minute": minute,
        "end_hour": hour,
        "end_minute": minute,
        "inspecting_entity": "QC/QA",
        "inspector_name": "AI Platform",
    }

    # Optional: map to Procore template ID if configured
    template_id = INSPECTION_TYPE_TO_TEMPLATE_ID.get(
        (inspection_type or "").lower().strip()
    )
    if template_id is not None:
        inspection_log["inspection_type_id"] = template_id

    payload: Dict[str, Any] = {
        "inspection_log": inspection_log,
        "_meta": {
            "project_id": project_id,
            "inspection_run_id": inspection_run_id,
            "procore_project_id": contract.project.procore_project_id,
            "contract_version": contract.version,
            "run_status": run_ctx.status,
            "has_finding": contract.finding is not None,
            "outcome": outcome,
            "contract": contract.model_dump(mode="json"),
        },
    }

    return payload, None


def build_writeback_payload_for_api(
    db: Session,
    project_id: int,
    inspection_run_id: int,
) -> Dict[str, Any]:
    """
    Build the JSON body to send to Procore create_inspection.
    Strips _meta before sending.
    """
    payload, err = build_inspection_payload(db, project_id, inspection_run_id)
    if err:
        raise ValueError(err)

    # Remove internal _meta before sending to Procore
    out = {k: v for k, v in payload.items() if k != "_meta"}
    return out
