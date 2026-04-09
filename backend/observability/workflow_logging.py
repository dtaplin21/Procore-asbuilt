from __future__ import annotations

import logging
from typing import Any, Iterable

logger = logging.getLogger(__name__)


def normalize_evidence_ids(value: Iterable[Any] | None) -> list[int]:
    """
    Build a list of integer evidence ids for logging.

    Accepts:
    - ``None`` → ``[]``
    - iterable of ``int``
    - iterable of ORM objects (or any object) with a non-None ``.id`` (coerced with ``int()``)

    Do not pass raw ``EvidenceRecord`` lists to ``log_finding_created`` without going through
    this helper — model objects are normalized here so logs never store wrong types.
    """
    if value is None:
        return []
    out: list[int] = []
    for item in value:
        if item is None:
            continue
        if isinstance(item, int):
            out.append(item)
            continue
        rid = getattr(item, "id", None)
        if rid is not None:
            out.append(int(rid))
    return out


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
    evidence_ids: Iterable[Any] | None = None,
    finding_type: str | None = None,
    severity: str | None = None,
) -> None:
    """
    Log a persisted finding. ``evidence_ids`` may be ints or ORM rows; see ``normalize_evidence_ids``.
    Use ``finding_type=...`` for the log field (not ``type=``) so the JSON key stays stable.
    """
    logger.info(
        "finding_created",
        extra={
            "project_id": project_id,
            "finding_id": finding_id,
            "evidence_ids": normalize_evidence_ids(evidence_ids),
            "finding_type": finding_type,
            "severity": severity,
        },
    )
