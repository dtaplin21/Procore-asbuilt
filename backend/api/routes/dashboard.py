from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from services.storage import StorageService
from models.schemas import DashboardStats

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(db: Session = Depends(get_db)):
    storage = StorageService(db)
    stats = storage.get_dashboard_stats()
    return stats

