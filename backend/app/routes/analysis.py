import logging
import time
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
import sys

from backend.app.database import get_db
from backend.app.models.user import User
from backend.app.models.tweet import Tweet, VALID_SENTIMENTS
from backend.app.models.target import Target
from backend.app.schemas.tweet import SentimentAnalysis
from backend.app.services.auth import get_current_user

# Ajouter le path pour importer le modèle sentiment
sys.path.insert(0, ".")
from services.sentiment.model import get_analyzer

logger = logging.getLogger("sentiflow.analysis")
logger.setLevel(logging.DEBUG)

router = APIRouter(prefix="/analysis", tags=["Analyse"])


@router.post("/{target_id}/analyze")
def analyze_tweets(
    target_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Analyse les tweets non analysés d'une cible avec le modèle de sentiment"""
    start_time = time.time()

    # Vérifier que la cible appartient à l'utilisateur
    target = db.query(Target).filter(
        Target.id == target_id,
        Target.user_id == current_user.id
    ).first()

    if not target:
        logger.warning(f"[ANALYSE] Cible #{target_id} non trouvée pour user #{current_user.id}")
        raise HTTPException(status_code=404, detail="Cible non trouvée")

    # Récupérer les tweets non analysés
    tweets = db.query(Tweet).filter(
        Tweet.target_id == target_id,
        Tweet.sentiment.is_(None)
    ).all()

    if not tweets:
        logger.info(f"[ANALYSE] ✅ Aucun tweet en attente d'analyse pour '{target.name}'")
        return {"message": "Aucun tweet à analyser", "analyzed": 0}

    logger.info(
        f"[ANALYSE] ▶ Début analyse IA pour '{target.name}' | "
        f"🧾 {len(tweets)} tweets en attente"
    )

    # Charger le modèle
    model_start = time.time()
    analyzer = get_analyzer()
    model_load_time = time.time() - model_start
    logger.info(f"[ANALYSE] 🤖 Modèle '{analyzer.model_name}' chargé en {model_load_time:.2f}s (device={'GPU' if analyzer.device == 0 else 'CPU'})")

    analyzed_count = 0
    errors = 0
    sentiment_stats = {s: 0 for s in VALID_SENTIMENTS}
    low_confidence_count = 0
    skipped_no_text = 0

    for i, tweet in enumerate(tweets):
        tweet_start = time.time()
        try:
            # Filtrer les tweets sans vrai contenu textuel
            import re
            clean = re.sub(r'http\S+|www\S+|https\S+', '', tweet.text or '')
            clean = re.sub(r'@\w+', '', clean)
            clean = re.sub(r'#\w+', '', clean)
            clean = re.sub(r'[^\w\s]', '', clean)
            clean = clean.strip()

            if len(clean) < 10:
                logger.warning(
                    f"[ANALYSE] ⏭ Tweet #{tweet.id} ignoré: pas assez de texte ({len(clean)} chars)"
                )
                skipped_no_text += 1
                continue

            # Prédire le sentiment
            scores = analyzer.predict(tweet.text)
            dominant, confidence = analyzer.get_dominant_sentiment(scores)
            tweet_time = time.time() - tweet_start

            # Seuil de confiance : si < 50%, marquer comme "incertain"
            CONFIDENCE_THRESHOLD = 0.50
            if confidence < CONFIDENCE_THRESHOLD:
                dominant = "incertain"

            # Mettre à jour le tweet
            tweet.sentiment_scores = scores
            tweet.confidence = confidence
            tweet.sentiment = dominant
            tweet.analyzed_at = datetime.utcnow()

            analyzed_count += 1
            sentiment_stats[dominant] = sentiment_stats.get(dominant, 0) + 1

            if confidence < 0.4:
                low_confidence_count += 1
                preview = tweet.text[:60].replace("\n", " ")
                logger.warning(
                    f"[ANALYSE] ⚠ Confiance faible ({confidence:.0%}) pour tweet #{tweet.id}: "
                    f"\"{preview}...\" → {dominant}"
                )

            # Log de progression tous les 10 tweets
            if (i + 1) % 10 == 0:
                elapsed = time.time() - start_time
                speed = (i + 1) / elapsed
                remaining = (len(tweets) - i - 1) / speed if speed > 0 else 0
                logger.info(
                    f"[ANALYSE] 📊 Progression: {i+1}/{len(tweets)} tweets "
                    f"({speed:.1f} tweets/s, ~{remaining:.0f}s restantes)"
                )

            # Log détaillé pour les 3 premiers tweets
            if i < 3:
                preview = tweet.text[:80].replace("\n", " ")
                scores_str = " | ".join(f"{k}={v:.0%}" for k, v in sorted(scores.items(), key=lambda x: -x[1])[:3])
                logger.debug(
                    f"[ANALYSE] 🔬 Tweet #{tweet.id} @{tweet.author_username or '?'}: "
                    f"\"{preview}\" → {dominant} ({confidence:.0%}) [{scores_str}]"
                )

        except Exception as e:
            errors += 1
            logger.error(f"[ANALYSE] ❌ Erreur analyse tweet #{tweet.id}: {e}")
            continue

    db.commit()

    total_time = time.time() - start_time
    speed = analyzed_count / total_time if total_time > 0 else 0

    # Résumé des sentiments détectés
    sentiment_summary = " | ".join(
        f"{k}: {v} ({v/analyzed_count*100:.0f}%)"
        for k, v in sorted(sentiment_stats.items(), key=lambda x: -x[1])
        if v > 0
    ) if analyzed_count > 0 else "aucun"

    logger.info(
        f"[ANALYSE] ✅ Analyse terminée pour '{target.name}' en {total_time:.2f}s | "
        f"🤖 {analyzed_count}/{len(tweets)} analysés ({speed:.1f} tweets/s)"
    )
    logger.info(f"[ANALYSE] 📈 Répartition: {sentiment_summary}")

    if errors > 0:
        logger.warning(f"[ANALYSE] ⚠ {errors} erreurs rencontrées pendant l'analyse")

    if low_confidence_count > 0:
        logger.warning(
            f"[ANALYSE] ⚠ {low_confidence_count}/{analyzed_count} tweets avec confiance < 40% — "
            f"le modèle hésite sur ces textes"
        )

    return {
        "message": f"{analyzed_count} tweets analysés",
        "analyzed": analyzed_count,
        "total": len(tweets),
        "errors": errors,
        "low_confidence": low_confidence_count,
        "sentiment_distribution": sentiment_stats,
        "duration_seconds": round(total_time, 2),
        "speed_tweets_per_sec": round(speed, 1)
    }


@router.get("/{target_id}", response_model=SentimentAnalysis)
def get_sentiment_analysis(
    target_id: int,
    days: int = Query(default=7, le=30),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Récupère l'analyse de sentiment pour une cible"""
    
    # Vérifier que la cible appartient à l'utilisateur (admin voit tout)
    if current_user.is_admin:
        target = db.query(Target).filter(Target.id == target_id).first()
    else:
        target = db.query(Target).filter(
            Target.id == target_id, 
            Target.user_id == current_user.id
        ).first()
    
    if not target:
        raise HTTPException(status_code=404, detail="Cible non trouvée")
    
    since = datetime.utcnow() - timedelta(days=days)
    
    # Compter les tweets par sentiment
    results = db.query(
        Tweet.sentiment,
        func.count(Tweet.id).label("count"),
        func.avg(Tweet.confidence).label("avg_confidence")
    ).filter(
        Tweet.target_id == target_id,
        Tweet.analyzed_at >= since,
        Tweet.sentiment.isnot(None)
    ).group_by(Tweet.sentiment).all()
    
    total = sum(r.count for r in results)
    
    # Construire la distribution
    distribution = {s: 0.0 for s in VALID_SENTIMENTS}
    avg_confidence = 0.0
    
    if total > 0:
        for r in results:
            if r.sentiment in distribution:
                distribution[r.sentiment] = round(r.count / total, 3)
        avg_confidence = sum(r.avg_confidence * r.count for r in results) / total
    
    return SentimentAnalysis(
        target_id=target_id,
        target_name=target.name,
        period=f"{days}d",
        total_tweets=total,
        sentiment_distribution=distribution,
        average_confidence=round(avg_confidence, 3)
    )
