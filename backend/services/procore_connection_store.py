# backend/services/procore_connection_store.py

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from models.models import ProcoreConnection


def get_active_connection(db: Session, procore_user_id: str) -> Optional[ProcoreConnection]:
    return (
        db.query(ProcoreConnection)
        .filter(
            ProcoreConnection.procore_user_id == str(procore_user_id),
            ProcoreConnection.is_active.is_(True),
            ProcoreConnection.revoked_at.is_(None),
        )
        .order_by(ProcoreConnection.updated_at.desc())
        .first()
    )


def get_connection(db: Session, company_id: int, procore_user_id: str) -> Optional[ProcoreConnection]:
    return (
        db.query(ProcoreConnection)
        .filter(
            ProcoreConnection.company_id == int(company_id),
            ProcoreConnection.procore_user_id == str(procore_user_id),
        )
        .first()
    )


def set_active_company(db: Session, procore_user_id: str, company_id: int) -> None:
    """
    No commit here. Caller commits once per high-level operation.
    """
    procore_user_id = str(procore_user_id)
    company_id = int(company_id)
    now = datetime.now(timezone.utc)

    # deactivate all
    (
        db.query(ProcoreConnection)
        .filter(ProcoreConnection.procore_user_id == procore_user_id)
        # NOTE: bulk updates do not trigger SQLAlchemy onupdate= handlers
        .update(
            {ProcoreConnection.is_active: False, ProcoreConnection.updated_at: now},
            synchronize_session=False,
        )
    )

    # activate selected
    (
        db.query(ProcoreConnection)
        .filter(
            ProcoreConnection.procore_user_id == procore_user_id,
            ProcoreConnection.company_id == company_id,
            ProcoreConnection.revoked_at.is_(None),
        )
        .update(
            {ProcoreConnection.is_active: True, ProcoreConnection.updated_at: now},
            synchronize_session=False,
        )
    )


def upsert_connection(
    db: Session,
    company_id: int,
    procore_user_id: str,
    access_token: str,
    refresh_token: str,
    token_expires_at,  # datetime
    token_type: str = "Bearer",
    scope: Optional[str] = None,
    make_active: bool = True,
) -> ProcoreConnection:
    """
    Insert or update the row for (company_id, procore_user_id).
    Commits exactly once here.
    """
    company_id = int(company_id)
    procore_user_id = str(procore_user_id)

    conn = get_connection(db, company_id, procore_user_id)

    if conn is None:
        conn = ProcoreConnection(
            company_id=company_id,
            procore_user_id=procore_user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=token_expires_at,
            token_type=token_type or "Bearer",
            scope=scope,
            revoked_at=None,
            is_active=bool(make_active),
        )
        db.add(conn)
        db.flush()
    else:
        conn.access_token = access_token
        conn.refresh_token = refresh_token
        conn.token_expires_at = token_expires_at
        conn.token_type = token_type or conn.token_type or "Bearer"
        if scope is not None:
            conn.scope = scope
        conn.revoked_at = None
        if make_active:
            conn.is_active = True
        db.add(conn)

    if make_active:
        set_active_company(db, procore_user_id, company_id)

    db.commit()
    db.refresh(conn)
    return conn


def delete_connection(db: Session, procore_user_id: str, company_id: int) -> None:
    procore_user_id = str(procore_user_id)
    company_id = int(company_id)

    conn = get_connection(db, company_id, procore_user_id)
    if conn is None:
        return

    was_active = bool(conn.is_active)
    db.delete(conn)
    db.commit()

    if was_active:
        replacement = (
            db.query(ProcoreConnection)
            .filter(
                ProcoreConnection.procore_user_id == procore_user_id,
                ProcoreConnection.revoked_at.is_(None),
            )
            .order_by(ProcoreConnection.updated_at.desc())
            .first()
        )
        if replacement:
            set_active_company(db, procore_user_id, replacement.company_id)
            db.commit()


def revoke_connection(db: Session, procore_user_id: str, company_id: int) -> None:
    """
    Optional: audit-friendly disconnect.
    """
    conn = get_connection(db, int(company_id), str(procore_user_id))
    if conn is None:
        return
    conn.revoked_at = datetime.now(timezone.utc)
    conn.is_active = False
    db.add(conn)
    db.commit()