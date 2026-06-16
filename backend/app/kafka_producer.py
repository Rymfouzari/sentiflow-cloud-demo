import json
import logging
import os
from kafka import KafkaProducer

logger = logging.getLogger("sentiflow.kafka_producer")

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
TOPIC_TWEETS_RAW = "tweets-raw"


def get_producer():
    """Crée un producer Kafka"""
    logger.info(f"[PRODUCER] 🔌 Connexion au producer Kafka ({KAFKA_BOOTSTRAP_SERVERS})")
    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k else None,
    )
    logger.info("[PRODUCER] ✅ Producer Kafka connecté")
    return producer


def send_tweet_to_kafka(producer, tweet_data: dict, target_id: int, target_name: str):
    """Envoie un tweet brut dans le topic Kafka"""
    message = {
        "target_id": target_id,
        "target_name": target_name,
        "twitter_id": str(tweet_data.get("id", "")),
        "text": tweet_data.get("text", ""),
        "author_id": str(tweet_data.get("author", {}).get("id", "")),
        "author_username": tweet_data.get("author", {}).get("userName", ""),
        "created_at": tweet_data.get("createdAt", ""),
        "lang": tweet_data.get("lang", ""),
    }

    preview = message["text"][:60].replace("\n", " ")
    logger.debug(
        f"[PRODUCER] 📤 → Kafka [{target_name}] @{message['author_username'] or '?'}: "
        f"\"{preview}...\""
    )

    producer.send(
        TOPIC_TWEETS_RAW,
        key=str(target_id),
        value=message,
    )


def flush_producer(producer):
    """Force l'envoi de tous les messages en attente"""
    producer.flush()
    logger.info("[PRODUCER] 📨 Tous les messages envoyés (flush)")
