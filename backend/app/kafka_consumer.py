import json
import logging
import os
import sys
import time
from datetime import datetime
from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable

# Path pour le modèle sentiment
sys.path.insert(0, "/app")

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("sentiflow.kafka_consumer")

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
TOPIC_TWEETS_RAW = "tweets-raw"
TOPIC_TWEETS_ANALYZED = "tweets-analyzed"


def create_consumer():
    """Crée un consumer Kafka avec retry"""
    logger.info(f"[KAFKA] Connexion a Kafka ({KAFKA_BOOTSTRAP_SERVERS})...")
    for attempt in range(10):
        try:
            consumer = KafkaConsumer(
                TOPIC_TWEETS_RAW,
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                group_id="sentiflow-analyzer",
                auto_offset_reset="earliest",
                enable_auto_commit=True,
            )
            logger.info(f"[KAFKA] Connecte a Kafka (tentative {attempt+1})")
            return consumer
        except NoBrokersAvailable:
            logger.warning(f"[KAFKA] Kafka pas pret, retry {attempt+1}/10...")
            time.sleep(5)

    raise Exception("Impossible de se connecter a Kafka apres 10 tentatives")


def process_tweet(db, analyzer, message):
    """Traite un tweet : sauvegarde en DB + analyse sentiment"""
    from backend.app.models.tweet import Tweet

    data = message.value
    twitter_id = data.get("twitter_id", "")
    target_name = data.get("target_name", "?")

    # Verifier si le tweet existe deja
    exists = db.query(Tweet).filter(Tweet.twitter_id == twitter_id).first()
    if exists:
        logger.debug(f"[KAFKA] Tweet {twitter_id[:15]}... deja en base, ignore")
        return None

    # Parser la date du tweet
    tweet_date = None
    created_at_str = data.get("created_at", "")
    if created_at_str:
        try:
            tweet_date = datetime.strptime(created_at_str, "%a %b %d %H:%M:%S %z %Y")
        except Exception:
            tweet_date = None

    # Analyser le sentiment
    text = data.get("text", "")
    if not text.strip():
        logger.warning(f"[KAFKA] Tweet {twitter_id[:15]}... ignore: texte vide")
        return None

    # Tronquer a 1000 caracteres (limite colonne DB)
    text = text[:1000]

    # Filtrer les tweets sans vrai contenu textuel (images, liens seuls, emojis seuls)
    import re
    clean = re.sub(r'http\S+|www\S+|https\S+', '', text)  # supprimer URLs
    clean = re.sub(r'@\w+', '', clean)  # supprimer mentions
    clean = re.sub(r'#\w+', '', clean)  # supprimer hashtags
    clean = re.sub(r'[^\w\s]', '', clean)  # supprimer emojis/ponctuation
    clean = clean.strip()

    if len(clean) < 10:
        logger.warning(f"[KAFKA] Tweet {twitter_id[:15]}... ignore: pas assez de texte ({len(clean)} chars)")
        # Sauvegarder quand meme en DB mais sans analyse
        try:
            tweet = Tweet(
                twitter_id=twitter_id,
                target_id=data.get("target_id"),
                text=text,
                author_id=data.get("author_id", ""),
                author_username=data.get("author_username", ""),
                sentiment=None,
                sentiment_scores=None,
                confidence=None,
                tweet_created_at=tweet_date,
                analyzed_at=None,
            )
            db.add(tweet)
            db.flush()
            db.commit()
        except Exception:
            db.rollback()
        return None

    analysis_start = time.time()
    scores = analyzer.predict(text)
    dominant, confidence = analyzer.get_dominant_sentiment(scores)
    analysis_time = time.time() - analysis_start

    # Seuil de confiance : si < 50%, marquer comme "incertain"
    CONFIDENCE_THRESHOLD = 0.50
    if confidence < CONFIDENCE_THRESHOLD:
        logger.info(
            f"[KAFKA] Confiance trop faible ({confidence:.0%}) pour tweet {twitter_id[:15]}... "
            f"-> incertain (au lieu de {dominant})"
        )
        dominant = "incertain"

    # Sauvegarder en DB
    try:
        tweet = Tweet(
            twitter_id=twitter_id,
            target_id=data.get("target_id"),
            text=text,
            author_id=data.get("author_id", ""),
            author_username=data.get("author_username", ""),
            sentiment=dominant,
            sentiment_scores=scores,
            confidence=confidence,
            tweet_created_at=tweet_date,
            analyzed_at=datetime.utcnow(),
        )
        db.add(tweet)
        db.flush()
        db.commit()

        preview = text[:70].replace("\n", " ")
        author = data.get("author_username", "?")

        if confidence < 0.4:
            logger.warning(
                f"[KAFKA] Confiance faible | @{author} -> {dominant} ({confidence:.0%}) | "
                f'"{preview}..." [{analysis_time:.3f}s]'
            )
        else:
            logger.info(
                f"[KAFKA] @{author} [{target_name}] -> {dominant} ({confidence:.0%}) | "
                f'"{preview}..." [{analysis_time:.3f}s]'
            )

        return tweet
    except Exception as e:
        db.rollback()
        logger.error(f"[KAFKA] Erreur sauvegarde tweet {twitter_id[:15]}...: {e}")
        return None


def run_consumer():
    """Boucle principale du consumer"""
    from backend.app.database import SessionLocal
    from services.sentiment.model import get_analyzer

    logger.info("=" * 60)
    logger.info("[KAFKA] Demarrage du Kafka Consumer SentiFlow")
    logger.info("=" * 60)

    logger.info("[KAFKA] Chargement du modele de sentiment...")
    model_start = time.time()
    analyzer = get_analyzer()
    model_time = time.time() - model_start
    device_str = "GPU" if analyzer.device == 0 else "CPU"
    logger.info(f"[KAFKA] Modele '{analyzer.model_name}' charge en {model_time:.2f}s ({device_str})")

    consumer = create_consumer()
    db = SessionLocal()

    logger.info(f"[KAFKA] En ecoute sur le topic '{TOPIC_TWEETS_RAW}'...")

    processed = 0
    errors = 0
    duplicates = 0
    start_time = time.time()
    last_log_time = start_time
    sentiment_counts = {}

    try:
        for message in consumer:
            result = process_tweet(db, analyzer, message)

            if result:
                processed += 1
                sent = result.sentiment
                sentiment_counts[sent] = sentiment_counts.get(sent, 0) + 1
            else:
                duplicates += 1

            # Resume toutes les 20 secondes ou tous les 10 tweets
            now = time.time()
            if processed > 0 and (processed % 10 == 0 or now - last_log_time > 20):
                elapsed = now - start_time
                speed = processed / elapsed if elapsed > 0 else 0
                sentiment_summary = " | ".join(
                    f"{k}: {v}" for k, v in sorted(sentiment_counts.items(), key=lambda x: -x[1])
                )
                logger.info(
                    f"[KAFKA] Bilan: {processed} traites, {duplicates} doublons, "
                    f"{errors} erreurs | {speed:.1f} tweets/s | {sentiment_summary}"
                )
                last_log_time = now

    except KeyboardInterrupt:
        total_time = time.time() - start_time
        logger.info("=" * 60)
        logger.info(f"[KAFKA] Arret du consumer")
        logger.info(
            f"[KAFKA] Bilan final: {processed} traites, {duplicates} doublons, "
            f"{errors} erreurs en {total_time:.0f}s"
        )
        logger.info("=" * 60)
    finally:
        consumer.close()
        db.close()


if __name__ == "__main__":
    run_consumer()
