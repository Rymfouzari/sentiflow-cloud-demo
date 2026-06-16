"""
Monitoring des predictions ML et detection de data drift.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
from collections import Counter
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.app.models.tweet import Tweet, VALID_SENTIMENTS
from backend.app.models.prediction_log import PredictionLog
from backend.app.models.drift_log import DriftLog

logger = logging.getLogger("sentiflow.monitoring")


def log_prediction(
    db: Session,
    tweet_id: Optional[int],
    text: str,
    sentiment: str,
    confidence: float,
    scores: Dict,
    inference_time_ms: float,
    model_version: str = "v10",
):
    """Log une prediction du modele ML"""
    log = PredictionLog(
        tweet_id=tweet_id,
        text_preview=text[:200],
        predicted_sentiment=sentiment,
        confidence=confidence,
        scores=scores,
        inference_time_ms=inference_time_ms,
        model_version=model_version,
    )
    db.add(log)
    db.flush()
    return log


def get_monitoring_stats(db: Session, hours: int = 24) -> Dict:
    """Statistiques de monitoring sur les dernieres heures"""
    since = datetime.utcnow() - timedelta(hours=hours)

    logs = db.query(PredictionLog).filter(PredictionLog.created_at >= since).all()

    if not logs:
        return {"period_hours": hours, "total_predictions": 0}

    confidences = [l.confidence for l in logs]
    inference_times = [l.inference_time_ms for l in logs if l.inference_time_ms]
    sentiments = Counter(l.predicted_sentiment for l in logs)

    low_confidence = sum(1 for c in confidences if c < 0.5)

    return {
        "period_hours": hours,
        "total_predictions": len(logs),
        "avg_confidence": round(np.mean(confidences), 3),
        "min_confidence": round(min(confidences), 3),
        "low_confidence_count": low_confidence,
        "low_confidence_pct": round(low_confidence / len(logs) * 100, 1),
        "avg_inference_ms": round(np.mean(inference_times), 1) if inference_times else None,
        "sentiment_distribution": dict(sentiments.most_common()),
        "model_versions": dict(Counter(l.model_version for l in logs)),
    }


def detect_drift(
    db: Session,
    target_id: Optional[int] = None,
    reference_days: int = 14,
    current_days: int = 7,
    threshold: float = 0.15,
) -> Dict:
    """
    Detecte le data drift en comparant la distribution des sentiments
    entre une periode de reference et la periode actuelle.

    Utilise la distance de Jensen-Shannon (symetrique, bornee entre 0 et 1).
    """
    now = datetime.utcnow()
    ref_start = now - timedelta(days=reference_days + current_days)
    ref_end = now - timedelta(days=current_days)
    cur_start = now - timedelta(days=current_days)

    # Filtres de base
    base_filter = [Tweet.sentiment.isnot(None)]
    if target_id:
        base_filter.append(Tweet.target_id == target_id)

    # Distribution de reference
    ref_results = db.query(
        Tweet.sentiment, func.count(Tweet.id)
    ).filter(
        *base_filter,
        Tweet.analyzed_at >= ref_start,
        Tweet.analyzed_at < ref_end,
    ).group_by(Tweet.sentiment).all()

    # Distribution actuelle
    cur_results = db.query(
        Tweet.sentiment, func.count(Tweet.id)
    ).filter(
        *base_filter,
        Tweet.analyzed_at >= cur_start,
    ).group_by(Tweet.sentiment).all()

    ref_total = sum(c for _, c in ref_results)
    cur_total = sum(c for _, c in cur_results)

    if ref_total == 0 or cur_total == 0:
        return {
            "drift_detected": False,
            "message": "Pas assez de donnees pour detecter le drift",
            "ref_total": ref_total,
            "cur_total": cur_total,
        }

    # Construire les distributions
    all_sentiments = list(set(s for s, _ in ref_results) | set(s for s, _ in cur_results))
    ref_dist = {s: 0.0 for s in all_sentiments}
    cur_dist = {s: 0.0 for s in all_sentiments}

    for s, c in ref_results:
        ref_dist[s] = c / ref_total
    for s, c in cur_results:
        cur_dist[s] = c / cur_total

    # Jensen-Shannon divergence
    ref_arr = np.array([ref_dist.get(s, 0) for s in all_sentiments])
    cur_arr = np.array([cur_dist.get(s, 0) for s in all_sentiments])

    # Ajouter un petit epsilon pour eviter log(0)
    eps = 1e-10
    ref_arr = ref_arr + eps
    cur_arr = cur_arr + eps
    ref_arr = ref_arr / ref_arr.sum()
    cur_arr = cur_arr / cur_arr.sum()

    m = 0.5 * (ref_arr + cur_arr)
    js_div = 0.5 * np.sum(ref_arr * np.log(ref_arr / m)) + 0.5 * np.sum(cur_arr * np.log(cur_arr / m))
    drift_score = float(np.sqrt(js_div))  # JS distance (0 a 1)

    is_drift = drift_score > threshold

    # Details par sentiment
    details = {}
    for s in all_sentiments:
        ref_pct = ref_dist.get(s, 0) * 100
        cur_pct = cur_dist.get(s, 0) * 100
        change = cur_pct - ref_pct
        details[s] = {
            "reference_pct": round(ref_pct, 1),
            "current_pct": round(cur_pct, 1),
            "change_pct": round(change, 1),
        }

    # Sauvegarder le log
    drift_log = DriftLog(
        target_id=target_id,
        period_start=ref_start,
        period_end=now,
        reference_distribution=ref_dist,
        current_distribution=cur_dist,
        drift_score=drift_score,
        is_drift_detected=is_drift,
        drift_threshold=threshold,
        details=details,
    )
    db.add(drift_log)
    db.commit()

    if is_drift:
        logger.warning(
            f"[DRIFT] DRIFT DETECTE (score={drift_score:.3f}, seuil={threshold}) "
            f"target_id={target_id}"
        )
    else:
        logger.info(f"[DRIFT] Pas de drift (score={drift_score:.3f}, seuil={threshold})")

    return {
        "drift_detected": is_drift,
        "drift_score": round(drift_score, 3),
        "threshold": threshold,
        "reference_period": f"{reference_days}j (avant les {current_days} derniers jours)",
        "current_period": f"{current_days} derniers jours",
        "ref_total": ref_total,
        "cur_total": cur_total,
        "details": details,
    }
