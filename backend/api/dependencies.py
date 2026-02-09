from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db

def get_storage_service(db: Session = Depends(get_db)):
    """Dependency to get storage service"""
    from services.storage import StorageService
    return StorageService(db)

