from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from backend.app.database import get_db
from backend.app.models.user import User
from backend.app.services.auth import get_current_user
from backend.app.services.monitoring import get_monitoring_stats, detect_drift

router = APIRouter(prefix="/monitoring", tags=["Monitoring"])


@router.get("/stats")
def monitoring_stats(
    hours: int = Query(default=24, le=168),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Statistiques de monitoring des predictions ML"""
    return get_monitoring_stats(db, hours)


@router.get("/drift")
def check_drift(
    target_id: Optional[int] = None,
    reference_days: int = Query(default=14, le=60),
    current_days: int = Query(default=7, le=30),
    threshold: float = Query(default=0.15),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Detecte le data drift sur les sentiments"""
    return detect_drift(db, target_id, reference_days, current_days, threshold)
