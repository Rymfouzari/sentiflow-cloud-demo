from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from backend.app.database import Base


class TargetType(str, enum.Enum):
    HASHTAG = "hashtag"
    ACCOUNT = "account"


class Target(Base):
    __tablename__ = "targets"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(255), nullable=False)  # ex: "#IA" ou "@elonmusk"
    target_type = Column(Enum(TargetType), nullable=False)
    query = Column(String(500), nullable=False)  # Requête Twitter
    last_tweet_id = Column(String(50), nullable=True)  # Pour pagination
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relations
    user = relationship("User", back_populates="targets")
    tweets = relationship("Tweet", back_populates="target")
    alerts = relationship("Alert", back_populates="target")
    sentiment_aggregates = relationship("SentimentAggregate", back_populates="target")
    dashboards = relationship("Dashboard", back_populates="target")
