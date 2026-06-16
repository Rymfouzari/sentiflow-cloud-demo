"""
Export des tweets labellises pour re-entrainement sur nos propres donnees.
Permet de creer un dataset custom a partir des tweets analyses par le modele
+ valides/corriges par les utilisateurs via le feedback.
"""
import logging
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from datetime import datetime, timedelta

from backend.app.database import get_db
from backend.app.models.user import User
from backend.app.models.tweet import Tweet, VALID_SENTIMENTS
from backend.app.models.target import Target
from backend.app.models.feedback import Feedback
from backend.app.services.auth import get_current_user

logger = logging.getLogger("sentiflow.data_export")

router = APIRouter(prefix="/data", tags=["Data Export"])


@router.get("/export-training")
def export_training_data(
    min_confidence: float = Query(default=0.7, description="Confiance minimum pour inclure"),
    limit: int = Query(default=10000, le=50000),
    target_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Exporte les tweets labellises pour re-entrainement.
    
    Strategie:
    1. Tweets avec feedback utilisateur (labels corriges) -> priorite max
    2. Tweets avec haute confiance (>70%) -> labels fiables du modele
    3. Exclut les tweets "incertain" et confiance < seuil
    """
    # 1. Tweets avec feedback (labels corriges par humain)
    feedback_tweets = db.query(
        Tweet.text,
        Feedback.corrected_label.label("label"),
    ).join(
        Feedback, Feedback.tweet_id == Tweet.id
    ).filter(
        Feedback.corrected_label.isnot(None)
    ).all()

    human_labeled = [
        {"text": t.text, "label": t.label, "source": "human"}
        for t in feedback_tweets
    ]

    # 2. Tweets haute confiance (labels du modele)
    query = db.query(Tweet).filter(
        Tweet.sentiment.isnot(None),
        Tweet.sentiment != "incertain",
        Tweet.confidence >= min_confidence,
    )
    if target_id:
        query = query.filter(Tweet.target_id == target_id)

    model_tweets = query.order_by(Tweet.confidence.desc()).limit(limit).all()

    model_labeled = [
        {
            "text": t.text,
            "label": t.sentiment,
            "confidence": round(t.confidence, 3),
            "source": "model",
        }
        for t in model_tweets
    ]

    # Stats
    all_data = human_labeled + model_labeled
    label_counts = {}
    for d in all_data:
        label_counts[d["label"]] = label_counts.get(d["label"], 0) + 1

    logger.info(
        f"[DATA] Export: {len(human_labeled)} human + {len(model_labeled)} model = {len(all_data)} total"
    )

    return {
        "total": len(all_data),
        "human_labeled": len(human_labeled),
        "model_labeled": len(model_labeled),
        "min_confidence": min_confidence,
        "label_distribution": label_counts,
        "data": all_data,
    }


@router.get("/stats")
def data_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Statistiques sur les donnees disponibles pour le re-entrainement"""
    total = db.query(func.count(Tweet.id)).scalar()
    analyzed = db.query(func.count(Tweet.id)).filter(Tweet.sentiment.isnot(None)).scalar()
    high_conf = db.query(func.count(Tweet.id)).filter(Tweet.confidence >= 0.7).scalar()
    low_conf = db.query(func.count(Tweet.id)).filter(
        Tweet.confidence.isnot(None), Tweet.confidence < 0.5
    ).scalar()
    incertain = db.query(func.count(Tweet.id)).filter(Tweet.sentiment == "incertain").scalar()

    # Distribution par sentiment
    dist = db.query(
        Tweet.sentiment, func.count(Tweet.id)
    ).filter(
        Tweet.sentiment.isnot(None)
    ).group_by(Tweet.sentiment).all()

    # Confiance moyenne par sentiment
    conf_by_sent = db.query(
        Tweet.sentiment, func.avg(Tweet.confidence)
    ).filter(
        Tweet.sentiment.isnot(None)
    ).group_by(Tweet.sentiment).all()

    return {
        "total_tweets": total,
        "analyzed": analyzed,
        "not_analyzed": total - analyzed,
        "high_confidence": high_conf,
        "low_confidence": low_conf,
        "incertain": incertain,
        "usable_for_training": high_conf,
        "sentiment_distribution": {s: c for s, c in dist},
        "avg_confidence_by_sentiment": {s: round(float(c), 3) for s, c in conf_by_sent},
    }
