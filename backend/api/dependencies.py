from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from database import get_db


def get_idempotency_key(idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key")) -> str:
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
    return idempotency_key


def get_storage_service(db: Session = Depends(get_db)):
    """Dependency to get storage service"""
    from services.storage import StorageService
    return StorageService(db)

