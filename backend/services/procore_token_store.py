"""
In-memory Procore token store.

We removed the SQLAlchemy table models and schemas. Until the new data model is defined,
we keep Procore OAuth tokens in-memory so the backend can still run end-to-end.

Important:
- This is NOT durable storage (tokens are lost on restart).
- Replace this with a real persistence layer once the new tables are designed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from threading import RLock
from typing import Dict, Optional


@dataclass
class ProcoreTokenRecord:
    access_token: str
    refresh_token: str
    expires_at: datetime
    token_type: str = "Bearer"
    scope: Optional[str] = None
    company_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


_lock = RLock()
_tokens: Dict[str, ProcoreTokenRecord] = {}


def get_token(user_id: str) -> Optional[ProcoreTokenRecord]:
    with _lock:
        return _tokens.get(user_id)


def upsert_token(user_id: str, token: ProcoreTokenRecord) -> ProcoreTokenRecord:
    with _lock:
        token.updated_at = datetime.utcnow()
        _tokens[user_id] = token
        return token


def delete_token(user_id: str) -> bool:
    with _lock:
        return _tokens.pop(user_id, None) is not None


def move_token(old_user_id: str, new_user_id: str) -> bool:
    """
    Re-key a token from one user_id to another (e.g., temp session id -> Procore user id).
    """
    with _lock:
        token = _tokens.pop(old_user_id, None)
        if token is None:
            return False
        token.updated_at = datetime.utcnow()
        _tokens[new_user_id] = token
        return True

