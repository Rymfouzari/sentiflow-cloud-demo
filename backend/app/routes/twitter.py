import logging
import time
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.models.user import User
from backend.app.models.target import Target
from backend.app.models.tweet import Tweet
from backend.app.services.auth import get_current_user
from backend.app.services.twitter import twitter_service
from datetime import datetime

logger = logging.getLogger("sentiflow.twitter")
logger.setLevel(logging.DEBUG)

router = APIRouter(prefix="/twitter", tags=["Twitter"])


@router.post("/collect/{target_id}")
async def collect_tweets(
    target_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Collecte les tweets pour une cible donnée"""
    start_time = time.time()

    # Vérifier que la cible appartient à l'utilisateur
    target = db.query(Target).filter(
        Target.id == target_id,
        Target.user_id == current_user.id
    ).first()

    if not target:
        logger.warning(f"[COLLECTE] Cible #{target_id} non trouvée pour user #{current_user.id}")
        raise HTTPException(status_code=404, detail="Cible non trouvée")

    logger.info(f"[COLLECTE] ▶ Début collecte pour '{target.name}' (type={target.target_type.value}, cible #{target.id})")

    # Collecter selon le type
    try:
        if target.target_type.value == "hashtag":
            logger.info(f"[COLLECTE] 🔍 Recherche tweets pour hashtag: {target.query}")
            result = await twitter_service.search_tweets(target.query)
        else:
            username = target.name.lstrip("@")
            logger.info(f"[COLLECTE] 👤 Récupération tweets de @{username}")
            result = await twitter_service.get_user_tweets(target.name)
    except Exception as e:
        logger.error(f"[COLLECTE] ❌ Erreur appel API Twitter pour '{target.name}': {e}")
        raise HTTPException(status_code=500, detail=f"Erreur API Twitter: {str(e)}")

    api_time = time.time() - start_time
    logger.info(f"[COLLECTE] ⏱ Réponse API Twitter en {api_time:.2f}s")

    if "error" in result:
        logger.error(f"[COLLECTE] ❌ Erreur Twitter API: {result['error']} (status={result.get('status', '?')})")
        raise HTTPException(status_code=400, detail=f"Erreur Twitter: {result['error']}")

    # Extraire les tweets (différents formats possibles)
    tweets_data = result.get("tweets", result.get("data", []))

    # Format compte: data.data.tweets (dict imbriqué)
    if isinstance(tweets_data, dict):
        tweets_data = tweets_data.get("tweets", tweets_data.get("results", []))

    # S'assurer que c'est une liste
    if not isinstance(tweets_data, list):
        logger.warning(f"[COLLECTE] ⚠ Format inattendu de la réponse Twitter (type={type(tweets_data).__name__})")
        tweets_data = []

    logger.info(f"[COLLECTE] 📦 {len(tweets_data)} tweets reçus de l'API Twitter")

    if not tweets_data:
        logger.warning(f"[COLLECTE] ⚠ Aucun tweet retourné par l'API pour '{target.name}'")
        return {"message": "Aucun tweet trouvé", "total_fetched": 0, "saved": 0}

    saved_count = 0
    duplicates = 0
    skipped = 0

    for i, tweet_data in enumerate(tweets_data):
        # S'assurer que tweet_data est un dict
        if not isinstance(tweet_data, dict):
            skipped += 1
            continue

        # Vérifier si le tweet existe déjà
        twitter_id = tweet_data.get("id") or tweet_data.get("id_str") or tweet_data.get("tweetId")
        if not twitter_id:
            logger.debug(f"[COLLECTE] ⚠ Tweet #{i+1} ignoré: pas d'ID trouvé")
            skipped += 1
            continue

        existing = db.query(Tweet).filter(Tweet.twitter_id == str(twitter_id)).first()
        if existing:
            duplicates += 1
            continue

        # Extraire le texte (tronquer à 1000 caractères)
        text = tweet_data.get("text") or tweet_data.get("full_text") or tweet_data.get("content", "")
        text = text[:1000] if text else ""

        if not text.strip():
            logger.debug(f"[COLLECTE] ⚠ Tweet {twitter_id} ignoré: texte vide")
            skipped += 1
            continue

        # Extraire l'auteur
        author = tweet_data.get("author", {})
        if isinstance(author, dict):
            author_id = author.get("id")
            author_username = author.get("userName") or author.get("username") or author.get("screen_name")
        else:
            author_id = tweet_data.get("author_id")
            author_username = tweet_data.get("author_username")

        # Créer le tweet
        tweet = Tweet(
            twitter_id=str(twitter_id),
            target_id=target_id,
            text=text,
            author_id=str(author_id) if author_id else None,
            author_username=author_username,
            tweet_created_at=datetime.utcnow()
        )
        db.add(tweet)
        saved_count += 1

        if saved_count <= 3:
            preview = text[:80].replace("\n", " ")
            logger.debug(f"[COLLECTE] 💬 Tweet @{author_username or '?'}: \"{preview}...\"")

    db.commit()

    # Mettre à jour last_tweet_id
    if tweets_data and isinstance(tweets_data[0], dict):
        first_id = tweets_data[0].get("id") or tweets_data[0].get("id_str") or tweets_data[0].get("tweetId")
        if first_id:
            target.last_tweet_id = str(first_id)
            db.commit()

    total_time = time.time() - start_time
    logger.info(
        f"[COLLECTE] ✅ Collecte terminée pour '{target.name}' en {total_time:.2f}s | "
        f"📥 {len(tweets_data)} reçus → 💾 {saved_count} sauvegardés, "
        f"🔄 {duplicates} doublons, ⏭ {skipped} ignorés"
    )

    if duplicates > len(tweets_data) * 0.8:
        logger.warning(
            f"[COLLECTE] ⚠ {duplicates}/{len(tweets_data)} doublons pour '{target.name}' — "
            f"la plupart des tweets sont déjà en base"
        )

    return {
        "message": f"{saved_count} nouveaux tweets collectés",
        "total_fetched": len(tweets_data),
        "saved": saved_count,
        "duplicates": duplicates,
        "skipped": skipped,
        "duration_seconds": round(total_time, 2)
    }


@router.get("/verify/{target_id}")
async def verify_target(
    target_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Vérifie si une cible existe sur Twitter"""
    target = db.query(Target).filter(
        Target.id == target_id,
        Target.user_id == current_user.id
    ).first()
    
    if not target:
        raise HTTPException(status_code=404, detail="Cible non trouvée")
    
    if target.target_type.value == "hashtag":
        exists = await twitter_service.verify_hashtag(target.name)
        return {"exists": exists, "type": "hashtag", "name": target.name}
    else:
        user_info = await twitter_service.get_user_info(target.name)
        if user_info:
            return {
                "exists": True,
                "type": "account",
                "name": target.name,
                "info": user_info
            }
        return {"exists": False, "type": "account", "name": target.name}
