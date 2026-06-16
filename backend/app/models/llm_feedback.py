from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from backend.app.database import Base


class LLMFeedback(Base):
    """Feedback utilisateur sur une réponse générée par l'agent LLM."""

    __tablename__ = "llm_feedbacks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    question = Column(Text, nullable=False)
    previous_answer = Column(Text, nullable=True)
    regenerated_answer = Column(Text, nullable=True)
    vote = Column(Integer, nullable=False, default=-1)  # 1 = utile, -1 = à régénérer
    reason = Column(String(1000), nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    user = relationship("User")
