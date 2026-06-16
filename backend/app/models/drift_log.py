from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, Boolean
from datetime import datetime
from backend.app.database import Base


class DriftLog(Base):
    """Detection de data drift - compare les distributions de sentiments"""
    __tablename__ = "drift_logs"

    id = Column(Integer, primary_key=True, index=True)
    target_id = Column(Integer, nullable=True)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    reference_distribution = Column(JSON, nullable=False)  # distribution de reference
    current_distribution = Column(JSON, nullable=False)  # distribution actuelle
    drift_score = Column(Float, nullable=False)  # score de drift (0=identique, 1=totalement different)
    is_drift_detected = Column(Boolean, default=False)
    drift_threshold = Column(Float, default=0.15)
    details = Column(JSON, nullable=True)  # details par sentiment
    created_at = Column(DateTime, default=datetime.utcnow)
