"""
Construit une configuration de dashboard (widgets) à partir des tweets analysés
en base, pour les cibles données. Compatible avec GeneratedDashboardRenderer côté
frontend (sentiment_distribution, insight_summary, target_comparison,
sentiment_timeline, keyword_topics).

Utilisé pour que les dashboards générés par le RAG affichent de vrais graphiques,
pas seulement la synthèse texte.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.app.models.target import Target
from backend.app.models.tweet import Tweet

POSITIVE = {"joie", "amour"}
NEGATIVE = {"colere", "tristesse", "peur"}

_STOP = set("""
le la les un une des de du au aux et ou mais donc car que qui quoi ce cette ces
je tu il elle on nous vous ils elles ne pas plus pour par avec sans sur dans est
sont the a an of to in on for and or but is are was be been has have this that it
he she they we you my your not no yes so just like get rt http https com www amp co
""".split())


def _tokenize(text: str) -> list[str]:
    text = (text or "").lower()
    text = re.sub(r"http\S+|@\w+|#\w+|[^a-zàâçéèêëîïôûùüÿñæœ\s]", " ", text)
    return [w for w in text.split() if len(w) > 2 and w not in _STOP]


def _net_label(net: float) -> str:
    if net >= 0.4:
        return "Tonalité très positive"
    if net >= 0.1:
        return "Tonalité plutôt positive"
    if net > -0.1:
        return "Tonalité partagée"
    if net > -0.4:
        return "Tonalité plutôt négative"
    return "Tonalité très négative"


def build_dashboard_config(db: Session, target_ids: list[int], question: str | None = None) -> dict[str, Any]:
    """Retourne un config_json avec widgets, ou un dict minimal si pas de données."""
    if not target_ids:
        return {"source_question": question, "target_ids": [], "widgets": [], "generated_at": datetime.utcnow().isoformat()}

    targets = db.query(Target).filter(Target.id.in_(target_ids)).all()

    distribution_data = []
    insight_data = []
    comparison_data = []
    keyword_data = []
    timeline_data: dict[str, list] = {}

    for tgt in targets:
        tws = (
            db.query(Tweet)
            .filter(Tweet.target_id == tgt.id, Tweet.sentiment.isnot(None))
            .all()
        )
        if not tws:
            continue

        counts = Counter(t.sentiment for t in tws)
        total = sum(counts.values())
        distribution = {s: round(c / total, 4) for s, c in counts.items()}
        pos = sum(counts.get(s, 0) for s in POSITIVE)
        neg = sum(counts.get(s, 0) for s in NEGATIVE)
        net = round((pos - neg) / total, 4) if total else 0
        confs = [float(t.confidence) for t in tws if t.confidence is not None]
        avg_conf = round(sum(confs) / len(confs), 4) if confs else 0
        dominant = counts.most_common(1)[0][0] if counts else "neutre"

        distribution_data.append({
            "target_id": tgt.id,
            "target_name": tgt.name,
            "counts": dict(counts),
            "distribution": distribution,
        })
        insight_data.append({
            "target_id": tgt.id,
            "target_name": tgt.name,
            "net_sentiment_score": net,
            "net_sentiment_label": _net_label(net),
            "positive_ratio": round(pos / total, 4) if total else 0,
            "negative_ratio": round(neg / total, 4) if total else 0,
            "average_confidence": avg_conf,
        })
        comparison_data.append({
            "target_name": tgt.name,
            "sentiment_distribution": distribution,
            "total_tweets": total,
            "dominant_sentiment": dominant,
            "net_sentiment_score": net,
        })

        # Mots-clés
        tok_counter: Counter = Counter()
        for t in tws:
            tok_counter.update(set(_tokenize(t.text)))
        keyword_data.append({
            "target_name": tgt.name,
            "keywords": [{"term": w, "count": c} for w, c in tok_counter.most_common(8)],
        })

        # Timeline par jour
        by_day: dict[str, Counter] = defaultdict(Counter)
        for t in tws:
            dt = t.analyzed_at or t.tweet_created_at
            day = dt.strftime("%Y-%m-%d") if dt else datetime.utcnow().strftime("%Y-%m-%d")
            by_day[day][t.sentiment] += 1
        series = []
        for day in sorted(by_day.keys()):
            c = by_day[day]
            d_total = sum(c.values())
            d_pos = sum(c.get(s, 0) for s in POSITIVE)
            d_neg = sum(c.get(s, 0) for s in NEGATIVE)
            series.append({"date": day, "net_sentiment_score": round((d_pos - d_neg) / d_total, 4) if d_total else 0})
        timeline_data[tgt.name] = series

    widgets = []
    if distribution_data:
        widgets.append({"type": "insight_summary", "title": "Lecture rapide", "data": insight_data})
        widgets.append({"type": "sentiment_distribution", "title": "Répartition des sentiments", "data": distribution_data})
        if len(comparison_data) >= 2:
            widgets.append({"type": "target_comparison", "title": "Comparaison des cibles", "data": comparison_data})
        widgets.append({"type": "sentiment_timeline", "title": "Évolution temporelle", "data": timeline_data})
        widgets.append({"type": "keyword_topics", "title": "Mots récurrents", "data": keyword_data})

    return {
        "source_question": question,
        "target_ids": target_ids,
        "widgets": widgets,
        "generated_at": datetime.utcnow().isoformat(),
    }
