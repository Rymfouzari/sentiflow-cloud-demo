from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.app.database import Base


class SentimentAggregate(Base):
    """Agrégations pré-calculées pour le dashboard - table Sentiment_Aggregate du MCD"""
    __tablename__ = "sentiment_aggregates"

    id = Column(Integer, primary_key=True, index=True)
    target_id = Column(Integer, ForeignKey("targets.id"), nullable=False)
    bucket_start = Column(DateTime, nullable=False)  # Début de la période
    bucket_end = Column(DateTime, nullable=False)  # Fin de la période
    granularity = Column(String(20), nullable=False)  # "hour", "day", "week"
    total_posts = Column(Integer, default=0)
    counts_json = Column(JSON, nullable=True)  # {"joie": 45, "colere": 12, ...}
    scores_json = Column(JSON, nullable=True)  # {"joie": 0.38, "colere": 0.10, ...}
    model_version = Column(String(100), nullable=True)
    computed_at = Column(DateTime, default=datetime.utcnow)

    # Relations
    target = relationship("Target", back_populates="sentiment_aggregates")
