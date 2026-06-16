"""
MCP Server FROM SCRATCH pour SentiFlow.

Model Context Protocol (MCP) : le LLM/RAG peut appeler des outils
pour interagir avec le monde extérieur (Twitter, analyse, etc.)

Outils exposés :
- search_twitter(query, limit) → tweets en temps réel
- analyze_sentiment(text) → sentiment + scores
- search_and_analyze(query, limit) → tweets + sentiment en une seule étape
- get_user_tweets(username, limit) → tweets d'un compte

Le RAG utilise ces outils quand la BDD n'a pas assez de données.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("sentiflow.mcp")


# ============================================
# DÉFINITION DES OUTILS MCP
# ============================================

MCP_TOOLS = {
    "search_twitter": {
        "name": "search_twitter",
        "description": "Recherche des tweets en temps réel sur Twitter par hashtag ou mot-clé",
        "parameters": {
            "query": {"type": "string", "description": "Hashtag ou mot-clé à chercher (ex: #france, @elonmusk)"},
            "limit": {"type": "integer", "description": "Nombre max de tweets (défaut: 20)", "default": 20},
        },
        "required": ["query"],
    },
    "analyze_sentiment": {
        "name": "analyze_sentiment",
        "description": "Analyse le sentiment d'un texte avec le modèle ML SentiFlow",
        "parameters": {
            "text": {"type": "string", "description": "Texte à analyser"},
        },
        "required": ["text"],
    },
    "search_and_analyze": {
        "name": "search_and_analyze",
        "description": "Recherche des tweets ET analyse leurs sentiments en une seule étape. Outil principal du RAG.",
        "parameters": {
            "query": {"type": "string", "description": "Hashtag ou mot-clé"},
            "limit": {"type": "integer", "description": "Nombre max de tweets", "default": 20},
        },
        "required": ["query"],
    },
    "get_user_tweets": {
        "name": "get_user_tweets",
        "description": "Récupère les derniers tweets d'un utilisateur Twitter",
        "parameters": {
            "username": {"type": "string", "description": "Nom d'utilisateur (avec ou sans @)"},
            "limit": {"type": "integer", "description": "Nombre max de tweets", "default": 20},
        },
        "required": ["username"],
    },
    "query_database": {
        "name": "query_database",
        "description": "Interroge la base de données SentiFlow pour obtenir des infos sur les cibles, tweets stockés, stats",
        "parameters": {
            "query_type": {"type": "string", "description": "Type de requête: targets, tweet_count, sentiment_stats, languages"},
        },
        "required": ["query_type"],
    },
}


# ============================================
# EXÉCUTION DES OUTILS MCP
# ============================================

async def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Exécute un outil MCP et retourne le résultat.
    Point d'entrée principal pour le RAG.
    """
    start = time.time()
    logger.info(f"[MCP] Exécution outil '{tool_name}' avec args={arguments}")

    if tool_name not in MCP_TOOLS:
        return {"error": f"Outil inconnu: {tool_name}", "available_tools": list(MCP_TOOLS.keys())}

    try:
        if tool_name == "search_twitter":
            result = await _tool_search_twitter(
                query=arguments["query"],
                limit=arguments.get("limit", 20),
            )
        elif tool_name == "analyze_sentiment":
            result = _tool_analyze_sentiment(text=arguments["text"])
        elif tool_name == "search_and_analyze":
            result = await _tool_search_and_analyze(
                query=arguments["query"],
                limit=arguments.get("limit", 20),
            )
        elif tool_name == "get_user_tweets":
            result = await _tool_get_user_tweets(
                username=arguments["username"],
                limit=arguments.get("limit", 20),
            )
        elif tool_name == "query_database":
            result = _tool_query_database(
                query_type=arguments.get("query_type", "targets"),
            )
        else:
            result = {"error": f"Outil '{tool_name}' non implémenté"}

        elapsed = time.time() - start
        result["_mcp_meta"] = {
            "tool": tool_name,
            "duration_seconds": round(elapsed, 2),
            "timestamp": datetime.utcnow().isoformat(),
        }
        logger.info(f"[MCP] '{tool_name}' terminé en {elapsed:.2f}s")
        return result

    except Exception as e:
        logger.error(f"[MCP] Erreur '{tool_name}': {e}")
        return {"error": str(e), "tool": tool_name}


# ============================================
# IMPLÉMENTATION DES OUTILS
# ============================================

async def _tool_search_twitter(query: str, limit: int = 20) -> Dict[str, Any]:
    """Recherche des tweets en temps réel via l'API Twitter."""
    from backend.app.services.twitter import twitter_service

    # Déterminer si c'est un hashtag ou un compte
    query_clean = query.strip()
    if query_clean.startswith("@"):
        api_result = await twitter_service.get_user_tweets(query_clean)
    else:
        api_result = await twitter_service.search_tweets(query_clean)

    if "error" in api_result:
        return {"error": api_result["error"], "query": query_clean, "tweets": []}

    # Extraire les tweets
    raw_tweets = _extract_tweets_from_api(api_result)

    # Formater pour le RAG
    tweets = []
    for t in raw_tweets[:limit]:
        text = t.get("text") or t.get("full_text") or t.get("content") or ""
        text = str(text).strip()[:1000]
        if not text:
            continue

        author = t.get("author", {})
        if isinstance(author, dict):
            author_username = author.get("userName") or author.get("username") or author.get("screen_name") or "?"
        else:
            author_username = t.get("author_username") or "?"

        tweets.append({
            "twitter_id": t.get("id") or t.get("id_str") or t.get("tweetId"),
            "text": text,
            "author": author_username,
            "created_at": t.get("createdAt") or t.get("created_at"),
        })

    return {
        "query": query_clean,
        "total_fetched": len(tweets),
        "tweets": tweets,
    }


def _tool_analyze_sentiment(text: str) -> Dict[str, Any]:
    """Analyse le sentiment d'un texte unique."""
    from services.sentiment.model import get_analyzer

    analyzer = get_analyzer()
    scores = analyzer.predict(text)
    dominant, confidence = analyzer.get_dominant_sentiment(scores)

    return {
        "text": text[:200],
        "sentiment": dominant,
        "confidence": round(confidence, 4),
        "scores": scores,
    }


async def _tool_search_and_analyze(query: str, limit: int = 20) -> Dict[str, Any]:
    """
    Outil combiné : recherche Twitter + analyse sentiment.
    C'est l'outil principal utilisé par le RAG pour enrichir ses données.
    """
    # 1. Chercher sur Twitter
    search_result = await _tool_search_twitter(query, limit)

    if "error" in search_result and not search_result.get("tweets"):
        return search_result

    tweets = search_result.get("tweets", [])
    if not tweets:
        return {
            "query": query,
            "total_analyzed": 0,
            "tweets": [],
            "message": "Aucun tweet trouvé pour cette requête",
        }

    # 2. Analyser les sentiments
    from services.sentiment.model import get_analyzer
    analyzer = get_analyzer()

    analyzed_tweets = []
    sentiment_counts: Dict[str, int] = {}

    for tweet in tweets:
        text = tweet.get("text", "")
        if len(text.strip()) < 10:
            continue

        scores = analyzer.predict(text)
        dominant, confidence = analyzer.get_dominant_sentiment(scores)

        analyzed_tweets.append({
            "id": tweet.get("twitter_id"),
            "text": text,
            "author": tweet.get("author", "?"),
            "sentiment": dominant,
            "confidence": round(confidence, 4),
            "scores": scores,
            "created_at": tweet.get("created_at"),
            "target": query,
        })

        sentiment_counts[dominant] = sentiment_counts.get(dominant, 0) + 1

    # 3. Résumé statistique
    total = len(analyzed_tweets)
    distribution = {k: round(v / total, 4) for k, v in sentiment_counts.items()} if total > 0 else {}

    return {
        "query": query,
        "total_analyzed": total,
        "sentiment_distribution": distribution,
        "dominant_sentiment": max(sentiment_counts, key=sentiment_counts.get) if sentiment_counts else None,
        "tweets": analyzed_tweets,
    }


async def _tool_get_user_tweets(username: str, limit: int = 20) -> Dict[str, Any]:
    """Récupère les tweets d'un utilisateur."""
    from backend.app.services.twitter import twitter_service

    username = username.lstrip("@")
    api_result = await twitter_service.get_user_tweets(username)

    if "error" in api_result:
        return {"error": api_result["error"], "username": username, "tweets": []}

    raw_tweets = _extract_tweets_from_api(api_result)
    tweets = []
    for t in raw_tweets[:limit]:
        text = t.get("text") or t.get("full_text") or t.get("content") or ""
        tweets.append({
            "twitter_id": t.get("id") or t.get("id_str") or t.get("tweetId"),
            "text": str(text).strip()[:1000],
            "author": username,
            "created_at": t.get("createdAt") or t.get("created_at"),
        })

    return {
        "username": username,
        "total_fetched": len(tweets),
        "tweets": tweets,
    }


# ============================================
# UTILITAIRES
# ============================================

def _extract_tweets_from_api(api_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extrait les tweets depuis la réponse API (différents formats possibles)."""
    tweets_data = api_result.get("tweets", api_result.get("data", []))
    if isinstance(tweets_data, dict):
        tweets_data = tweets_data.get("tweets", tweets_data.get("results", []))
    if not isinstance(tweets_data, list):
        return []
    return [item for item in tweets_data if isinstance(item, dict)]


def _tool_query_database(query_type: str = "targets") -> Dict[str, Any]:
    """Interroge la BDD SentiFlow pour obtenir des infos sur les données stockées."""
    from backend.app.database import SessionLocal
    from backend.app.models.tweet import Tweet
    from backend.app.models.target import Target

    db = SessionLocal()
    try:
        if query_type == "targets":
            targets = db.query(Target).all()
            target_info = []
            for t in targets:
                count = db.query(Tweet).filter(Tweet.target_id == t.id).count()
                analyzed = db.query(Tweet).filter(
                    Tweet.target_id == t.id, Tweet.sentiment.isnot(None)
                ).count()
                target_info.append({
                    "name": t.name,
                    "type": str(t.target_type.value) if hasattr(t.target_type, "value") else str(t.target_type),
                    "total_tweets": count,
                    "analyzed_tweets": analyzed,
                })
            return {
                "query_type": "targets",
                "total_targets": len(targets),
                "targets": target_info,
                "summary": f"{len(targets)} cibles suivies, {sum(t['total_tweets'] for t in target_info)} tweets au total",
            }

        elif query_type == "tweet_count":
            total = db.query(Tweet).count()
            analyzed = db.query(Tweet).filter(Tweet.sentiment.isnot(None)).count()
            return {
                "query_type": "tweet_count",
                "total": total,
                "analyzed": analyzed,
                "pending": total - analyzed,
            }

        elif query_type == "sentiment_stats":
            from sqlalchemy import func
            stats = (
                db.query(Tweet.sentiment, func.count(Tweet.id))
                .filter(Tweet.sentiment.isnot(None))
                .group_by(Tweet.sentiment)
                .all()
            )
            total = sum(count for _, count in stats)
            return {
                "query_type": "sentiment_stats",
                "distribution": {sent: count for sent, count in stats},
                "total_analyzed": total,
                "percentages": {sent: f"{count/total:.0%}" for sent, count in stats} if total > 0 else {},
            }

        elif query_type == "languages":
            # Détection simple de langue basée sur les caractères
            tweets = db.query(Tweet.text).filter(Tweet.sentiment.isnot(None)).limit(500).all()
            import re
            lang_counts = {"français": 0, "anglais": 0, "coréen": 0, "autre": 0}
            for (text,) in tweets:
                if not text:
                    continue
                if re.search(r"[\uac00-\ud7af]", text):
                    lang_counts["coréen"] += 1
                elif re.search(r"[àâäçéèêëîïôöùûüÿœæ]", text.lower()):
                    lang_counts["français"] += 1
                elif re.search(r"[a-zA-Z]", text):
                    lang_counts["anglais"] += 1
                else:
                    lang_counts["autre"] += 1
            total = sum(lang_counts.values())
            return {
                "query_type": "languages",
                "distribution": {k: v for k, v in lang_counts.items() if v > 0},
                "total_analyzed": total,
                "percentages": {k: f"{v/total:.0%}" for k, v in lang_counts.items() if v > 0} if total > 0 else {},
            }

        elif query_type == "anger_by_target":
            # Colère par cible
            from sqlalchemy import func
            stats = (
                db.query(Target.name, func.count(Tweet.id))
                .join(Tweet, Tweet.target_id == Target.id)
                .filter(Tweet.sentiment.in_(["colere", "tristesse", "peur"]))
                .group_by(Target.name)
                .order_by(func.count(Tweet.id).desc())
                .all()
            )
            return {
                "query_type": "anger_by_target",
                "results": [{"target": name, "negative_tweets": count} for name, count in stats],
                "summary": f"Cibles avec le plus de tweets négatifs : {', '.join(f'{n} ({c})' for n, c in stats[:5])}",
            }

        else:
            return {"error": f"query_type '{query_type}' non supporté. Utilisez: targets, tweet_count, sentiment_stats, languages"}

    finally:
        db.close()


def list_tools() -> List[Dict[str, Any]]:
    """Liste tous les outils MCP disponibles."""
    return list(MCP_TOOLS.values())


def get_tool_schema(tool_name: str) -> Optional[Dict[str, Any]]:
    """Retourne le schéma d'un outil spécifique."""
    return MCP_TOOLS.get(tool_name)
