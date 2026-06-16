from pydantic import BaseModel
from datetime import datetime
from backend.app.models.target import TargetType


class TargetCreate(BaseModel):
    name: str  # ex: "#IA" ou "@elonmusk"
    target_type: TargetType


class TargetResponse(BaseModel):
    id: int
    name: str
    target_type: TargetType
    query: str
    created_at: datetime
    
    class Config:
        from_attributes = True
