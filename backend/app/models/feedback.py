from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.app.database import Base


class Feedback(Base):
    """Corrections utilisateur sur les prédictions - table Feedbacks du MCD"""
    __tablename__ = "feedbacks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    tweet_id = Column(Integer, ForeignKey("tweets.id"), nullable=False)
    target_type = Column(String(20), nullable=True)  # "hashtag", "account"
    target_id = Column(Integer, ForeignKey("targets.id"), nullable=True)
    vote = Column(Integer, nullable=False)  # 1 = correct, -1 = incorrect
    corrected_label = Column(String(20), nullable=True)  # Le bon sentiment selon l'utilisateur
    reason = Column(String(500), nullable=True)  # Raison de la correction
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relations
    user = relationship("User", back_populates="feedbacks")
    tweet = relationship("Tweet", back_populates="feedbacks")
