from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class AlertCreate(BaseModel):
    target_id: int
    name: str
    sentiment: str  # "joie", "colere", "tristesse", "peur", "surprise", "amour"
    threshold: float  # 0.0 à 1.0
    is_above: bool = True  # True = alerte si > seuil


class AlertResponse(BaseModel):
    id: int
    target_id: int
    name: str
    sentiment: str
    threshold: float
    is_above: bool
    is_active: bool
    last_triggered: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True
