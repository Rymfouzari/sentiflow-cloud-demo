import asyncio
import json
import os
import subprocess
import logging
import time
from datetime import datetime, timedelta
from sqlalchemy import func
from backend.app.celery_app import celery_app
from backend.app.database import SessionLocal
from backend.app.models.target import Target
from backend.app.models.tweet import Tweet, VALID_SENTIMENTS
from backend.app.models.alert import Alert
from backend.app.models.sentiment_aggregate import SentimentAggregate
from backend.app.models.feedback import Feedback

logger = logging.getLogger("sentiflow.celery")
logger.setLevel(logging.DEBUG)


def get_db():
    db = SessionLocal()
    try:
        return db
    except:
        db.close()
        raise


# --- COLLECTE AUTO ---

@celery_app.task(name="backend.app.tasks.collect_all_targets")
def collect_all_targets():
    """Collecte les tweets et les envoie dans Kafka. Respecte le flag Redis de pause."""
    import redis
    from backend.app.config import get_settings

    # Vérifier si la collecte est pausée par l'admin
    try:
        r = redis.from_url(get_settings().redis_url)
        if r.get("sentiflow:collect_paused"):
            logger.info("[CELERY:COLLECTE] ⏸ Collecte pausée par l'admin, ignorée")
            return {"message": "Collecte pausée par l'admin"}
    except Exception:
        pass

    from backend.app.services.twitter import twitter_service
    from backend.app.kafka_producer import get_producer, send_tweet_to_kafka, flush_producer

    start_time = time.time()
    db = get_db()
    try:
        targets = db.query(Target).all()

        if not targets:
            logger.info("[CELERY:COLLECTE] ℹ Aucune cible en base, collecte ignorée")
            return {"message": "Aucune cible"}

        logger.info(f"[CELERY:COLLECTE] ▶ Début collecte automatique pour {len(targets)} cible(s)")

        producer = get_producer()
        results = []
        total_sent = 0

        for i, target in enumerate(targets):
            # Respecter le rate limit de l'API Twitter (1 req / 5s pour le tier gratuit)
            if i > 0:
                logger.info(f"[CELERY:COLLECTE] ⏳ Pause 6s (rate limit API Twitter)...")
                time.sleep(6)

            target_start = time.time()
            try:
                sent = _collect_and_produce(target, twitter_service, producer)
                target_time = time.time() - target_start
                total_sent += sent
                results.append({"target": target.name, "sent_to_kafka": sent})
                logger.info(
                    f"[CELERY:COLLECTE] 📤 '{target.name}' → {sent} tweets envoyés à Kafka "
                    f"en {target_time:.2f}s"
                )
            except Exception as e:
                results.append({"target": target.name, "error": str(e)})
                logger.error(f"[CELERY:COLLECTE] ❌ Erreur pour '{target.name}': {e}")

        flush_producer(producer)
        producer.close()

        total_time = time.time() - start_time
        logger.info(
            f"[CELERY:COLLECTE] ✅ Collecte terminée en {total_time:.2f}s | "
            f"{total_sent} tweets envoyés à Kafka pour {len(targets)} cible(s)"
        )
        return results
    finally:
        db.close()


def _collect_and_produce(target, twitter_service, producer):
    """Collecte les tweets et les envoie dans Kafka"""
    from backend.app.kafka_producer import send_tweet_to_kafka

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        if target.target_type.value == "hashtag":
            logger.debug(f"[CELERY:COLLECTE] 🔍 Recherche hashtag: {target.query}")
            data = loop.run_until_complete(twitter_service.search_tweets(target.query))
        else:
            username = target.name.lstrip("@")
            logger.debug(f"[CELERY:COLLECTE] 👤 Récupération tweets de @{username}")
            data = loop.run_until_complete(twitter_service.get_user_tweets(username))
    finally:
        loop.close()

    if "error" in data:
        raise Exception(data["error"])

    tweets_data = data.get("tweets", data.get("data", []))
    
    # Format compte: data.data.tweets (dict imbriqué)
    if isinstance(tweets_data, dict):
        tweets_data = tweets_data.get("tweets", tweets_data.get("results", []))
    
    if not isinstance(tweets_data, list):
        tweets_data = []

    sent = 0

    for tweet_data in tweets_data:
        if isinstance(tweet_data, dict):
            send_tweet_to_kafka(producer, tweet_data, target.id, target.name)
            sent += 1

    return sent


# --- ANALYSE AUTO ---

@celery_app.task(name="backend.app.tasks.analyze_all_targets")
def analyze_all_targets():
    """Analyse les tweets non analysés pour toutes les cibles"""
    import sys
    sys.path.insert(0, ".")
    from services.sentiment.model import get_analyzer

    start_time = time.time()
    db = get_db()
    try:
        logger.info("[CELERY:ANALYSE] 🤖 Chargement du modèle de sentiment...")
        model_start = time.time()
        analyzer = get_analyzer()
        model_time = time.time() - model_start
        logger.info(
            f"[CELERY:ANALYSE] 🤖 Modèle chargé en {model_time:.2f}s "
            f"(device={'GPU' if analyzer.device == 0 else 'CPU'})"
        )

        tweets = db.query(Tweet).filter(Tweet.sentiment.is_(None)).all()

        if not tweets:
            logger.info("[CELERY:ANALYSE] ✅ Aucun tweet en attente d'analyse")
            return {"analyzed": 0}

        logger.info(f"[CELERY:ANALYSE] ▶ Début analyse de {len(tweets)} tweets non analysés")

        analyzed = 0
        errors = 0
        low_confidence = 0
        sentiment_stats = {}

        for i, tweet in enumerate(tweets):
            try:
                scores = analyzer.predict(tweet.text)
                dominant, confidence = analyzer.get_dominant_sentiment(scores)

                tweet.sentiment_scores = scores
                tweet.confidence = confidence
                tweet.sentiment = dominant
                tweet.analyzed_at = datetime.utcnow()
                analyzed += 1

                sentiment_stats[dominant] = sentiment_stats.get(dominant, 0) + 1

                if confidence < 0.4:
                    low_confidence += 1
                    preview = tweet.text[:60].replace("\n", " ")
                    logger.warning(
                        f"[CELERY:ANALYSE] ⚠ Confiance faible ({confidence:.0%}) tweet #{tweet.id}: "
                        f"\"{preview}...\" → {dominant}"
                    )

                # Progression tous les 25 tweets
                if (i + 1) % 25 == 0:
                    elapsed = time.time() - start_time
                    speed = (i + 1) / elapsed
                    logger.info(
                        f"[CELERY:ANALYSE] 📊 Progression: {i+1}/{len(tweets)} "
                        f"({speed:.1f} tweets/s)"
                    )

            except Exception as e:
                errors += 1
                logger.error(f"[CELERY:ANALYSE] ❌ Erreur tweet #{tweet.id}: {e}")
                continue

        db.commit()

        total_time = time.time() - start_time
        speed = analyzed / total_time if total_time > 0 else 0

        sentiment_summary = " | ".join(
            f"{k}: {v} ({v/analyzed*100:.0f}%)"
            for k, v in sorted(sentiment_stats.items(), key=lambda x: -x[1])
            if v > 0
        ) if analyzed > 0 else "aucun"

        logger.info(
            f"[CELERY:ANALYSE] ✅ Analyse terminée en {total_time:.2f}s | "
            f"{analyzed}/{len(tweets)} analysés ({speed:.1f} tweets/s)"
        )
        logger.info(f"[CELERY:ANALYSE] 📈 Répartition: {sentiment_summary}")

        if errors > 0:
            logger.warning(f"[CELERY:ANALYSE] ⚠ {errors} erreurs rencontrées")
        if low_confidence > 0:
            logger.warning(
                f"[CELERY:ANALYSE] ⚠ {low_confidence}/{analyzed} tweets avec confiance < 40%"
            )

        return {"analyzed": analyzed, "errors": errors, "low_confidence": low_confidence}
    finally:
        db.close()


# --- ALERTES AUTO ---

@celery_app.task(name="backend.app.tasks.check_all_alerts")
def check_all_alerts():
    """Vérifie toutes les alertes actives et déclenche si seuil dépassé"""
    db = get_db()
    try:
        alerts = db.query(Alert).filter(Alert.is_active == True).all()

        if not alerts:
            logger.info("[CELERY:ALERTES] ℹ Aucune alerte active")
            return {"checked": 0, "triggered": []}

        logger.info(f"[CELERY:ALERTES] 🔔 Vérification de {len(alerts)} alerte(s) active(s)")
        triggered = []

        for alert in alerts:
            try:
                was_triggered = _check_alert(db, alert)
                if was_triggered:
                    triggered.append(alert.name)
                    logger.warning(
                        f"[CELERY:ALERTES] 🚨 ALERTE DÉCLENCHÉE: '{alert.name}' | "
                        f"sentiment={alert.sentiment}, seuil={'>' if alert.is_above else '<'}{alert.threshold:.0%}"
                    )
                else:
                    logger.debug(f"[CELERY:ALERTES] ✅ Alerte '{alert.name}' OK (seuil non dépassé)")
            except Exception as e:
                logger.error(f"[CELERY:ALERTES] ❌ Erreur alerte #{alert.id} '{alert.name}': {e}")

        db.commit()
        logger.info(
            f"[CELERY:ALERTES] ✅ Vérification terminée: "
            f"{len(triggered)}/{len(alerts)} alerte(s) déclenchée(s)"
        )
        return {"checked": len(alerts), "triggered": triggered}
    finally:
        db.close()


def _check_alert(db, alert):
    """Vérifie une alerte et la déclenche si nécessaire"""
    since = datetime.utcnow() - timedelta(days=7)

    # Compter les tweets par sentiment pour cette cible
    results = db.query(
        Tweet.sentiment,
        func.count(Tweet.id).label("count")
    ).filter(
        Tweet.target_id == alert.target_id,
        Tweet.analyzed_at >= since,
        Tweet.sentiment.isnot(None)
    ).group_by(Tweet.sentiment).all()

    total = sum(r.count for r in results)
    if total == 0:
        return False

    # Calculer le ratio du sentiment surveillé
    sentiment_count = 0
    for r in results:
        if r.sentiment == alert.sentiment:
            sentiment_count = r.count
            break

    ratio = sentiment_count / total

    # Vérifier le seuil
    if alert.is_above and ratio > alert.threshold:
        alert.last_triggered = datetime.utcnow()
        return True
    elif not alert.is_above and ratio < alert.threshold:
        alert.last_triggered = datetime.utcnow()
        return True

    return False


# --- AGRÉGATION ---

@celery_app.task(name="backend.app.tasks.aggregate_sentiments")
def aggregate_sentiments():
    """Pré-calcule les agrégations de sentiments par jour"""
    start_time = time.time()
    db = get_db()
    try:
        targets = db.query(Target).all()

        if not targets:
            logger.info("[CELERY:AGREG] ℹ Aucune cible, agrégation ignorée")
            return {"targets": 0}

        logger.info(f"[CELERY:AGREG] 📊 Début agrégation pour {len(targets)} cible(s)")

        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        aggregated = 0

        for target in targets:
            # Compter les tweets du jour par sentiment
            results = db.query(
                Tweet.sentiment,
                func.count(Tweet.id).label("count")
            ).filter(
                Tweet.target_id == target.id,
                Tweet.analyzed_at >= today_start,
                Tweet.analyzed_at < today_end,
                Tweet.sentiment.isnot(None)
            ).group_by(Tweet.sentiment).all()

            total = sum(r.count for r in results)
            if total == 0:
                logger.debug(f"[CELERY:AGREG] ⏭ '{target.name}': aucun tweet analysé aujourd'hui")
                continue

            counts = {s: 0 for s in VALID_SENTIMENTS}
            scores = {s: 0.0 for s in VALID_SENTIMENTS}
            for r in results:
                if r.sentiment in counts:
                    counts[r.sentiment] = r.count
                    scores[r.sentiment] = round(r.count / total, 4)

            # Upsert l'agrégation du jour
            existing = db.query(SentimentAggregate).filter(
                SentimentAggregate.target_id == target.id,
                SentimentAggregate.bucket_start == today_start,
                SentimentAggregate.granularity == "day"
            ).first()

            if existing:
                existing.total_posts = total
                existing.counts_json = counts
                existing.scores_json = scores
                existing.computed_at = now
            else:
                agg = SentimentAggregate(
                    target_id=target.id,
                    bucket_start=today_start,
                    bucket_end=today_end,
                    granularity="day",
                    total_posts=total,
                    counts_json=counts,
                    scores_json=scores,
                    computed_at=now
                )
                db.add(agg)

            aggregated += 1
            dominant = max(counts, key=counts.get)
            logger.info(
                f"[CELERY:AGREG] 📊 '{target.name}': {total} tweets | "
                f"dominant={dominant} ({scores[dominant]:.0%})"
            )

        db.commit()
        total_time = time.time() - start_time
        logger.info(
            f"[CELERY:AGREG] ✅ Agrégation terminée en {total_time:.2f}s | "
            f"{aggregated}/{len(targets)} cible(s) avec données"
        )
        return {"targets": len(targets), "aggregated": aggregated}
    finally:
        db.close()


# --- FEEDBACK LOOP / RETRAINING ---

@celery_app.task(name="backend.app.tasks.retrain_sentiment_from_feedback")
def retrain_sentiment_from_feedback():
    """
    Tâche hebdomadaire de feedback loop.

    Par défaut, elle exporte les corrections validées par les utilisateurs en JSONL.
    Pour lancer un vrai fine-tuning automatiquement, définir :
    SENTIFLOW_FEEDBACK_RETRAIN_CMD="python scripts/train_sentiment_with_feedback.py --input /app/data/feedback/latest.jsonl"
    """
    db = get_db()
    try:
        rows = (
            db.query(Feedback, Tweet)
            .join(Tweet, Tweet.id == Feedback.tweet_id)
            .filter(Feedback.vote == -1, Feedback.corrected_label.isnot(None))
            .order_by(Feedback.created_at.asc())
            .all()
        )

        output_dir = os.getenv("SENTIFLOW_FEEDBACK_DIR", "/app/data/feedback")
        os.makedirs(output_dir, exist_ok=True)
        dated_path = os.path.join(output_dir, f"sentiment_feedback_{datetime.utcnow().strftime('%Y%m%d')}.jsonl")
        latest_path = os.path.join(output_dir, "latest.jsonl")

        exported = 0
        with open(dated_path, "w", encoding="utf-8") as dated_file, open(latest_path, "w", encoding="utf-8") as latest_file:
            for feedback, tweet in rows:
                record = {
                    "text": tweet.text,
                    "label": feedback.corrected_label,
                    "tweet_id": tweet.id,
                    "target_id": tweet.target_id,
                    "feedback_id": feedback.id,
                    "created_at": feedback.created_at.isoformat() if feedback.created_at else None,
                    "metadata": feedback.metadata_json or {},
                }
                line = json.dumps(record, ensure_ascii=False)
                dated_file.write(line + "\n")
                latest_file.write(line + "\n")
                exported += 1

        command = os.getenv("SENTIFLOW_FEEDBACK_RETRAIN_CMD")
        retrain_result = None
        if command and exported > 0:
            logger.info("[CELERY:FEEDBACK] Lancement réentraînement feedback: %s", command)
            completed = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60 * 60 * 3)
            retrain_result = {
                "returncode": completed.returncode,
                "stdout_tail": completed.stdout[-2000:],
                "stderr_tail": completed.stderr[-2000:],
            }
            if completed.returncode != 0:
                logger.error("[CELERY:FEEDBACK] Réentraînement en erreur: %s", retrain_result["stderr_tail"])
            else:
                logger.info("[CELERY:FEEDBACK] Réentraînement terminé")
        else:
            logger.info(
                "[CELERY:FEEDBACK] %s corrections exportées. Aucun réentraînement lancé%s.",
                exported,
                " car SENTIFLOW_FEEDBACK_RETRAIN_CMD est vide" if not command else " car aucune correction n'est disponible",
            )

        return {
            "exported": exported,
            "dataset_path": dated_path,
            "latest_path": latest_path,
            "retrain_result": retrain_result,
        }
    finally:
        db.close()


# --- PIPELINE TINYGPT AUTO ---

@celery_app.task(name="backend.app.tasks.retrain_tinygpt_pipeline")
def retrain_tinygpt_pipeline():
    """
    Tâche planifiée tous les 2 jours.
    Lance la pipeline d'entraînement TinyGPT :
    export BDD → fusion → entraînement → évaluation → remplacement conditionnel.
    """
    import subprocess

    logger.info("[CELERY:TINYGPT] Lancement pipeline de ré-entraînement TinyGPT...")

    try:
        result = subprocess.run(
            ["python", "scripts/auto_retrain_pipeline.py", "--epochs", "4", "--synthetic-examples", "6000"],
            capture_output=True,
            text=True,
            timeout=3600 * 2,  # 2h max
            cwd="/app",
        )

        if result.returncode == 0:
            logger.info("[CELERY:TINYGPT] Pipeline terminée avec succès")
            logger.info(result.stdout[-1000:])
        else:
            logger.error(f"[CELERY:TINYGPT] Pipeline en erreur (code {result.returncode})")
            logger.error(result.stderr[-1000:])

        return {
            "returncode": result.returncode,
            "stdout_tail": result.stdout[-500:],
            "stderr_tail": result.stderr[-500:],
        }
    except subprocess.TimeoutExpired:
        logger.error("[CELERY:TINYGPT] Pipeline timeout (>2h)")
        return {"error": "timeout"}
    except Exception as e:
        logger.error(f"[CELERY:TINYGPT] Erreur: {e}")
        return {"error": str(e)}
