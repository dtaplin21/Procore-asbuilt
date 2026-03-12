from __future__ import annotations

from typing import Any, Dict, List, cast
from sqlalchemy.orm import Session

from services.procore_client import ProcoreAPIClient
from services.storage import StorageService
from models.models import EvidenceRecord, Project


def _normalize_rfi_to_evidence(rfi: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a Procore RFI payload into the normalized EvidenceRecord shape.
    Adjust field names as needed once you inspect your actual Procore responses.
    """

    source_id = str(rfi.get("id") or "")
    number = rfi.get("number")
    subject = rfi.get("subject") or rfi.get("title") or f"RFI {source_id}"
    status = str(rfi.get("status") or "unknown")

    question = rfi.get("question") or ""
    answer = rfi.get("answer") or ""
    description_parts = [part for part in [question, answer] if part]
    text_content = "\n\n".join(description_parts) if description_parts else None

    dates = {
        "created_at": rfi.get("created_at"),
        "updated_at": rfi.get("updated_at"),
        "due_date": rfi.get("due_date"),
        "closed_at": rfi.get("closed_at"),
    }

    attachments_json = []
    for attachment in rfi.get("attachments", []) or []:
        attachments_json.append(
            {
                "id": attachment.get("id"),
                "name": attachment.get("name"),
                "url": attachment.get("url"),
                "content_type": attachment.get("content_type"),
            }
        )

    cross_refs_json = []
    if number is not None:
        cross_refs_json.append({"kind": "rfi_number", "value": number})

    return {
        "source_id": source_id,
        "title": subject,
        "status": status,
        "text_content": text_content,
        "dates": dates,
        "attachments_json": attachments_json,
        "cross_refs_json": cross_refs_json,
    }


async def ingest_rfis_for_project(
    db: Session,
    *,
    user_id: str,
    project: Project,
) -> List[EvidenceRecord]:
    """
    Pull RFIs from Procore for one project and normalize them into EvidenceRecord(type='rfi').
    """
    storage = StorageService(db)

    procore_project_id = getattr(project, "procore_project_id", None)
    if not procore_project_id:
        raise ValueError("Project is missing procore_project_id")

    async with ProcoreAPIClient(db, user_id) as client:
        rfis = await client.get_rfis(project_id=str(procore_project_id))

    records: List[EvidenceRecord] = []

    for rfi in rfis:
        normalized = _normalize_rfi_to_evidence(cast(Dict[str, Any], rfi))

        record = storage.upsert_rfi_evidence_record(
            project_id=cast(int, project.id),
            source_id=normalized["source_id"],
            title=normalized["title"],
            status=normalized["status"],
            text_content=normalized["text_content"],
            dates=normalized["dates"],
            attachments_json=normalized["attachments_json"],
            cross_refs_json=normalized["cross_refs_json"],
        )

        records.append(record)

    return records
