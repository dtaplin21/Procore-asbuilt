from __future__ import annotations

import logging
from typing import Iterable

logger = logging.getLogger(__name__)


def log_job_status_transition(
    *,
    project_id: int | None,
    job_id: int | None,
    status: str | None,
    previous_status: str | None = None,
) -> None:
    logger.info(
        "job_status_transition",
        extra={
            "project_id": project_id,
            "job_id": job_id,
            "status": status,
            "previous_status": previous_status,
        },
    )


def log_finding_created(
    *,
    project_id: int | None,
    finding_id: int | None,
    evidence_ids: Iterable[int] | None = None,
    finding_type: str | None = None,
    severity: str | None = None,
) -> None:
    logger.info(
        "finding_created",
        extra={
            "project_id": project_id,
            "finding_id": finding_id,
            "evidence_ids": list(evidence_ids or []),
            "finding_type": finding_type,
            "severity": severity,
        },
    )
