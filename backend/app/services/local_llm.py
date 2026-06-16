
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.models.target import Target
from backend.app.models.tweet import Tweet, VALID_SENTIMENTS


DISPLAY_SENTIMENTS = [*VALID_SENTIMENTS, "neutre"]

SENTIMENT_LABELS = {
    "joie": "joie",
    "amour": "amour",
    "surprise": "surprise",
    "neutre": "neutre",
    "peur": "peur",
    "tristesse": "tristesse",
    "colere": "colère",
}

SENTIMENT_WEIGHTS = {
    "joie": 1.0,
    "amour": 0.85,
    "surprise": 0.15,
    "neutre": 0.0,
    "peur": -0.55,
    "tristesse": -0.75,
    "colere": -1.0,
}

NEGATIVE_SENTIMENTS = {"colere", "tristesse", "peur"}
POSITIVE_SENTIMENTS = {"joie", "amour"}

STOPWORDS = {
    "avec", "alors", "apres", "après", "avoir", "avant", "aussi", "autre",
    "aux", "auxquels", "auxquelles", "bien", "bon", "car", "cela", "ces",
    "cet", "cette", "chez", "comme", "comment", "dans", "des", "donc",
    "dont", "elle", "elles", "encore", "entre", "est", "ete", "été", "etre",
    "être", "fait", "faire", "faut", "ici", "ils", "les", "leur", "leurs",
    "mais", "mes", "meme", "même", "mon", "nous", "pas", "plus", "pour",
    "pourquoi", "quand", "que", "quel", "quelle", "qui", "quoi", "sans",
    "ses", "son", "sont", "sur", "tes", "toi", "ton", "tous", "tout", "tres",
    "très", "une", "vos", "votre", "vous",
    "about", "after", "again", "also", "and", "are", "because", "been", "but",
    "can", "cant", "could", "dont", "from", "have", "here", "https", "into",
    "just", "like", "more", "not", "now", "only", "that", "the", "their",
    "them", "then", "there", "this", "with", "you", "your", "tweet", "tweets",
    "twitter", "rt", "amp",
}


def normalize_text(text: str) -> str:
    text = str(text or "").lower()
    text = "".join(
        char for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )
    return text


def tokenize(text: str) -> list[str]:
    text = normalize_text(text)
    return re.findall(r"[a-z0-9_#@]+", text)


class TinyIntentModel:
    """
    Petit classifieur local pour le mode /llm/ask historique.
    En mode agent, le planner peut fournir une intention déjà décidée.
    """

    def __init__(self):
        self.intent_word_counts = defaultdict(Counter)
        self.intent_counts = Counter()
        self.vocab = set()
        self.total_examples = 0

    def fit(self, examples: list[tuple[str, str]]) -> None:
        for text, intent in examples:
            tokens = tokenize(text)
            self.intent_counts[intent] += 1
            self.total_examples += 1

            for token in tokens:
                self.intent_word_counts[intent][token] += 1
                self.vocab.add(token)

    def predict(self, question: str) -> tuple[str, float]:
        tokens = tokenize(question)
        if not tokens or not self.total_examples:
            return "summary", 0.0

        best_intent = "summary"
        best_score = -10**9
        scores = {}
        vocab_size = max(len(self.vocab), 1)

        for intent in self.intent_counts:
            prior = math.log(self.intent_counts[intent] / self.total_examples)
            total_words = sum(self.intent_word_counts[intent].values())
            score = prior

            for token in tokens:
                count = self.intent_word_counts[intent][token]
                proba = (count + 1) / (total_words + vocab_size)
                score += math.log(proba)

            scores[intent] = score
            if score > best_score:
                best_score = score
                best_intent = intent

        sorted_scores = sorted(scores.values(), reverse=True)
        if len(sorted_scores) >= 2:
            confidence = min(1.0, max(0.0, sorted_scores[0] - sorted_scores[1]))
        else:
            confidence = 1.0

        return best_intent, round(confidence, 3)


TRAINING_EXAMPLES = [
    ("résume l'activité de ce compte", "summary"),
    ("quel est le sentiment dominant", "summary"),
    ("comment les gens réagissent", "summary"),
    ("donne moi une synthèse", "summary"),
    ("résumé des sentiments", "summary"),
    ("analyse en profondeur ce hashtag", "summary"),
    ("donne une lecture détaillée des résultats", "summary"),
    ("quels sont les signaux importants", "summary"),

    ("compare ces hashtags", "comparison"),
    ("comparaison entre ces comptes", "comparison"),
    ("lequel est le plus positif", "comparison"),
    ("qui a le plus de colère", "comparison"),
    ("compare les sentiments", "comparison"),
    ("quelle cible est la plus négative", "comparison"),

    ("évolution temporelle des sentiments", "timeline"),
    ("comment ça évolue dans le temps", "timeline"),
    ("tendance sur les derniers jours", "timeline"),
    ("est-ce que la joie augmente", "timeline"),
    ("analyse temporelle", "timeline"),
    ("est-ce que la colère baisse", "timeline"),

    ("génère un dashboard", "dashboard"),
    ("fais moi un dashboard", "dashboard"),
    ("je veux des graphiques", "dashboard"),
    ("prépare une visualisation", "dashboard"),

    ("montre des exemples de tweets négatifs", "examples"),
    ("donne des tweets représentatifs", "examples"),
    ("exemples de tweets joyeux", "examples"),
    ("tweets les plus tristes", "examples"),
    ("quels tweets expliquent ce sentiment", "examples"),
]

INTENT_MODEL = TinyIntentModel()
INTENT_MODEL.fit(TRAINING_EXAMPLES)


def canonical_intent(intent: str | None, actions: list[str] | None = None) -> str:
    raw = normalize_text(intent or "")
    actions = actions or []

    if raw in {"compare", "comparison", "compare_targets"} or "compare_targets" in actions:
        return "comparison"
    if raw in {"timeline", "temporal", "get_timeline"} or "get_timeline" in actions:
        return "timeline"
    if raw in {"dashboard", "generate_dashboard"}:
        return "dashboard"
    if raw in {"examples", "collect_analyze_examples", "get_examples"} or "get_examples" in actions:
        return "examples"
    return "summary"


def extract_days(question: str, default_days: int = 7) -> int:
    q = normalize_text(question)

    match = re.search(r"(\d+)\s*(jour|jours|j|day|days)", q)
    if match:
        return max(1, min(90, int(match.group(1))))
    if "mois" in q:
        return 30
    if "semaine" in q:
        return 7
    if "hier" in q or "24h" in q:
        return 1
    return default_days


def detect_sentiment_filter(question: str) -> str | None:
    question = re.sub(r"[#@][A-Za-z0-9_À-ÿ-]+", " ", question or "")
    q = normalize_text(question)

    aliases = {
        "joie": ["joie", "joyeux", "positif", "positive", "heureux"],
        "tristesse": ["tristesse", "triste", "negatif", "negative", "decu", "déçu"],
        "colere": ["colere", "colère", "rage", "enerve", "énervé", "haine"],
        "peur": ["peur", "inquiet", "inquiétude", "anxiete", "angoisse"],
        "surprise": ["surprise", "etonne", "étonné", "wow"],
        "neutre": ["neutre", "neutral"],
        "amour": ["amour", "love", "coeur"],
    }

    for sentiment, words in aliases.items():
        if any(normalize_text(word) in q for word in words):
            return sentiment
    return None


def get_user_targets(db: Session, user_id: int, target_ids: list[int]) -> list[Target]:
    targets = (
        db.query(Target)
        .filter(Target.user_id == user_id, Target.id.in_(target_ids))
        .all()
    )

    by_id = {target.id: target for target in targets}
    missing_ids = [target_id for target_id in target_ids if target_id not in by_id]
    if missing_ids:
        raise ValueError(f"Cibles introuvables ou non autorisées : {missing_ids}")

    return [by_id[target_id] for target_id in target_ids]


def pct(value: float | int | None) -> str:
    return f"{float(value or 0):.0%}"


def signed_pct(value: float | int | None) -> str:
    value = float(value or 0)
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.0%}"


def score_label(score: float) -> str:
    if score >= 0.35:
        return "clairement positif"
    if score >= 0.12:
        return "plutôt positif"
    if score <= -0.35:
        return "clairement négatif"
    if score <= -0.12:
        return "plutôt négatif"
    return "assez neutre / partagé"


def trend_label(delta: float) -> str:
    if delta >= 0.12:
        return "amélioration nette"
    if delta >= 0.04:
        return "légère amélioration"
    if delta <= -0.12:
        return "dégradation nette"
    if delta <= -0.04:
        return "légère dégradation"
    return "stable"


def empty_sentiment_counts() -> dict[str, int]:
    return {sentiment: 0 for sentiment in DISPLAY_SENTIMENTS}


def distribution_from_counts(counts: dict[str, int], total: int | None = None) -> dict[str, float]:
    total = int(total if total is not None else sum(counts.values()))
    if total <= 0:
        return {sentiment: 0.0 for sentiment in counts}
    return {sentiment: round(count / total, 4) for sentiment, count in counts.items()}


def net_score_from_counts(counts: dict[str, int]) -> float:
    total = sum(counts.values())
    if total <= 0:
        return 0.0
    score = sum(SENTIMENT_WEIGHTS.get(sentiment, 0.0) * count for sentiment, count in counts.items()) / total
    return round(score, 4)


def top_two_sentiments(counts: dict[str, int]) -> tuple[tuple[str | None, int], tuple[str | None, int]]:
    ordered = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    first = ordered[0] if ordered else (None, 0)
    second = ordered[1] if len(ordered) > 1 else (None, 0)
    return first, second


def clean_text_for_keywords(text: str) -> list[str]:
    text = normalize_text(text)
    text = re.sub(r"https?://\S+|www\.\S+", " ", text)
    text = re.sub(r"[@#]", " ", text)
    words = re.findall(r"[a-z0-9_]{3,}", text)
    return [word for word in words if word not in STOPWORDS and not word.isdigit()]


def extract_keywords(tweets: list[Tweet], limit: int = 8) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for tweet in tweets:
        counter.update(clean_text_for_keywords(tweet.text or ""))
    return [
        {"term": term, "count": count}
        for term, count in counter.most_common(limit)
        if count > 1 or len(counter) <= 5
    ]


def build_period_counts(tweets: list[Tweet], start: datetime, end: datetime) -> dict[str, int]:
    counts = empty_sentiment_counts()
    for tweet in tweets:
        analyzed_at = tweet.analyzed_at or tweet.tweet_created_at
        if not analyzed_at or analyzed_at < start or analyzed_at >= end:
            continue
        sentiment = tweet.sentiment or "neutre"
        counts[sentiment] = counts.get(sentiment, 0) + 1
    return counts


def compute_target_stats(db: Session, target: Target, since: datetime, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.utcnow()
    tweets = (
        db.query(Tweet)
        .filter(
            Tweet.target_id == target.id,
            Tweet.sentiment.isnot(None),
            Tweet.analyzed_at >= since,
        )
        .order_by(Tweet.analyzed_at.asc())
        .all()
    )

    total = len(tweets)
    sentiment_counts = empty_sentiment_counts()
    confidence_sum = 0.0
    confidence_count = 0
    confidence_buckets = {"high": 0, "medium": 0, "low": 0}

    for tweet in tweets:
        sentiment = tweet.sentiment or "neutre"
        sentiment_counts[sentiment] = sentiment_counts.get(sentiment, 0) + 1
        if tweet.confidence is not None:
            confidence = float(tweet.confidence)
            confidence_sum += confidence
            confidence_count += 1
            if confidence >= 0.75:
                confidence_buckets["high"] += 1
            elif confidence >= 0.55:
                confidence_buckets["medium"] += 1
            else:
                confidence_buckets["low"] += 1

    sentiment_distribution = distribution_from_counts(sentiment_counts, total)
    (dominant_sentiment, dominant_count), (second_sentiment, second_count) = top_two_sentiments(sentiment_counts)
    dominant_margin = round(((dominant_count or 0) - (second_count or 0)) / total, 4) if total else 0.0
    avg_confidence = round(confidence_sum / confidence_count, 4) if confidence_count else 0.0
    low_conf_rate = round(confidence_buckets["low"] / confidence_count, 4) if confidence_count else 0.0
    net_score = net_score_from_counts(sentiment_counts)

    negative_count = sum(sentiment_counts.get(sentiment, 0) for sentiment in NEGATIVE_SENTIMENTS)
    positive_count = sum(sentiment_counts.get(sentiment, 0) for sentiment in POSITIVE_SENTIMENTS)

    midpoint = since + (now - since) / 2
    first_counts = build_period_counts(tweets, since, midpoint)
    second_counts = build_period_counts(tweets, midpoint, now + timedelta(seconds=1))
    first_score = net_score_from_counts(first_counts)
    second_score = net_score_from_counts(second_counts)

    trend = {
        "first_half_total": sum(first_counts.values()),
        "second_half_total": sum(second_counts.values()),
        "first_half_score": first_score,
        "second_half_score": second_score,
        "score_delta": round(second_score - first_score, 4),
        "label": trend_label(second_score - first_score),
        "volume_delta": sum(second_counts.values()) - sum(first_counts.values()),
        "negative_delta": round(
            sum(second_counts.get(s, 0) for s in NEGATIVE_SENTIMENTS) / max(sum(second_counts.values()), 1)
            - sum(first_counts.get(s, 0) for s in NEGATIVE_SENTIMENTS) / max(sum(first_counts.values()), 1),
            4,
        ),
        "positive_delta": round(
            sum(second_counts.get(s, 0) for s in POSITIVE_SENTIMENTS) / max(sum(second_counts.values()), 1)
            - sum(first_counts.get(s, 0) for s in POSITIVE_SENTIMENTS) / max(sum(first_counts.values()), 1),
            4,
        ),
    }

    quality_notes = []
    if total < 15:
        quality_notes.append("échantillon faible")
    elif total < 40:
        quality_notes.append("échantillon moyen")
    else:
        quality_notes.append("échantillon correct")
    if avg_confidence and avg_confidence < 0.6:
        quality_notes.append("confiance modèle faible")
    elif avg_confidence >= 0.75:
        quality_notes.append("confiance modèle élevée")
    if dominant_margin < 0.12 and total > 0:
        quality_notes.append("sentiments assez partagés")

    return {
        "target_id": target.id,
        "target_name": target.name,
        "target_type": str(target.target_type.value if hasattr(target.target_type, "value") else target.target_type),
        "total_tweets": total,
        "dominant_sentiment": dominant_sentiment,
        "dominant_count": dominant_count,
        "second_sentiment": second_sentiment,
        "second_count": second_count,
        "dominant_margin": dominant_margin,
        "sentiment_counts": sentiment_counts,
        "sentiment_distribution": sentiment_distribution,
        "positive_ratio": round(positive_count / total, 4) if total else 0.0,
        "negative_ratio": round(negative_count / total, 4) if total else 0.0,
        "average_confidence": avg_confidence,
        "confidence_buckets": confidence_buckets,
        "low_confidence_rate": low_conf_rate,
        "net_sentiment_score": net_score,
        "net_sentiment_label": score_label(net_score),
        "trend": trend,
        "keywords": extract_keywords(tweets, limit=8),
        "quality_notes": quality_notes,
    }


def compute_timeline(db: Session, target: Target, since: datetime) -> list[dict[str, Any]]:
    day_expr = func.date(Tweet.analyzed_at)

    rows = (
        db.query(
            day_expr.label("day"),
            Tweet.sentiment,
            func.count(Tweet.id).label("count"),
        )
        .filter(
            Tweet.target_id == target.id,
            Tweet.sentiment.isnot(None),
            Tweet.analyzed_at >= since,
        )
        .group_by(day_expr, Tweet.sentiment)
        .order_by(day_expr)
        .all()
    )

    timeline: dict[str, dict[str, Any]] = {}
    for row in rows:
        day = str(row.day)
        if day not in timeline:
            timeline[day] = {
                "date": day,
                "target_id": target.id,
                "target_name": target.name,
                "total": 0,
                "sentiments": empty_sentiment_counts(),
            }

        sentiment = row.sentiment or "neutre"
        count = int(row.count)
        timeline[day]["sentiments"][sentiment] = timeline[day]["sentiments"].get(sentiment, 0) + count
        timeline[day]["total"] += count

    result = []
    for item in timeline.values():
        item["net_sentiment_score"] = net_score_from_counts(item["sentiments"])
        item["dominant_sentiment"] = top_two_sentiments(item["sentiments"])[0][0]
        result.append(item)
    return result


def get_representative_tweets(
    db: Session,
    target_ids: list[int],
    since: datetime,
    sentiment_filter: str | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    query = (
        db.query(Tweet)
        .filter(
            Tweet.target_id.in_(target_ids),
            Tweet.sentiment.isnot(None),
            Tweet.analyzed_at >= since,
        )
    )

    if sentiment_filter:
        from backend.app.services.llm_from_scratch import expand_sentiment_filter
        wanted = expand_sentiment_filter(sentiment_filter)
        if wanted:
            query = query.filter(Tweet.sentiment.in_(wanted))

    tweets = query.order_by(Tweet.confidence.desc().nullslast()).limit(limit).all()

    return [
        {
            "tweet_id": tweet.id,
            "target_id": tweet.target_id,
            "author": tweet.author_username,
            "text": tweet.text,
            "sentiment": tweet.sentiment,
            "confidence": round(float(tweet.confidence or 0), 3),
            "created_at": str(tweet.tweet_created_at) if tweet.tweet_created_at else None,
        }
        for tweet in tweets
    ]


def get_contrast_examples(db: Session, target_ids: list[int], since: datetime) -> dict[str, list[dict[str, Any]]]:
    examples: dict[str, list[dict[str, Any]]] = {}
    for sentiment in ["joie", "amour", "colere", "tristesse", "peur", "surprise", "neutre"]:
        rows = get_representative_tweets(db, target_ids, since, sentiment_filter=sentiment, limit=2)
        if rows:
            examples[sentiment] = rows
    return examples


def format_keywords(keywords: list[dict[str, Any]], max_items: int = 5) -> str:
    if not keywords:
        return "pas assez de mots récurrents exploitables"
    return ", ".join(item["term"] for item in keywords[:max_items])


def format_caveat(stats: dict[str, Any]) -> str:
    notes = stats.get("quality_notes") or []
    if not notes:
        return ""
    return f"Qualité lecture : {', '.join(notes)}."


def strongest_signals(stats: dict[str, Any]) -> list[str]:
    signals = []
    dist = stats["sentiment_distribution"]
    if stats["negative_ratio"] >= 0.35:
        signals.append(f"niveau négatif élevé ({pct(stats['negative_ratio'])})")
    elif stats["negative_ratio"] >= 0.2:
        signals.append(f"signal négatif à surveiller ({pct(stats['negative_ratio'])})")

    if dist.get("colere", 0) >= 0.2:
        signals.append(f"colère notable ({pct(dist.get('colere'))})")
    if dist.get("peur", 0) >= 0.2:
        signals.append(f"peur/inquiétude notable ({pct(dist.get('peur'))})")
    if dist.get("tristesse", 0) >= 0.2:
        signals.append(f"tristesse notable ({pct(dist.get('tristesse'))})")
    if stats["positive_ratio"] >= 0.5:
        signals.append(f"perception majoritairement positive ({pct(stats['positive_ratio'])})")
    if stats["dominant_margin"] < 0.1 and stats["total_tweets"] > 0:
        signals.append("pas de sentiment ultra dominant : conversation partagée")
    if not signals:
        signals.append("aucun signal émotionnel extrême détecté")
    return signals


def generate_summary_answer(stats: list[dict[str, Any]], examples: list[dict[str, Any]]) -> str:
    total_tweets = sum(item["total_tweets"] for item in stats)
    lines = [f"Analyse avancée sur {total_tweets} tweets analysés :"]

    for item in stats:
        dominant = item["dominant_sentiment"] or "inconnu"
        dominant_pct = item["sentiment_distribution"].get(dominant, 0) if dominant != "inconnu" else 0
        lines.append("")
        lines.append(f"### {item['target_name']}")
        lines.append(
            f"- Lecture globale : tonalité {item['net_sentiment_label']} "
            f"(score {item['net_sentiment_score']:+.2f})."
        )
        lines.append(
            f"- Sentiment dominant : {SENTIMENT_LABELS.get(dominant, dominant)} "
            f"({pct(dominant_pct)}), confiance moyenne {pct(item['average_confidence'])}."
        )
        lines.append(
            f"- Positif vs négatif : {pct(item['positive_ratio'])} positif / "
            f"{pct(item['negative_ratio'])} négatif."
        )
        lines.append(f"- Tendance récente : {item['trend']['label']} ({signed_pct(item['trend']['score_delta'])} de score émotionnel).")
        lines.append(f"- Sujets/mots qui ressortent : {format_keywords(item['keywords'])}.")
        lines.append(f"- Signaux : {'; '.join(strongest_signals(item))}.")
        lines.append(f"- {format_caveat(item)}")

    if examples:
        lines.append("")
        lines.append("Tweets représentatifs :")
        for tweet in examples[:4]:
            text = re.sub(r"\s+", " ", tweet["text"] or "").strip()
            lines.append(
                f"- @{tweet['author'] or '?'} : \"{text[:180]}\" "
                f"→ {SENTIMENT_LABELS.get(tweet['sentiment'], tweet['sentiment'])} ({pct(tweet['confidence'])})"
            )

    lines.append("")
    lines.append("Conclusion : la réponse s'appuie sur les tweets réellement collectés et analysés. Les pourcentages doivent être lus avec prudence si l'échantillon est faible ou si la confiance moyenne est basse.")
    return "\n".join(lines)


def generate_comparison_answer(stats: list[dict[str, Any]]) -> str:
    total_tweets = sum(item["total_tweets"] for item in stats)
    lines = [f"Comparaison avancée sur {total_tweets} tweets analysés :"]

    sorted_by_volume = sorted(stats, key=lambda item: item["total_tweets"], reverse=True)
    most_positive = max(stats, key=lambda item: item["net_sentiment_score"])
    most_negative = min(stats, key=lambda item: item["net_sentiment_score"])
    most_negative_ratio = max(stats, key=lambda item: item["negative_ratio"])
    most_confident = max(stats, key=lambda item: item["average_confidence"])

    lines.append("")
    lines.append("Vue par cible :")
    for item in sorted_by_volume:
        dominant = item["dominant_sentiment"] or "inconnu"
        dominant_pct = item["sentiment_distribution"].get(dominant, 0) if dominant != "inconnu" else 0
        lines.append(
            f"- {item['target_name']} : {item['total_tweets']} tweets, "
            f"dominant {SENTIMENT_LABELS.get(dominant, dominant)} ({pct(dominant_pct)}), "
            f"score {item['net_sentiment_score']:+.2f} ({item['net_sentiment_label']}), "
            f"négatif {pct(item['negative_ratio'])}, confiance {pct(item['average_confidence'])}."
        )

    lines.append("")
    lines.append("Écarts principaux :")
    lines.append(f"- Cible la plus positive : {most_positive['target_name']} (score {most_positive['net_sentiment_score']:+.2f}).")
    lines.append(f"- Cible la plus négative : {most_negative['target_name']} (score {most_negative['net_sentiment_score']:+.2f}).")
    lines.append(f"- Plus gros niveau de signaux négatifs : {most_negative_ratio['target_name']} ({pct(most_negative_ratio['negative_ratio'])}).")
    lines.append(f"- Résultat le plus fiable côté confiance modèle : {most_confident['target_name']} ({pct(most_confident['average_confidence'])}).")

    lines.append("")
    lines.append("Conclusion comparative :")
    if most_positive["target_id"] == most_negative["target_id"]:
        lines.append("- Les cibles sont assez proches : aucune différence forte ne ressort sur le score émotionnel.")
    else:
        lines.append(
            f"- {most_positive['target_name']} ressort mieux que {most_negative['target_name']} "
            "sur la tonalité globale. Pour décider si c'est vraiment significatif, regarde aussi le volume de tweets et la confiance moyenne."
        )

    return "\n".join(lines)


def generate_timeline_answer(stats: list[dict[str, Any]], timeline: list[dict[str, Any]]) -> str:
    if not timeline:
        return "Je n'ai pas assez de données temporelles pour produire une tendance fiable. Lance plusieurs collectes à des moments différents pour enrichir l'historique."

    lines = ["Analyse temporelle des sentiments :"]
    for item in stats:
        trend = item["trend"]
        lines.append("")
        lines.append(f"- {item['target_name']} : {trend['label']}.")
        lines.append(
            f"  Score première moitié : {trend['first_half_score']:+.2f}, "
            f"seconde moitié : {trend['second_half_score']:+.2f}, "
            f"delta : {trend['score_delta']:+.2f}."
        )
        lines.append(
            f"  Volume : {trend['first_half_total']} tweets au début contre "
            f"{trend['second_half_total']} récemment."
        )
        if abs(trend.get("negative_delta", 0)) >= 0.08:
            lines.append(f"  Variation du négatif : {signed_pct(trend['negative_delta'])}.")
        if abs(trend.get("positive_delta", 0)) >= 0.08:
            lines.append(f"  Variation du positif : {signed_pct(trend['positive_delta'])}.")

    lines.append("")
    lines.append("Le dashboard associé permet de vérifier la courbe jour par jour. Si toutes les données viennent d'une seule collecte, la tendance reste limitée.")
    return "\n".join(lines)


def generate_examples_answer(examples: list[dict[str, Any]], contrast_examples: dict[str, list[dict[str, Any]]]) -> str:
    if not examples and not contrast_examples:
        return "Je n'ai pas trouvé de tweets représentatifs pour cette demande."

    lines = ["Tweets représentatifs détectés :"]
    for tweet in examples[:8]:
        text = re.sub(r"\s+", " ", tweet["text"] or "").strip()
        lines.append(
            f"- @{tweet['author'] or '?'} : \"{text[:200]}\" "
            f"→ {SENTIMENT_LABELS.get(tweet['sentiment'], tweet['sentiment'])} ({pct(tweet['confidence'])})"
        )

    if contrast_examples:
        lines.append("")
        lines.append("Exemples par tonalité :")
        for sentiment, rows in contrast_examples.items():
            sample = rows[0]
            text = re.sub(r"\s+", " ", sample["text"] or "").strip()
            lines.append(
                f"- {SENTIMENT_LABELS.get(sentiment, sentiment)} : \"{text[:160]}\" "
                f"(@{sample['author'] or '?'})"
            )

    return "\n".join(lines)


def generate_text_answer(
    intent: str,
    stats: list[dict[str, Any]],
    timeline: list[dict[str, Any]],
    examples: list[dict[str, Any]],
    contrast_examples: dict[str, list[dict[str, Any]]] | None = None,
) -> str:
    if not stats:
        return "Je n'ai trouvé aucune cible à analyser."

    total_tweets = sum(item["total_tweets"] for item in stats)
    if total_tweets == 0:
        return (
            "Je n'ai pas encore assez de tweets analysés pour répondre. "
            "Lance d'abord une collecte puis une analyse de sentiment sur les cibles sélectionnées."
        )

    intent = canonical_intent(intent)
    contrast_examples = contrast_examples or {}

    if intent == "comparison":
        return generate_comparison_answer(stats)
    if intent == "timeline":
        return generate_timeline_answer(stats, timeline)
    if intent == "examples":
        return generate_examples_answer(examples, contrast_examples)
    return generate_summary_answer(stats, examples)




def regenerate_answer_variant(
    base_answer: str,
    feedback_context: str,
    stats: list[dict[str, Any]],
    examples: list[dict[str, Any]],
) -> str:
    """Produit une variante déterministe mais différente après feedback utilisateur."""
    lines = [
        "Réponse régénérée à partir de ton feedback :",
        f"Feedback pris en compte : {feedback_context.strip()[:500]}",
        "",
        "Lecture alternative :",
    ]

    for item in stats:
        dominant = item.get("dominant_sentiment") or "inconnu"
        second = item.get("second_sentiment") or "inconnu"
        lines.append(
            f"- {item['target_name']} : le signal principal reste {SENTIMENT_LABELS.get(dominant, dominant)}, "
            f"mais je vérifie aussi le second signal ({SENTIMENT_LABELS.get(second, second)}) "
            f"et la marge de dominance ({pct(item.get('dominant_margin', 0))})."
        )
        if item.get("low_confidence_rate", 0) >= 0.2:
            lines.append("  → Attention : une partie notable des tweets est peu confiante, donc la lecture doit rester prudente.")
        if item.get("keywords"):
            lines.append(f"  → Mots à contrôler manuellement : {format_keywords(item['keywords'], max_items=8)}.")

    if examples:
        lines.append("")
        lines.append("Tweets à vérifier en priorité :")
        # On inverse l'ordre pour ne pas ressortir exactement les mêmes exemples dominants.
        for tweet in list(reversed(examples))[:5]:
            text = re.sub(r"\s+", " ", tweet["text"] or "").strip()
            lines.append(
                f"- @{tweet['author'] or '?'} : \"{text[:180]}\" "
                f"→ {SENTIMENT_LABELS.get(tweet['sentiment'], tweet['sentiment'])} ({pct(tweet['confidence'])})"
            )

    lines.append("")
    lines.append("Ancienne synthèse, conservée pour comparaison :")
    lines.append(base_answer)
    return "\n".join(lines)

def generate_dashboard_config(question: str, intent: str, stats: list[dict[str, Any]], timeline_by_target: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    widgets: list[dict[str, Any]] = []

    widgets.append({
        "type": "sentiment_distribution",
        "title": "Répartition des sentiments",
        "chart": "pie",
        "data": [
            {
                "target_id": item["target_id"],
                "target_name": item["target_name"],
                "distribution": item["sentiment_distribution"],
                "counts": item["sentiment_counts"],
            }
            for item in stats
        ],
    })

    widgets.append({
        "type": "insight_summary",
        "title": "Insights automatiques",
        "chart": "cards",
        "data": [
            {
                "target_id": item["target_id"],
                "target_name": item["target_name"],
                "net_sentiment_score": item["net_sentiment_score"],
                "net_sentiment_label": item["net_sentiment_label"],
                "positive_ratio": item["positive_ratio"],
                "negative_ratio": item["negative_ratio"],
                "average_confidence": item["average_confidence"],
                "trend": item["trend"],
                "quality_notes": item["quality_notes"],
            }
            for item in stats
        ],
    })

    if len(stats) > 1 or canonical_intent(intent) == "comparison":
        widgets.append({
            "type": "target_comparison",
            "title": "Comparaison des cibles",
            "chart": "bar",
            "data": [
                {
                    "target_id": item["target_id"],
                    "target_name": item["target_name"],
                    "total_tweets": item["total_tweets"],
                    "dominant_sentiment": item["dominant_sentiment"],
                    "sentiment_distribution": item["sentiment_distribution"],
                    "net_sentiment_score": item["net_sentiment_score"],
                    "negative_ratio": item["negative_ratio"],
                    "positive_ratio": item["positive_ratio"],
                }
                for item in stats
            ],
        })

    widgets.append({
        "type": "sentiment_timeline",
        "title": "Évolution temporelle des sentiments",
        "chart": "line",
        "data": timeline_by_target,
    })

    widgets.append({
        "type": "keyword_topics",
        "title": "Mots et sujets récurrents",
        "chart": "bar",
        "data": [
            {
                "target_id": item["target_id"],
                "target_name": item["target_name"],
                "keywords": item["keywords"],
            }
            for item in stats
        ],
    })

    return {
        "title": "Dashboard généré par le LLM SentiFlow",
        "source_question": question,
        "intent": canonical_intent(intent),
        "generated_at": datetime.utcnow().isoformat(),
        "widgets": widgets,
    }


def ask_local_llm(
    db: Session,
    user_id: int,
    question: str,
    target_ids: list[int],
    days: int = 7,
    generate_dashboard: bool = True,
    intent_override: str | None = None,
    sentiment_filter_override: str | None = None,
    planner_actions: list[str] | None = None,
    feedback_context: str | None = None,
) -> dict[str, Any]:
    if not target_ids:
        raise ValueError("Il faut sélectionner au moins une cible.")

    detected_days = extract_days(question, default_days=days)
    since = datetime.utcnow() - timedelta(days=detected_days)

    predicted_intent, intent_confidence = INTENT_MODEL.predict(question)
    intent = canonical_intent(intent_override or predicted_intent, planner_actions)
    sentiment_filter = sentiment_filter_override or detect_sentiment_filter(question)

    targets = get_user_targets(db, user_id, target_ids)
    stats = [compute_target_stats(db, target, since) for target in targets]

    timeline_by_target = {target.name: compute_timeline(db, target, since) for target in targets}
    all_timeline_rows: list[dict[str, Any]] = []
    for rows in timeline_by_target.values():
        all_timeline_rows.extend(rows)

    examples = get_representative_tweets(
        db=db,
        target_ids=target_ids,
        since=since,
        sentiment_filter=sentiment_filter,
        limit=8,
    )
    contrast_examples = get_contrast_examples(db, target_ids, since)

    answer = generate_text_answer(
        intent=intent,
        stats=stats,
        timeline=all_timeline_rows,
        examples=examples,
        contrast_examples=contrast_examples,
    )

    if feedback_context:
        answer = regenerate_answer_variant(answer, feedback_context, stats, examples)

    dashboard_config = None
    if generate_dashboard or intent == "dashboard":
        dashboard_config = generate_dashboard_config(
            question=question,
            intent=intent,
            stats=stats,
            timeline_by_target=timeline_by_target,
        )

    return {
        "question": question,
        "intent": intent,
        "intent_confidence": intent_confidence,
        "period_days": detected_days,
        "sentiment_filter": sentiment_filter,
        "answer": answer,
        "targets": stats,
        "examples": examples,
        "contrast_examples": contrast_examples,
        "dashboard_config": dashboard_config,
    }
