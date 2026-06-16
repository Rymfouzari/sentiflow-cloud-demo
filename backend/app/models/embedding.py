from sqlalchemy import Column, Integer, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from datetime import datetime
from backend.app.database import Base


class TweetEmbedding(Base):
    """Embeddings vectoriels des tweets pour le RAG"""
    __tablename__ = "tweet_embeddings"

    id = Column(Integer, primary_key=True, index=True)
    tweet_id = Column(Integer, ForeignKey("tweets.id", ondelete="CASCADE"), unique=True, nullable=False)
    embedding = Column(Vector(384), nullable=False)  # all-MiniLM-L6-v2 = 384 dims
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relations
    tweet = relationship("Tweet", backref="embedding_rel")
