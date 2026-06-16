from sqlalchemy import Column, Integer, String, DateTime, JSON
from datetime import datetime
from backend.app.database import Base


class QuestionLog(Base):
    """Log de toutes les questions posées par les utilisateurs — pour ré-entraînement."""
    __tablename__ = "question_logs"

    id = Column(Integer, primary_key=True, index=True)
    question = Column(String(1000), nullable=False)
    intent_detected = Column(String(50), nullable=True)
    mode_used = Column(String(20), nullable=True)  # rag, agent, database
    targets_detected = Column(JSON, nullable=True)
    response_time_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
