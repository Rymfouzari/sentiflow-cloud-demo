from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.user import User
from backend.app.models.target import Target
from backend.app.models.tweet import Tweet
from backend.app.services.auth import get_current_user

router = APIRouter(prefix="/tweets", tags=["tweets"])


@router.get("/{target_id}")
def get_tweets(
    target_id: int,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target = (
        db.query(Target)
        .filter(Target.id == target_id, Target.user_id == current_user.id)
        .first()
    )

    if not target:
        raise HTTPException(status_code=404, detail="Cible introuvable")

    tweets = (
        db.query(Tweet)
        .filter(Tweet.target_id == target_id)
        .order_by(Tweet.tweet_created_at.desc().nullslast())
        .limit(limit)
        .all()
    )

    return tweets
