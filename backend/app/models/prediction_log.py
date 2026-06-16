from sqlalchemy import Column, Integer, String, Float, DateTime, JSON
from datetime import datetime
from backend.app.database import Base


class PredictionLog(Base):
    """Logs de chaque prediction du modele ML pour le monitoring"""
    __tablename__ = "prediction_logs"

    id = Column(Integer, primary_key=True, index=True)
    tweet_id = Column(Integer, nullable=True)
    text_preview = Column(String(200), nullable=True)
    predicted_sentiment = Column(String(20), nullable=False)
    confidence = Column(Float, nullable=False)
    scores = Column(JSON, nullable=True)
    inference_time_ms = Column(Float, nullable=True)
    model_version = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
