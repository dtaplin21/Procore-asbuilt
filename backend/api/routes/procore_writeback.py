"""
Procore writeback routes.

Endpoints for pushing inspection runs, findings, etc. to Procore.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from api.dependencies import get_db
from models.schemas import ProcoreWritebackRequest, ProcoreWritebackResponse
from models.models import InspectionRun
from services.procore_writeback_contract import build_writeback_contract
from services.procore_writeback import (
    translate_contract_to_procore_payload,
    build_inspection_item_contract,
    translate_contract_to_procore_inspection_item_payload,
)
from services.procore_client import ProcoreAPIClient
from services.procore_connection_store import get_active_connection
from errors import AppError, ProcoreNotConnected


def _extract_procore_inspection_id(created: dict) -> Optional[str]:
    """Extract Procore inspection ID from create_inspection response for persistence."""
    if not created or not isinstance(created, dict):
        return None
    pid = created.get("id")
    if pid is not None:
        return str(pid)
    inner = created.get("inspection_log") or created.get("inspection")
    if isinstance(inner, dict) and inner.get("id") is not None:
        return str(inner["id"])
    return None


router = APIRouter(prefix="/api/projects", tags=["procore-writeback"])


@router.post(
    "/{project_id}/procore/writeback",
    response_model=ProcoreWritebackResponse,
)
async def procore_writeback(
    project_id: int,
    body: ProcoreWritebackRequest,
    user_id: str = Query(..., description="Procore user ID for auth"),
    db: Session = Depends(get_db),
) -> ProcoreWritebackResponse:
    """
    Write inspection run to Procore.

    Request body:
        - inspection_run_id (int): ID of the inspection run to write back
        - mode: "dry_run" | "commit"

    - **dry_run**: Builds normalized contract, translates to Procore payload(s), returns payload only.
      No Procore API calls. Lets you inspect what would be sent safely.
    - **commit**: Builds payload, translates, calls Procore, returns payload sent + Procore response + success status.
    """
    if body.mode not in ("dry_run", "commit"):
        raise HTTPException(
            status_code=400,
            detail="mode must be 'dry_run' or 'commit'",
        )

    run = (
        db.query(InspectionRun)
        .filter(
            InspectionRun.project_id == project_id,
            InspectionRun.id == body.inspection_run_id,
        )
        .first()
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Inspection run not found")
    status = str(run.status) if run.status is not None else ""
    if status != "complete":
        raise HTTPException(
            status_code=400,
            detail=f"Run is incomplete (status: {status}); only completed runs can be written back",
        )
    existing_procore_id = getattr(run, "procore_inspection_id", None)
    if existing_procore_id:
        raise HTTPException(
            status_code=409,
            detail=f"Inspection run already written to Procore (procore_inspection_id: {existing_procore_id})",
        )

    try:
        contract = build_writeback_contract(db, project_id, body.inspection_run_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    procore_payload = translate_contract_to_procore_payload(contract)

    if body.mode == "dry_run":
        return ProcoreWritebackResponse(
            mode="dry_run",
            payload=procore_payload,
        )

    if get_active_connection(db, user_id) is None:
        raise ProcoreNotConnected(details={"user_id": user_id})

    procore_project_id = contract.get("project", {}).get("procore_project_id", "")
    if not procore_project_id:
        raise HTTPException(
            status_code=400,
            detail="Project has no procore_project_id; sync project from Procore first",
        )

    items_contract = build_inspection_item_contract(db, project_id, body.inspection_run_id)
    item_payloads = [
        translate_contract_to_procore_inspection_item_payload(item)
        for item in items_contract
    ]

    created = None
    try:
        async with ProcoreAPIClient(db, user_id) as client:
            created = await client.create_inspection(
                project_id=str(procore_project_id),
                inspection_data=procore_payload,
            )

            procore_id = _extract_procore_inspection_id(created)
            if procore_id:
                db.query(InspectionRun).filter(
                    InspectionRun.project_id == project_id,
                    InspectionRun.id == body.inspection_run_id,
                ).update({"procore_inspection_id": procore_id})
                db.commit()

                for item_payload in item_payloads:
                    await client.create_inspection_item(
                        project_id=str(procore_project_id),
                        inspection_id=procore_id,
                        payload=item_payload,
                    )

        return ProcoreWritebackResponse(
            mode="commit",
            payload=procore_payload,
            committed=True,
            procore_response=created,
        )
    except AppError:
        raise
    except Exception as e:
        return ProcoreWritebackResponse(
            mode="commit",
            payload=procore_payload,
            committed=False,
            procore_response=created,
            message=str(e),
        )
