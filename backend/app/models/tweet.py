from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.app.database import Base

# Liste des sentiments valides (en minuscules)
VALID_SENTIMENTS = ["joie", "colere", "tristesse", "peur", "surprise", "amour", "incertain"]


class Tweet(Base):
    __tablename__ = "tweets"

    id = Column(Integer, primary_key=True, index=True)
    twitter_id = Column(String(50), unique=True, index=True, nullable=False)
    target_id = Column(Integer, ForeignKey("targets.id"), nullable=False)
    text = Column(String(1000), nullable=False)
    author_id = Column(String(50), nullable=True)
    author_username = Column(String(100), nullable=True)
    sentiment = Column(String(20), nullable=True)  # "joie", "colere", etc.
    sentiment_scores = Column(JSON, nullable=True)  # {"joie": 0.8, "colere": 0.1, ...}
    confidence = Column(Float, nullable=True)
    tweet_created_at = Column(DateTime, nullable=True)
    analyzed_at = Column(DateTime, default=datetime.utcnow)

    # Relations
    target = relationship("Target", back_populates="tweets")
    feedbacks = relationship("Feedback", back_populates="tweet")
