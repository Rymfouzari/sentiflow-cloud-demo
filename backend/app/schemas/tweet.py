from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class TweetResponse(BaseModel):
    id: int
    twitter_id: str
    text: str
    author_username: Optional[str] = None
    sentiment: Optional[str] = None
    sentiment_scores: Optional[dict] = None
    confidence: Optional[float] = None
    tweet_created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SentimentAnalysis(BaseModel):
    target_id: int
    target_name: str
    period: str
    total_tweets: int
    sentiment_distribution: dict  # {"joie": 0.3, "colere": 0.2, ...}
    average_confidence: float = 0.0
