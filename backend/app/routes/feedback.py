from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.feedback import Feedback
from backend.app.models.llm_feedback import LLMFeedback
from backend.app.models.target import Target
from backend.app.models.tweet import Tweet, VALID_SENTIMENTS
from backend.app.models.user import User
from backend.app.services.auth import get_current_user
from backend.app.services.llm_agent import AgentError, run_sentiflow_agent

router = APIRouter(prefix="/feedback", tags=["Feedback"])

DISPLAY_SENTIMENTS = [*VALID_SENTIMENTS, "neutre"]


class SentimentFeedbackRequest(BaseModel):
    tweet_id: int
    satisfied: bool = False
    corrected_label: str | None = Field(default=None, description="Emotion choisie par l'utilisateur au 2e refus")
    reason: str | None = Field(default=None, max_length=500)


class LLMFeedbackRequest(BaseModel):
    question: str = Field(..., min_length=3)
    previous_answer: str | None = None
    target_ids: list[int] = Field(default_factory=list)
    days: int = Field(default=7, ge=1, le=90)
    intent: str | None = None
    sentiment_filter: str | None = None
    reason: str | None = Field(default=None, max_length=1000)
    regenerate: bool = True


def _owned_tweet(db: Session, user_id: int, tweet_id: int) -> Tweet:
    tweet = (
        db.query(Tweet)
        .join(Target, Target.id == Tweet.target_id)
        .filter(Tweet.id == tweet_id, Target.user_id == user_id)
        .first()
    )
    if not tweet:
        raise HTTPException(status_code=404, detail="Tweet introuvable ou non autorisé")
    return tweet


def _safe_scores(scores: Any) -> dict[str, float]:
    if not isinstance(scores, dict):
        return {label: 0.0 for label in DISPLAY_SENTIMENTS}

    safe = {label: 0.0 for label in DISPLAY_SENTIMENTS}
    for key, value in scores.items():
        key = str(key)
        if key in safe:
            try:
                safe[key] = max(0.0, float(value or 0.0))
            except (TypeError, ValueError):
                safe[key] = 0.0
    return safe


def _rerank_with_zero_weight(scores: dict[str, float], forbidden_labels: set[str]) -> tuple[str, float, dict[str, float]]:
    """
    Feedback loop niveau 1 : on ne relance pas le modèle.
    On prend les scores déjà calculés et on met un poids à 0 sur l'émotion refusée.
    """
    reranked = dict(scores)
    for label in forbidden_labels:
        if label in reranked:
            reranked[label] = 0.0

    allowed = {k: v for k, v in reranked.items() if k not in forbidden_labels}
    if not allowed:
        fallback = next((label for label in DISPLAY_SENTIMENTS if label not in forbidden_labels), "neutre")
        reranked[fallback] = 1.0
        return fallback, 1.0, reranked

    dominant = max(allowed, key=allowed.get)
    confidence = float(allowed.get(dominant, 0.0) or 0.0)

    # Si tous les scores restants sont nuls, on renvoie neutre si possible, sinon le premier label autorisé.
    if confidence <= 0:
        dominant = "neutre" if "neutre" not in forbidden_labels else next(iter(allowed.keys()))
        confidence = 0.0
    return dominant, confidence, reranked


@router.post("/sentiment")
def submit_sentiment_feedback(
    payload: SentimentFeedbackRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tweet = _owned_tweet(db, current_user.id, payload.tweet_id)
    previous_label = tweet.sentiment or "neutre"
    previous_scores = _safe_scores(tweet.sentiment_scores)

    if payload.corrected_label and payload.corrected_label not in DISPLAY_SENTIMENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Emotion invalide. Valeurs possibles : {', '.join(DISPLAY_SENTIMENTS)}",
        )

    if payload.satisfied:
        feedback = Feedback(
            user_id=current_user.id,
            tweet_id=tweet.id,
            target_type=tweet.target.target_type.value if hasattr(tweet.target.target_type, "value") else str(tweet.target.target_type),
            target_id=tweet.target_id,
            vote=1,
            corrected_label=previous_label,
            reason=payload.reason,
            metadata_json={
                "action": "classification_accepted",
                "label": previous_label,
                "scores": previous_scores,
            },
        )
        db.add(feedback)
        db.commit()
        return {
            "message": "Feedback positif enregistré",
            "tweet_id": tweet.id,
            "sentiment": tweet.sentiment,
            "confidence": tweet.confidence,
            "requires_correction": False,
        }

    previous_negative_count = (
        db.query(Feedback)
        .filter(Feedback.user_id == current_user.id, Feedback.tweet_id == tweet.id, Feedback.vote == -1)
        .count()
    )

    # Niveau 2 : après un premier refus, l'utilisateur impose la bonne émotion.
    if payload.corrected_label:
        corrected_scores = {label: 0.0 for label in DISPLAY_SENTIMENTS}
        corrected_scores[payload.corrected_label] = 1.0

        feedback = Feedback(
            user_id=current_user.id,
            tweet_id=tweet.id,
            target_type=tweet.target.target_type.value if hasattr(tweet.target.target_type, "value") else str(tweet.target.target_type),
            target_id=tweet.target_id,
            vote=-1,
            corrected_label=payload.corrected_label,
            reason=payload.reason,
            metadata_json={
                "action": "classification_corrected_by_user",
                "previous_label": previous_label,
                "previous_scores": previous_scores,
                "attempt_index": previous_negative_count + 1,
            },
        )
        tweet.sentiment = payload.corrected_label
        tweet.confidence = 1.0
        tweet.sentiment_scores = corrected_scores
        tweet.analyzed_at = datetime.utcnow()
        db.add(feedback)
        db.commit()
        return {
            "message": "Correction utilisateur enregistrée. Elle sera exportée pour le réentraînement.",
            "tweet_id": tweet.id,
            "sentiment": tweet.sentiment,
            "confidence": tweet.confidence,
            "sentiment_scores": tweet.sentiment_scores,
            "requires_correction": False,
        }

    # Niveau 1 : premier refus -> on met le poids du label courant à 0 et on prend le second meilleur.
    if previous_negative_count == 0:
        new_label, new_confidence, reranked_scores = _rerank_with_zero_weight(previous_scores, {previous_label})
        feedback = Feedback(
            user_id=current_user.id,
            tweet_id=tweet.id,
            target_type=tweet.target.target_type.value if hasattr(tweet.target.target_type, "value") else str(tweet.target.target_type),
            target_id=tweet.target_id,
            vote=-1,
            corrected_label=None,
            reason=payload.reason,
            metadata_json={
                "action": "classification_regenerated_zero_weight",
                "forbidden_label": previous_label,
                "previous_scores": previous_scores,
                "reranked_scores": reranked_scores,
                "new_label": new_label,
            },
        )
        tweet.sentiment = new_label
        tweet.confidence = new_confidence
        tweet.sentiment_scores = reranked_scores
        tweet.analyzed_at = datetime.utcnow()
        db.add(feedback)
        db.commit()
        return {
            "message": f"Classification régénérée : l'ancien label '{previous_label}' a été mis à 0.",
            "tweet_id": tweet.id,
            "previous_sentiment": previous_label,
            "sentiment": tweet.sentiment,
            "confidence": tweet.confidence,
            "sentiment_scores": tweet.sentiment_scores,
            "requires_correction": True,
        }

    # Si le user refuse encore, on ne devine plus : on demande l'émotion correcte.
    feedback = Feedback(
        user_id=current_user.id,
        tweet_id=tweet.id,
        target_type=tweet.target.target_type.value if hasattr(tweet.target.target_type, "value") else str(tweet.target.target_type),
        target_id=tweet.target_id,
        vote=-1,
        corrected_label=None,
        reason=payload.reason,
        metadata_json={
            "action": "classification_requires_user_label",
            "previous_label": previous_label,
            "previous_scores": previous_scores,
            "attempt_index": previous_negative_count + 1,
        },
    )
    db.add(feedback)
    db.commit()
    return {
        "message": "Deuxième refus enregistré : choisis maintenant l'émotion correcte.",
        "tweet_id": tweet.id,
        "sentiment": tweet.sentiment,
        "confidence": tweet.confidence,
        "requires_correction": True,
        "allowed_labels": DISPLAY_SENTIMENTS,
    }


@router.post("/llm")
async def submit_llm_feedback(
    payload: LLMFeedbackRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Enregistre un feedback sur une réponse LLM et, si demandé, relance l'agent complet.

    Important : on ne dépend plus obligatoirement de target_ids côté frontend.
    Le premier patch pouvait échouer si le message ne contenait pas les ids de cibles.
    Ici, on redonne la question originale à l'agent : il réapplique la guardrail #/@,
    retrouve/crée la cible, réutilise les tweets existants, analyse ce qui manque et
    régénère une réponse + un dashboard.
    """
    regenerated = None
    regenerated_answer = None

    if payload.regenerate:
        try:
            regenerated = await run_sentiflow_agent(
                db=db,
                user_id=current_user.id,
                question=payload.question,
                days=payload.days,
                generate_dashboard=True,
                force_refresh=False,
                allow_auto_collect=True,
                allow_auto_analyze=True,
                feedback_context=payload.reason or "L'utilisateur n'est pas satisfait de la réponse précédente.",
            )
            regenerated_answer = regenerated.get("answer")
        except AgentError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    feedback = LLMFeedback(
        user_id=current_user.id,
        question=payload.question,
        previous_answer=payload.previous_answer,
        regenerated_answer=regenerated_answer,
        vote=-1 if payload.regenerate else 1,
        reason=payload.reason,
        metadata_json={
            "target_ids_from_frontend": payload.target_ids,
            "days": payload.days,
            "intent": payload.intent,
            "sentiment_filter": payload.sentiment_filter,
            "regeneration_mode": "agent_full_rerun",
        },
    )
    db.add(feedback)
    db.commit()

    return {
        "message": "Feedback LLM enregistré" + (" et réponse régénérée" if regenerated else ""),
        "feedback_id": feedback.id,
        "regenerated": regenerated,
    }
