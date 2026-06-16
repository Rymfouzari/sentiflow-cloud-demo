from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.app.database import Base


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    target_id = Column(Integer, ForeignKey("targets.id"), nullable=False)
    name = Column(String(255), nullable=False)
    sentiment = Column(String(20), nullable=False)  # "joie", "colere", etc.
    threshold = Column(Float, nullable=False)  # Seuil (ex: 0.6 = 60%)
    is_above = Column(Boolean, default=True)  # True = alerte si > seuil
    is_active = Column(Boolean, default=True)
    last_triggered = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relations
    user = relationship("User", back_populates="alerts")
    target = relationship("Target", back_populates="alerts")
