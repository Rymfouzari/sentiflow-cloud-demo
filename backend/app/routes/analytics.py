"""
Analytics avancées pour le dashboard interactif "pro".

Calculs from scratch (NumPy) à partir des tweets analysés :
- KPIs (sentiment net, volume, variation)
- Timeline (évolution + proportions)
- Comparaison de cibles + share of voice
- Matrice de corrélation entre cibles
- ACP (PCA) des cibles
- Top mots-clés par polarité (drivers)

Réservé aux plans incluant le dashboard interactif (standard / premium).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any, Optional

import numpy as np
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.target import Target
from backend.app.models.tweet import Tweet
from backend.app.models.user import User
from backend.app.services.auth import get_current_user
from backend.app.services.plans import require_feature, has_feature

router = APIRouter(prefix="/analytics", tags=["Analytics"])

POSITIVE = {"joie", "amour"}
NEGATIVE = {"colere", "tristesse", "peur"}
ALL_SENTIMENTS = ["joie", "amour", "surprise", "incertain", "peur", "tristesse", "colere"]

# Stopwords FR + EN minimal pour les drivers
STOPWORDS = set("""
le la les un une des de du au aux et ou ni mais donc or car que qui quoi dont ou
ce cet cette ces mon ma mes ton ta tes son sa ses notre nos votre vos leur leurs
je tu il elle on nous vous ils elles me te se lui y en ne pas plus moins tres tres
pour par avec sans sous sur dans entre vers chez est sont etait suis es a as ai ont
ete être avoir fait faire dit comme tout tous toute toutes meme aussi alors si non oui
the a an of to in on for and or but is are was were be been has have had do does did done
this that these those it its he she they them we you i my your his her their our not no yes
so just like get got via rt http https com www amp co about over after all any more most
will would can could should may might must shall now new day days today new your you re ve
who what when where why how which whom while with within without into onto from up down out
off than then there here their theirs ours yours one two three some such only also very much
many lot lots great good bad big small still even ever never always going gonna want need
make made makes say says said see seen look looks know known thing things people time times
join free world signals every from
""".split())


def _net_score(counts: dict[str, int]) -> float:
    total = sum(counts.values())
    if total == 0:
        return 0.0
    pos = sum(counts.get(s, 0) for s in POSITIVE)
    neg = sum(counts.get(s, 0) for s in NEGATIVE)
    return round((pos - neg) / total, 4)


def _tweet_day(t: Tweet) -> str:
    dt = t.analyzed_at or t.tweet_created_at
    if not dt:
        return datetime.utcnow().strftime("%Y-%m-%d")
    return dt.strftime("%Y-%m-%d")


def _load_tweets(db: Session, user: User, target_ids: Optional[list[int]], days: int):
    """Charge les cibles de l'utilisateur + leurs tweets analysés sur la période."""
    targets_q = db.query(Target).filter(Target.user_id == user.id)
    if target_ids:
        targets_q = targets_q.filter(Target.id.in_(target_ids))
    targets = targets_q.all()
    tid_to_name = {t.id: t.name for t in targets}
    tids = list(tid_to_name.keys())
    if not tids:
        return targets, {}, []

    since = datetime.utcnow() - timedelta(days=days)
    tweets = (
        db.query(Tweet)
        .filter(
            Tweet.target_id.in_(tids),
            Tweet.sentiment.isnot(None),
        )
        .all()
    )
    # Filtre période (souple : garde si pas de date)
    kept = []
    for t in tweets:
        dt = t.analyzed_at or t.tweet_created_at
        if dt is None or dt >= since:
            kept.append(t)
    return targets, tid_to_name, kept


@router.get("/dashboard")
def analytics_dashboard(
    days: int = Query(default=30, ge=1, le=90),
    target_ids: Optional[str] = Query(default=None, description="IDs de cibles séparés par des virgules"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Payload complet pour le dashboard interactif."""
    require_feature(
        current_user, "interactive_dashboard",
        "Le dashboard interactif est réservé aux offres Standard et Premium.",
    )

    advanced = has_feature(current_user, "advanced_dashboard")

    parsed_ids = None
    if target_ids:
        parsed_ids = [int(x) for x in target_ids.split(",") if x.strip().isdigit()]

    targets, tid_to_name, tweets = _load_tweets(db, current_user, parsed_ids, days)

    if not tweets:
        return {
            "has_data": False,
            "plan_advanced": advanced,
            "message": "Aucune donnée analysée sur la période. Ajoutez des cibles et lancez une collecte.",
            "targets_count": len(targets),
        }

    # ---- KPIs ----
    total = len(tweets)
    global_counts = Counter(t.sentiment for t in tweets)
    pos = sum(global_counts.get(s, 0) for s in POSITIVE)
    neg = sum(global_counts.get(s, 0) for s in NEGATIVE)
    neu = total - pos - neg
    confidences = [float(t.confidence) for t in tweets if t.confidence is not None]
    avg_conf = round(sum(confidences) / len(confidences), 3) if confidences else 0.0

    # Variation vs période précédente (volume)
    mid = datetime.utcnow() - timedelta(days=days / 2)
    recent_vol = sum(1 for t in tweets if (t.analyzed_at or t.tweet_created_at or datetime.utcnow()) >= mid)
    older_vol = total - recent_vol
    volume_trend = round(((recent_vol - older_vol) / older_vol) * 100, 1) if older_vol > 0 else None

    kpis = {
        "total_tweets": total,
        "net_score": _net_score(global_counts),
        "positive_pct": round(pos / total * 100, 1),
        "negative_pct": round(neg / total * 100, 1),
        "neutral_pct": round(neu / total * 100, 1),
        "avg_confidence": avg_conf,
        "targets_count": len(targets),
        "volume_trend_pct": volume_trend,
    }

    # ---- Timeline (par jour) ----
    by_day: dict[str, Counter] = defaultdict(Counter)
    for t in tweets:
        by_day[_tweet_day(t)][t.sentiment] += 1
    timeline = []
    for day in sorted(by_day.keys()):
        c = by_day[day]
        d_total = sum(c.values())
        timeline.append({
            "date": day,
            "total": d_total,
            "net_score": _net_score(c),
            "positive": sum(c.get(s, 0) for s in POSITIVE),
            "negative": sum(c.get(s, 0) for s in NEGATIVE),
            "neutral": d_total - sum(c.get(s, 0) for s in POSITIVE) - sum(c.get(s, 0) for s in NEGATIVE),
        })

    # ---- Comparaison par cible + share of voice ----
    by_target: dict[int, list[Tweet]] = defaultdict(list)
    for t in tweets:
        by_target[t.target_id].append(t)

    targets_breakdown = []
    share_of_voice = []
    for tid, tw_list in by_target.items():
        c = Counter(t.sentiment for t in tw_list)
        vol = len(tw_list)
        name = tid_to_name.get(tid, str(tid))
        dist = {s: c.get(s, 0) for s in ALL_SENTIMENTS}
        targets_breakdown.append({
            "target_id": tid,
            "name": name,
            "volume": vol,
            "net_score": _net_score(c),
            "positive": sum(c.get(s, 0) for s in POSITIVE),
            "negative": sum(c.get(s, 0) for s in NEGATIVE),
            "distribution": dist,
        })
        share_of_voice.append({"name": name, "volume": vol})

    targets_breakdown.sort(key=lambda x: x["volume"], reverse=True)
    share_of_voice.sort(key=lambda x: x["volume"], reverse=True)

    result: dict[str, Any] = {
        "has_data": True,
        "plan_advanced": advanced,
        "period_days": days,
        "kpis": kpis,
        "timeline": timeline,
        "targets_breakdown": targets_breakdown,
        "share_of_voice": share_of_voice,
        "keywords": _top_keywords(tweets),
    }

    # ---- Analyses avancées (corrélation + ACP + clustering) : premium ----
    if advanced:
        result["correlation"] = _correlation_matrix(by_target, tid_to_name)
        result["pca"] = _pca_targets(by_target, tid_to_name)
    else:
        result["correlation"] = {"available": False, "reason": "premium_only"}
        result["pca"] = {"available": False, "reason": "premium_only"}

    # ---- Insights en clair (toujours générés) ----
    result["insights"] = _generate_insights(
        kpis, targets_breakdown, result["keywords"],
        result.get("correlation") if advanced else None,
        result.get("pca") if advanced else None,
    )

    return result


def _top_keywords(tweets: list[Tweet], top_n: int = 15) -> dict[str, list[dict[str, Any]]]:
    """
    Mots-clés DISTINCTIFS de chaque polarité (drivers), pas seulement les plus fréquents.

    On compare la fréquence d'un mot chez les positifs vs les négatifs via un log-ratio
    lissé. Un mot qui apparaît autant des deux côtés (ex. 'with', 'will') a un score ~0
    et n'est pas retenu. Seuls les mots vraiment caractéristiques ressortent.
    """
    import math

    pos_counter: Counter = Counter()
    neg_counter: Counter = Counter()

    def tokenize(text: str) -> list[str]:
        text = (text or "").lower()
        text = re.sub(r"http\S+|@\w+|#\w+|[^a-zàâçéèêëîïôûùüÿñæœ\s]", " ", text)
        return [w for w in text.split() if len(w) > 2 and w not in STOPWORDS]

    for t in tweets:
        toks = set(tokenize(t.text))  # set : on compte la présence par tweet, pas la répétition
        if t.sentiment in POSITIVE:
            pos_counter.update(toks)
        elif t.sentiment in NEGATIVE:
            neg_counter.update(toks)

    total_pos = sum(pos_counter.values()) or 1
    total_neg = sum(neg_counter.values()) or 1
    vocab = set(pos_counter) | set(neg_counter)
    V = len(vocab) or 1

    scored = []
    for w in vocab:
        pc = pos_counter.get(w, 0)
        nc = neg_counter.get(w, 0)
        if pc + nc < 2:  # trop rare = bruit
            continue
        p = (pc + 1) / (total_pos + V)
        n = (nc + 1) / (total_neg + V)
        score = math.log(p / n)  # >0 -> distinctif positif, <0 -> distinctif négatif
        scored.append((w, score, pc, nc))

    positives = sorted([s for s in scored if s[1] > 0.2], key=lambda x: x[1], reverse=True)[:top_n]
    negatives = sorted([s for s in scored if s[1] < -0.2], key=lambda x: x[1])[:top_n]

    return {
        "positive": [{"word": w, "count": pc} for w, _, pc, _ in positives],
        "negative": [{"word": w, "count": nc} for w, _, _, nc in negatives],
    }


def _daily_net_series(tw_list: list[Tweet], days_index: list[str]) -> list[float]:
    by_day: dict[str, Counter] = defaultdict(Counter)
    for t in tw_list:
        by_day[_tweet_day(t)][t.sentiment] += 1
    return [_net_score(by_day[d]) if d in by_day else 0.0 for d in days_index]


def _correlation_matrix(by_target: dict[int, list[Tweet]], tid_to_name: dict[int, str]) -> dict[str, Any]:
    """
    Corrélation entre cibles basée sur leur PROFIL de sentiment (répartition sur les
    7 émotions). Robuste même quand les tweets sont concentrés sur quelques jours
    (contrairement à une corrélation temporelle qui dégénère en ±1 avec peu de points).
    Deux cibles au profil émotionnel proche -> corrélation positive ; profils opposés
    (ex. joie vs colère) -> corrélation négative.
    """
    valid = {tid: tw for tid, tw in by_target.items() if len(tw) >= 5}
    if len(valid) < 3:
        return {
            "available": False,
            "reason": "need_3_targets",
            "message": "Ajoutez au moins 3 cibles (≥5 tweets chacune) pour débloquer la corrélation.",
        }

    labels: list[str] = []
    profiles: list[list[float]] = []
    for tid, tw in valid.items():
        c = Counter(t.sentiment for t in tw)
        total = sum(c.values())
        profiles.append([c.get(s, 0) / total for s in ALL_SENTIMENTS])
        labels.append(tid_to_name[tid])

    M = np.array(profiles, dtype=float)
    n = M.shape[0]
    corr = np.eye(n)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = M[i], M[j]
            if a.std() == 0 or b.std() == 0:
                c = 0.0
            else:
                c = float(np.corrcoef(a, b)[0, 1])
            corr[i, j] = corr[j, i] = round(c, 3)

    return {
        "available": True,
        "labels": labels,
        "matrix": corr.round(3).tolist(),
        "basis": "sentiment_profile",
    }


def _kmeans(coords: "np.ndarray", k: int, iters: int = 50) -> list[int]:
    """K-means minimal (from scratch) sur des points 2D. Retourne les labels."""
    n = coords.shape[0]
    if k >= n:
        return list(range(n))
    rng = np.random.default_rng(42)
    centers = coords[rng.choice(n, k, replace=False)]
    labels = [0] * n
    for _ in range(iters):
        # assignation
        dists = np.linalg.norm(coords[:, None, :] - centers[None, :, :], axis=2)
        new_labels = dists.argmin(axis=1)
        if list(new_labels) == labels:
            break
        labels = list(new_labels)
        # mise à jour
        for c in range(k):
            members = coords[new_labels == c]
            if len(members) > 0:
                centers[c] = members.mean(axis=0)
    return [int(x) for x in labels]


def _pca_targets(by_target: dict[int, list[Tweet]], tid_to_name: dict[int, str]) -> dict[str, Any]:
    """ACP 2D des cibles + détection automatique de familles de sujets (clusters)."""
    valid = {tid: tw for tid, tw in by_target.items() if len(tw) >= 3}
    if len(valid) < 3:
        return {
            "available": False,
            "reason": "need_3_targets",
            "message": "Ajoutez au moins 3 cibles avec des données pour débloquer la carte des sujets.",
        }

    labels, rows = [], []
    for tid, tw in valid.items():
        c = Counter(t.sentiment for t in tw)
        total = sum(c.values())
        feats = [c.get(s, 0) / total for s in ALL_SENTIMENTS]
        confs = [float(t.confidence) for t in tw if t.confidence is not None]
        feats.append(np.log1p(total))
        feats.append(sum(confs) / len(confs) if confs else 0.0)
        rows.append(feats)
        labels.append(tid_to_name[tid])

    X = np.array(rows, dtype=float)
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    std[std == 0] = 1.0
    Xs = (X - mean) / std

    U, S, Vt = np.linalg.svd(Xs, full_matrices=False)
    coords = U[:, :2] * S[:2]
    total_var = float((S ** 2).sum()) or 1.0
    explained = [(float(S[i] ** 2) / total_var) for i in range(min(2, len(S)))]

    # Clustering : familles de sujets
    k = max(2, min(4, len(labels) // 2))
    cluster_labels = _kmeans(coords, k)
    clusters: dict[int, list[str]] = defaultdict(list)
    for i, cl in enumerate(cluster_labels):
        clusters[cl].append(labels[i])

    points = [
        {
            "name": labels[i],
            "x": round(float(coords[i, 0]), 3),
            "y": round(float(coords[i, 1]), 3),
            "cluster": cluster_labels[i],
        }
        for i in range(len(labels))
    ]
    return {
        "available": True,
        "points": points,
        "explained_variance": [round(e, 3) for e in explained],
        "clusters": [{"id": cid, "members": members} for cid, members in clusters.items()],
    }


def _generate_insights(
    kpis: dict[str, Any],
    targets_breakdown: list[dict[str, Any]],
    keywords: dict[str, list],
    correlation: dict[str, Any] | None,
    pca: dict[str, Any] | None,
) -> list[dict[str, str]]:
    """Traduit les analyses en phrases claires pour un analyste non technique."""
    insights: list[dict[str, str]] = []

    # 1. Tonalité globale
    net = kpis.get("net_score", 0)
    if net >= 0.3:
        insights.append({"tone": "positive", "icon": "😊",
                         "text": f"Tonalité globale très positive ({kpis['positive_pct']}% de tweets positifs)."})
    elif net >= 0.05:
        insights.append({"tone": "positive", "icon": "🙂",
                         "text": f"Tonalité globale plutôt positive ({kpis['positive_pct']}% positifs, {kpis['negative_pct']}% négatifs)."})
    elif net > -0.05:
        insights.append({"tone": "neutral", "icon": "😐",
                         "text": f"Opinion partagée : {kpis['positive_pct']}% positifs contre {kpis['negative_pct']}% négatifs."})
    else:
        insights.append({"tone": "negative", "icon": "⚠️",
                         "text": f"Tonalité globale négative ({kpis['negative_pct']}% de tweets négatifs). À surveiller."})

    # 2. Meilleur / pire sujet
    ranked = sorted(targets_breakdown, key=lambda t: t["net_score"], reverse=True)
    if len(ranked) >= 2:
        best, worst = ranked[0], ranked[-1]
        insights.append({"tone": "positive", "icon": "🏆",
                         "text": f"« {best['name']} » est le sujet le mieux perçu (score {best['net_score']:+.2f})."})
        if worst["net_score"] < 0.1:
            insights.append({"tone": "negative", "icon": "🔻",
                             "text": f"« {worst['name']} » est le sujet le plus mal perçu (score {worst['net_score']:+.2f})."})

    # 3. Sujet le plus discuté (volume)
    if targets_breakdown:
        most = max(targets_breakdown, key=lambda t: t["volume"])
        insights.append({"tone": "neutral", "icon": "🗣️",
                         "text": f"« {most['name']} » domine la conversation ({most['volume']} tweets)."})

    # 4. Outlier via corrélation
    if correlation and correlation.get("available"):
        labels = correlation["labels"]
        matrix = correlation["matrix"]
        if len(labels) >= 3:
            avg_sim = []
            for i in range(len(labels)):
                others = [matrix[i][j] for j in range(len(labels)) if j != i]
                avg_sim.append(sum(others) / len(others) if others else 0)
            min_idx = int(np.argmin(avg_sim))
            if avg_sim[min_idx] < 0.5:
                insights.append({"tone": "negative", "icon": "🎯",
                                 "text": f"« {labels[min_idx]} » se démarque totalement des autres sujets : il suscite des réactions à part."})

    # 5. Familles de sujets (clusters)
    if pca and pca.get("available") and pca.get("clusters"):
        groups = [c for c in pca["clusters"] if len(c["members"]) >= 2]
        if groups:
            desc = " ; ".join("(" + ", ".join(g["members"]) + ")" for g in groups[:3])
            insights.append({"tone": "neutral", "icon": "🧩",
                             "text": f"{len(groups)} familles de sujets se ressemblent : {desc}."})

    # 6. Drivers négatifs
    neg_words = [w["word"] for w in keywords.get("negative", [])[:5]]
    if neg_words:
        insights.append({"tone": "negative", "icon": "💬",
                         "text": f"Mots qui reviennent chez les mécontents : {', '.join(neg_words)}."})

    return insights
