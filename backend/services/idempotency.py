import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, cast

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.models import IdempotencyKey

DEFAULT_TTL_MINUTES = 60


def stable_request_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def begin_idempotent_operation(
    db: Session,
    *,
    scope: str,
    idempotency_key: str,
    request_payload: dict[str, Any],
    ttl_minutes: int = DEFAULT_TTL_MINUTES,
) -> tuple[IdempotencyKey, bool]:
    req_hash = stable_request_hash(request_payload)
    now = datetime.now(timezone.utc)
    lock_until = now + timedelta(minutes=ttl_minutes)

    existing = (
        db.query(IdempotencyKey)
        .filter(
            IdempotencyKey.scope == scope,
            IdempotencyKey.idempotency_key == idempotency_key,
        )
        .first()
    )

    if existing is not None:
        if cast(str, existing.request_hash) != req_hash:
            raise ValueError("Idempotency-Key was reused with a different request payload")
        return existing, False

    row = IdempotencyKey(
        scope=scope,
        idempotency_key=idempotency_key,
        request_hash=req_hash,
        status="in_progress",
        locked_until=lock_until,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        row = (
            db.query(IdempotencyKey)
            .filter(
                IdempotencyKey.scope == scope,
                IdempotencyKey.idempotency_key == idempotency_key,
            )
            .first()
        )
        if row is None:
            raise ValueError("Idempotency race: row missing after IntegrityError")
        return row, False

    db.refresh(row)
    return row, True


def finish_idempotent_operation(
    db: Session,
    *,
    row_id: int,
    response_payload: dict[str, Any],
    resource_reference: Optional[dict[str, Any]] = None,
) -> IdempotencyKey:
    row = db.query(IdempotencyKey).filter(IdempotencyKey.id == row_id).first()
    if row is None:
        raise ValueError(f"Idempotency row not found: {row_id}")
    row.status = "completed"  # type: ignore[assignment]
    row.response_payload = response_payload  # type: ignore[assignment]
    row.resource_reference = resource_reference  # type: ignore[assignment]
    row.locked_until = None  # type: ignore[assignment]
    db.commit()
    db.refresh(row)
    return row


def fail_idempotent_operation(
    db: Session,
    *,
    row_id: int,
    response_payload: dict[str, Any],
) -> IdempotencyKey:
    row = db.query(IdempotencyKey).filter(IdempotencyKey.id == row_id).first()
    if row is None:
        raise ValueError(f"Idempotency row not found: {row_id}")
    row.status = "failed"  # type: ignore[assignment]
    row.response_payload = response_payload  # type: ignore[assignment]
    row.locked_until = None  # type: ignore[assignment]
    db.commit()
    db.refresh(row)
    return row
