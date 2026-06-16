"""
Agent SentiFlow 

Fonctionnement :
1. Le planner LLM transforme la question en plan JSON.
2. L'agent trouve ou crée les cibles demandées (#hashtag / @compte).
3. Il collecte uniquement si nécessaire : cible nouvelle, aucun tweet, ou demande explicite.
4. Il analyse uniquement les tweets non analysés.
5. Il réutilise les tweets déjà analysés pour répondre vite quand les données existent déjà.
6. Il renvoie une réponse + une configuration de dashboard.
"""

from __future__ import annotations

import logging
import re
import time
import unicodedata
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.app.models.generated_dashboard import GeneratedDashboard
from backend.app.models.target import Target, TargetType
from backend.app.models.tweet import Tweet, VALID_SENTIMENTS
from backend.app.services.llm_from_scratch import get_planner
from backend.app.services.local_llm import ask_local_llm
from backend.app.services.twitter import twitter_service

# Modèle de sentiment existant du projet.
from services.sentiment.model import get_analyzer


logger = logging.getLogger("sentiflow.llm_agent")
logger.setLevel(logging.INFO)


class AgentError(ValueError):
    pass


def normalize_target_value(value: str) -> str:
    return str(value or "").strip().lower().replace(" ", "")


def normalize_without_prefix(value: str) -> str:
    value = normalize_target_value(value)
    return value.lstrip("#@").strip()


def strip_accents(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFD", str(value or ""))
        if unicodedata.category(char) != "Mn"
    )


def normalize_for_target_match(value: str) -> str:
    value = strip_accents(value).lower()
    value = re.sub(r"[^a-z0-9_#@\s-]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def question_tokens_for_target_match(question: str) -> set[str]:
    normalized = normalize_for_target_match(question)
    raw_tokens = re.findall(r"[#@]?[a-z0-9_-]+", normalized)
    tokens = set()

    for token in raw_tokens:
        cleaned = token.strip().lower()
        if not cleaned:
            continue
        tokens.add(cleaned)
        tokens.add(cleaned.lstrip("#@"))

    return tokens




def extract_explicit_targets_from_question(question: str) -> list[str]:
    """
    Extrait les #hashtags et @comptes écrits explicitement par l'utilisateur.
    Ces cibles sont prioritaires sur le planner LLM pour éviter les hallucinations
    du type "#eipstein" compris comme "#psg".
    """
    raw_matches = re.findall(r"[#@][A-Za-z0-9_À-ÿ-]+", question or "")
    seen: set[str] = set()
    result: list[str] = []
    for raw in raw_matches:
        # On garde le texte exact normalisé, sans autocorrection.
        target_type = TargetType.ACCOUNT if raw.startswith("@") else TargetType.HASHTAG
        canonical = canonical_target_name(raw, target_type)
        key = normalize_without_prefix(canonical)
        if key and key not in seen:
            seen.add(key)
            result.append(canonical)
    return result


def plan_target_is_mentioned_in_question(raw_target: str, question: str) -> bool:
    tokens = question_tokens_for_target_match(question)
    normalized = normalize_for_target_match(raw_target).replace(" ", "")
    aliases = {normalized, normalized.lstrip("#@")}
    return bool(aliases.intersection(tokens))


def apply_target_guardrail(plan: dict[str, Any], question: str) -> dict[str, Any]:
    """
    Le LLM peut proposer une mauvaise cible. Règle de sécurité :
    - si l'utilisateur écrit explicitement #x ou @x, on utilise exactement ces cibles ;
    - sinon, on garde uniquement les cibles du plan qui apparaissent vraiment dans la question ;
    - on trace la correction dans plan['target_guardrail'].
    """
    original_targets = list(plan.get("targets", []) or [])
    explicit_targets = extract_explicit_targets_from_question(question)

    if explicit_targets:
        plan["targets"] = explicit_targets
        plan["target_types"] = {
            target: ("account" if target.startswith("@") else "hashtag")
            for target in explicit_targets
        }
        if [normalize_without_prefix(t) for t in explicit_targets] != [normalize_without_prefix(t) for t in original_targets]:
            plan["target_guardrail"] = {
                "status": "overrode_planner_targets_with_explicit_user_targets",
                "planner_targets": original_targets,
                "user_explicit_targets": explicit_targets,
                "reason": "Les cibles écrites avec # ou @ dans la question sont prioritaires sur le LLM.",
            }
        return plan

    if original_targets:
        kept = [target for target in original_targets if plan_target_is_mentioned_in_question(str(target), question)]
        rejected = [target for target in original_targets if target not in kept]
        if rejected:
            plan["target_guardrail"] = {
                "status": "rejected_unmentioned_planner_targets",
                "planner_targets": original_targets,
                "kept_targets": kept,
                "rejected_targets": rejected,
                "reason": "Une cible proposée par le LLM n'était pas présente dans la demande utilisateur.",
            }
        plan["targets"] = kept

    return plan

def target_aliases(target: Target) -> set[str]:
    aliases = set()
    for value in [target.name, target.query]:
        normalized = normalize_for_target_match(value).replace(" ", "")
        if not normalized:
            continue
        aliases.add(normalized)
        aliases.add(normalized.lstrip("#@"))
    return aliases


def find_existing_targets_mentioned_in_question(
    db: Session,
    user_id: int,
    question: str,
) -> list[Target]:

    tokens = question_tokens_for_target_match(question)
    if not tokens:
        return []

    targets = db.query(Target).filter(Target.user_id == user_id).all()
    matched: list[Target] = []

    for target in targets:
        aliases = target_aliases(target)
        if aliases.intersection(tokens):
            matched.append(target)

    return matched


def should_fallback_to_all_targets(question: str) -> bool:
    q = normalize_for_target_match(question)
    return any(
        phrase in q
        for phrase in [
            "toutes les cibles",
            "tous les hashtags",
            "tous les comptes",
            "mes cibles",
            "global",
            "globale",
            "general",
            "generale",
        ]
    )


def infer_target_type(raw_target: str) -> TargetType:
    return TargetType.ACCOUNT if str(raw_target).startswith("@") else TargetType.HASHTAG


def canonical_target_name(raw_target: str, target_type: TargetType | None = None) -> str:
    raw_target = normalize_target_value(raw_target)
    if not raw_target:
        raise AgentError("Cible vide.")

    target_type = target_type or infer_target_type(raw_target)
    name = normalize_without_prefix(raw_target)

    if target_type == TargetType.ACCOUNT:
        return f"@{name}"
    return f"#{name}"


def find_target(db: Session, user_id: int, raw_target: str) -> Target | None:
    normalized = normalize_without_prefix(raw_target)
    candidates = db.query(Target).filter(Target.user_id == user_id).all()
    for target in candidates:
        if normalize_without_prefix(target.name) == normalized:
            return target
        if normalize_without_prefix(target.query) == normalized:
            return target
    return None


def create_target_if_missing(db: Session, user_id: int, raw_target: str) -> tuple[Target, bool]:
    existing = find_target(db, user_id, raw_target)
    if existing:
        return existing, False

    target_type = infer_target_type(raw_target)
    name = canonical_target_name(raw_target, target_type)
    target = Target(
        user_id=user_id,
        name=name,
        target_type=target_type,
        query=name,
    )
    db.add(target)
    db.commit()
    db.refresh(target)
    return target, True


def count_tweets(db: Session, target_id: int) -> dict[str, int]:
    total = db.query(Tweet).filter(Tweet.target_id == target_id).count()
    analyzed = (
        db.query(Tweet)
        .filter(Tweet.target_id == target_id, Tweet.sentiment.isnot(None))
        .count()
    )
    pending = total - analyzed
    return {"total": total, "analyzed": analyzed, "pending": pending}


def _extract_tweets_data(api_result: dict[str, Any]) -> list[dict[str, Any]]:
    tweets_data = api_result.get("tweets", api_result.get("data", []))
    if isinstance(tweets_data, dict):
        tweets_data = tweets_data.get("tweets", tweets_data.get("results", []))
    if not isinstance(tweets_data, list):
        return []
    return [item for item in tweets_data if isinstance(item, dict)]


def _tweet_created_at(tweet_data: dict[str, Any]) -> datetime:
    # L'API utilisée renvoie parfois des formats différents. Pour rester robuste,
    # on stocke au minimum la date de collecte.
    return datetime.utcnow()


async def collect_for_target(db: Session, target: Target) -> dict[str, Any]:
    start = time.time()
    if target.target_type.value == "hashtag":
        api_result = await twitter_service.search_tweets(target.query)
    else:
        api_result = await twitter_service.get_user_tweets(target.name)

    if "error" in api_result:
        raise AgentError(f"Erreur Twitter pour {target.name}: {api_result['error']}")

    tweets_data = _extract_tweets_data(api_result)
    saved = 0
    duplicates = 0
    skipped = 0

    for tweet_data in tweets_data:
        twitter_id = tweet_data.get("id") or tweet_data.get("id_str") or tweet_data.get("tweetId")
        if not twitter_id:
            skipped += 1
            continue

        existing = db.query(Tweet).filter(Tweet.twitter_id == str(twitter_id)).first()
        if existing:
            duplicates += 1
            continue

        text = tweet_data.get("text") or tweet_data.get("full_text") or tweet_data.get("content") or ""
        text = str(text).strip()[:1000]
        if not text:
            skipped += 1
            continue

        author = tweet_data.get("author", {})
        if isinstance(author, dict):
            author_id = author.get("id")
            author_username = author.get("userName") or author.get("username") or author.get("screen_name")
        else:
            author_id = tweet_data.get("author_id")
            author_username = tweet_data.get("author_username")

        tweet = Tweet(
            twitter_id=str(twitter_id),
            target_id=target.id,
            text=text,
            author_id=str(author_id) if author_id else None,
            author_username=author_username,
            tweet_created_at=_tweet_created_at(tweet_data),
        )
        db.add(tweet)
        saved += 1

    if tweets_data:
        first_id = tweets_data[0].get("id") or tweets_data[0].get("id_str") or tweets_data[0].get("tweetId")
        if first_id:
            target.last_tweet_id = str(first_id)

    db.commit()

    return {
        "target_id": target.id,
        "target_name": target.name,
        "total_fetched": len(tweets_data),
        "saved": saved,
        "duplicates": duplicates,
        "skipped": skipped,
        "duration_seconds": round(time.time() - start, 2),
    }


def _clean_text_for_analysis(text: str) -> str:
    clean = re.sub(r"http\S+|www\S+|https\S+", "", text or "")
    clean = re.sub(r"@\w+", "", clean)
    clean = re.sub(r"#\w+", "", clean)
    clean = re.sub(r"[^\w\sÀ-ÿ]", "", clean)
    return clean.strip()


def analyze_pending_tweets(db: Session, target: Target) -> dict[str, Any]:
    start = time.time()
    pending_tweets = (
        db.query(Tweet)
        .filter(Tweet.target_id == target.id, Tweet.sentiment.is_(None))
        .order_by(Tweet.id.desc())
        .all()
    )

    if not pending_tweets:
        return {
            "target_id": target.id,
            "target_name": target.name,
            "analyzed": 0,
            "total_pending_before": 0,
            "message": "Aucun nouveau tweet à analyser",
            "duration_seconds": 0,
        }

    analyzer = get_analyzer()
    analyzed = 0
    errors = 0
    too_short = 0
    sentiment_distribution = {sentiment: 0 for sentiment in VALID_SENTIMENTS}
    sentiment_distribution["neutre"] = 0

    for tweet in pending_tweets:
        try:
            clean = _clean_text_for_analysis(tweet.text)
            if len(clean) < 10:
                tweet.sentiment = "neutre"
                tweet.confidence = 0.5
                tweet.sentiment_scores = {"neutre": 0.5}
                tweet.analyzed_at = datetime.utcnow()
                too_short += 1
                analyzed += 1
                sentiment_distribution["neutre"] += 1
                continue

            scores = analyzer.predict(tweet.text)
            dominant, confidence = analyzer.get_dominant_sentiment(scores)
            tweet.sentiment_scores = scores
            tweet.confidence = confidence
            tweet.sentiment = dominant
            tweet.analyzed_at = datetime.utcnow()
            analyzed += 1
            sentiment_distribution[dominant] = sentiment_distribution.get(dominant, 0) + 1
        except Exception as exc:  
            errors += 1
            logger.exception("Erreur analyse tweet #%s: %s", tweet.id, exc)

    db.commit()

    return {
        "target_id": target.id,
        "target_name": target.name,
        "analyzed": analyzed,
        "total_pending_before": len(pending_tweets),
        "errors": errors,
        "too_short_marked_neutral": too_short,
        "sentiment_distribution": sentiment_distribution,
        "duration_seconds": round(time.time() - start, 2),
    }



def save_generated_dashboard(
    db: Session,
    user_id: int,
    question: str,
    answer: str,
    target_ids: list[int],
    dashboard_config: dict[str, Any] | None,
    plan: dict[str, Any],
) -> GeneratedDashboard | None:

    if not dashboard_config:
        return None

    title = dashboard_config.get("title") or "Dashboard généré par le LLM"
    source_question = dashboard_config.get("source_question") or question

    enriched_config = {
        **dashboard_config,
        "source_question": source_question,
        "target_ids": target_ids,
        "saved_at": datetime.utcnow().isoformat(),
    }

    dashboard = GeneratedDashboard(
        user_id=user_id,
        title=str(title)[:255],
        question=question,
        answer=answer,
        target_ids=target_ids,
        config_json=enriched_config,
        plan_json=plan,
    )
    db.add(dashboard)
    db.commit()
    db.refresh(dashboard)
    return dashboard


def _format_execution_summary(execution_log: list[dict[str, Any]]) -> str:
    lines = []
    for step in execution_log:
        action = step.get("action")
        target = step.get("target")
        if action == "create_target":
            lines.append(f"- cible {target} créée")
        elif action == "reuse_target":
            lines.append(f"- cible {target} déjà existante")
        elif action == "collect_tweets":
            lines.append(
                f"- collecte {target}: {step.get('saved', 0)} nouveaux tweets, "
                f"{step.get('duplicates', 0)} doublons"
            )
        elif action == "skip_collect":
            lines.append(f"- collecte {target}: non relancée, données déjà disponibles")
        elif action == "analyze_sentiments":
            lines.append(f"- analyse {target}: {step.get('analyzed', 0)} tweets analysés")
        elif action == "skip_analyze":
            lines.append(f"- analyse {target}: rien de nouveau à analyser")
    return "\n".join(lines)


async def run_sentiflow_agent(
    db: Session,
    user_id: int,
    question: str,
    days: int | None = None,
    generate_dashboard: bool | None = None,
    force_refresh: bool | None = None,
    allow_auto_collect: bool = True,
    allow_auto_analyze: bool = True,
    feedback_context: str | None = None,
) -> dict[str, Any]:
    planner = get_planner()
    plan = planner.plan(question)
    plan = apply_target_guardrail(plan, question)

    if days is not None:
        plan["days"] = max(1, min(90, int(days)))
    if generate_dashboard is not None:
        plan["dashboard"] = bool(generate_dashboard)
        if generate_dashboard and "generate_dashboard" not in plan["actions"]:
            plan["actions"].append("generate_dashboard")
    if force_refresh is not None:
        plan["force_refresh"] = bool(force_refresh)

    requested_targets = plan.get("targets", []) or []
    execution_log: list[dict[str, Any]] = []
    selected_targets: list[Target] = []


    if not requested_targets:
        matched_targets = find_existing_targets_mentioned_in_question(db, user_id, question)
        if matched_targets:
            requested_targets = [target.name for target in matched_targets]
            plan["targets"] = requested_targets
            plan["target_types"] = {
                target.name: target.target_type.value
                if hasattr(target.target_type, "value")
                else str(target.target_type)
                for target in matched_targets
            }
            plan["planner_source"] = f"{plan.get('planner_source', 'unknown')}+db_target_match"

    if requested_targets:
        for raw_target in requested_targets:
            target, created = create_target_if_missing(db, user_id, raw_target)
            selected_targets.append(target)
            execution_log.append({
                "action": "create_target" if created else "reuse_target",
                "target": target.name,
                "target_id": target.id,
            })
    else:
        selected_targets = db.query(Target).filter(Target.user_id == user_id).all()
        if not selected_targets:
            raise AgentError(
                "Je n'ai trouvé aucune cible. Demande par exemple : récupère les tweets avec #france."
            )


        if not should_fallback_to_all_targets(question):
            names = ", ".join(target.name for target in selected_targets[:8])
            raise AgentError(
                "Je n'ai pas identifié la cible à analyser. "
                f"Précise un hashtag ou un compte, par exemple : {names}."
            )

        for target in selected_targets:
            execution_log.append({"action": "reuse_target", "target": target.name, "target_id": target.id})


    seen_ids = set()
    unique_targets = []
    for target in selected_targets:
        if target.id not in seen_ids:
            seen_ids.add(target.id)
            unique_targets.append(target)
    selected_targets = unique_targets

    for target in selected_targets:
        before = count_tweets(db, target.id)
        should_collect = (
            allow_auto_collect
            and (
                before["total"] == 0
                or plan.get("force_refresh", False)
            )
        )

        if should_collect:
            collect_result = await collect_for_target(db, target)
            collect_result["action"] = "collect_tweets"
            collect_result["target"] = target.name
            execution_log.append(collect_result)
        else:
            execution_log.append({
                "action": "skip_collect",
                "target": target.name,
                "target_id": target.id,
                "reason": "tweets déjà présents ou collecte non demandée",
            })

        after_collect = count_tweets(db, target.id)
        should_analyze = allow_auto_analyze and after_collect["pending"] > 0

        if should_analyze:
            analyze_result = analyze_pending_tweets(db, target)
            analyze_result["action"] = "analyze_sentiments"
            analyze_result["target"] = target.name
            execution_log.append(analyze_result)
        else:
            execution_log.append({
                "action": "skip_analyze",
                "target": target.name,
                "target_id": target.id,
                "reason": "aucun tweet non analysé",
            })

    target_ids = [target.id for target in selected_targets]
    local_result = ask_local_llm(
        db=db,
        user_id=user_id,
        question=question,
        target_ids=target_ids,
        days=plan.get("days", 7),
        generate_dashboard=bool(plan.get("dashboard", True)),
        intent_override=plan.get("intent"),
        sentiment_filter_override=plan.get("sentiment_filter"),
        planner_actions=plan.get("actions", []),
        feedback_context=feedback_context,
    )

    summary = _format_execution_summary(execution_log)
    answer = local_result.get("answer", "")
    if summary:
        answer = f"Actions effectuées :\n{summary}\n\n{answer}"

    saved_dashboard = save_generated_dashboard(
        db=db,
        user_id=user_id,
        question=question,
        answer=answer,
        target_ids=target_ids,
        dashboard_config=local_result.get("dashboard_config"),
        plan=plan,
    )

    if saved_dashboard and local_result.get("dashboard_config"):
        local_result["dashboard_config"] = {
            **local_result["dashboard_config"],
            "saved_dashboard_id": saved_dashboard.id,
            "dashboard_url": f"/dashboards/generated/{saved_dashboard.id}",
        }

    return {
        **local_result,
        "answer": answer,
        "plan": plan,
        "execution_log": execution_log,
        "model_info": planner.model_info(),
        "dashboard_id": saved_dashboard.id if saved_dashboard else None,
        "dashboard_url": f"/dashboards/generated/{saved_dashboard.id}" if saved_dashboard else None,
    }
