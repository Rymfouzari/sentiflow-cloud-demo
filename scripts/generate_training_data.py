"""
Génère automatiquement les données d'entraînement du TinyGPT
à partir des VRAIES données en BDD (cibles, tweets, sentiments).

Usage:
  docker compose exec api python /app/scripts/generate_training_data.py
  OU
  .venv/bin/python scripts/generate_training_data.py

Le script :
1. Lit les cibles réelles de la BDD
2. Lit les questions posées par les utilisateurs (si logged)
3. Génère un JSON de templates enrichi avec les vraies données
4. Exporte dans data/planner_training_templates.json
"""
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, "/app")

from backend.app.database import SessionLocal
from backend.app.models.target import Target
from backend.app.models.tweet import Tweet
from sqlalchemy import func


def get_real_targets(db):
    """Récupère les cibles réelles de la BDD."""
    targets = db.query(Target).all()
    return [t.name.lower() for t in targets]


def get_sentiment_distribution(db):
    """Récupère les sentiments réels en BDD."""
    stats = (
        db.query(Tweet.sentiment, func.count(Tweet.id))
        .filter(Tweet.sentiment.isnot(None))
        .group_by(Tweet.sentiment)
        .all()
    )
    return [sent for sent, _ in stats if sent]


def get_authors_with_most_tweets(db, limit=10):
    """Récupère les auteurs les plus actifs."""
    authors = (
        db.query(Tweet.author_username, func.count(Tweet.id))
        .filter(Tweet.author_username.isnot(None))
        .group_by(Tweet.author_username)
        .order_by(func.count(Tweet.id).desc())
        .limit(limit)
        .all()
    )
    return [f"@{author}" for author, _ in authors if author]


def generate_templates_json(db):
    """Génère le JSON de templates à partir des données réelles."""

    # Cibles réelles
    real_targets = get_real_targets(db)
    real_sentiments = get_sentiment_distribution(db)
    real_authors = get_authors_with_most_tweets(db)

    # Pool de cibles = réelles + exemples classiques
    base_targets = [
        "#france", "#minecraft", "#love", "#trump", "#psg", "#ia", "#openai",
        "#football", "#politique", "#cinema", "#music", "#paris", "#ecologie",
        "#bts", "#kpop", "#crypto", "#sport", "#tech", "#netflix", "#manga",
        "@elonmusk", "@openai", "@nasa", "@bts_twt", "@netflixfr", "@minecraft",
    ]

    # Inclure aussi les cibles du dataset original de lseillier
    lseillier_targets = [
        "#france", "#minecraft", "#love", "#trump", "#psg", "#ia", "#openai",
        "#football", "#politique", "#cinema", "#music", "#paris", "#ecologie",
        "@elonmusk", "@openai", "@nasa", "@x", "@minecraft", "@netflixfr",
    ]

    # Fusionner tout (réelles en premier, pas de doublons)
    all_targets = list(dict.fromkeys(real_targets + real_authors + base_targets + lseillier_targets))

    # Sentiments réels + base
    base_sentiments = ["joie", "colere", "tristesse", "peur", "surprise", "amour", "neutre"]
    all_sentiments = list(dict.fromkeys(real_sentiments + base_sentiments))

    print(f"📊 Données BDD:")
    print(f"   Cibles réelles: {real_targets}")
    print(f"   Sentiments détectés: {real_sentiments}")
    print(f"   Auteurs actifs: {real_authors[:5]}")
    print(f"   Total cibles (pool): {len(all_targets)}")

    # Générer des templates de questions basés sur les vraies cibles
    extra_summary = []
    extra_compare = []
    extra_collect = []
    for t in real_targets[:10]:
        extra_summary.append(f"c'est quoi le sentiment de {t}")
        extra_summary.append(f"analyse moi {t}")
        extra_summary.append(f"les gens sont contents de {t} ?")
        extra_collect.append(f"ajoute {t}, récupère les tweets et résume l'activité")
    for i in range(min(5, len(real_targets) - 1)):
        a, b = real_targets[i], real_targets[i + 1]
        extra_compare.append(f"compare {a} et {b}")
        extra_compare.append(f"lequel est mieux entre {a} et {b}")

    # Templates originaux de lseillier + nos ajouts
    templates = {
        "collect": [
            "récupère les tweets avec {a}",
            "collecte {a} puis analyse les sentiments",
            "analyse les nouveaux tweets de {a}",
            "crée la cible {a} et donne moi les résultats",
            "lance une collecte twitter sur {a}",
            "je veux savoir ce que les gens pensent de {a}",
            "ajoute {a} et récupère les tweets",
            "va chercher les tweets de {a}",
            "récupère moi {a} stp",
            "ajoute {a}, récupère les tweets et résume l'activité",
        ] + extra_collect,
        "summary": [
            "résume l'activité de {a}",
            "quel est le sentiment dominant sur {a}",
            "fais une synthèse de {a} sur {days} jours",
            "comment les gens réagissent à {a}",
            "quels sont les signaux importants sur {a}",
            "sentiment sur {a}",
            "analyse {a}",
            "c'est quoi le sentiment de {a}",
            "les gens pensent quoi de {a}",
            "dis moi le sentiment sur {a}",
            "que pensent les gens de {a}",
            "avis sur {a}",
            "donne moi le bilan sentiment de {a}",
            "analyse en profondeur les sentiments de {a}",
            "donne une lecture détaillée de {a}",
            "est-ce que les résultats de {a} sont fiables",
            "quels sujets ressortent dans les tweets sur {a}",
        ] + extra_summary,
        "compare": [
            "compare {a} et {b}",
            "qui est le plus positif entre {a} et {b}",
            "compare les sentiments de {a} avec {b}",
            "est-ce que {a} est plus négatif que {b}",
            "différence entre {a} et {b}",
            "lequel est mieux perçu {a} ou {b}",
            "{a} vs {b}",
        ] + extra_compare,
        "timeline": [
            "montre l'évolution temporelle de {a}",
            "est-ce que la colère augmente sur {a}",
            "tendance des sentiments sur {a} pendant {days} jours",
            "est-ce que la joie augmente sur {a}",
            "comment évolue le sentiment sur {a}",
            "la perception de {a} s'améliore ou se dégrade",
            "évolution de {a} cette semaine",
        ],
        "database": [
            "quels sont mes cibles",
            "combien de tweets j'ai en base",
            "quelle est la répartition des langues dans mes tweets",
            "quels comptes génèrent le plus de colère",
            "quels comptes génèrent le plus de tristesse",
            "quels hashtags sont les plus négatifs",
            "qui a le plus de tweets positifs",
            "statistiques globales de mes données",
            "combien de tweets analysés par cible",
            "c'est quoi les cibles que j'ai",
            "mes données en base",
            "quelles cibles je suis",
            "nombre total de tweets",
            "répartition des sentiments global",
            "montre moi mes stats",
            "combien de tweets j'ai sur chaque cible",
        ],
        "examples": [
            "montre des exemples de tweets sur {a}",
            "donne moi les tweets les plus {sentiment} sur {a}",
            "affiche quelques tweets représentatifs de {a}",
            "exemples de tweets {sentiment} sur {a}",
        ],
    }

    intents = {
        "collect": {
            "intent": "collect_analyze_summarize",
            "actions": ["create_missing_targets", "collect_tweets", "analyze_sentiments", "summarize", "generate_dashboard"],
            "force_refresh": True,
            "dashboard": True,
        },
        "summary": {
            "intent": "summarize",
            "actions": ["analyze_sentiments", "summarize", "generate_dashboard"],
            "force_refresh": False,
            "dashboard": True,
        },
        "compare": {
            "intent": "compare",
            "actions": ["analyze_sentiments", "compare_targets", "generate_dashboard"],
            "force_refresh": False,
            "dashboard": True,
        },
        "timeline": {
            "intent": "timeline",
            "actions": ["analyze_sentiments", "get_timeline", "generate_dashboard"],
            "force_refresh": False,
            "dashboard": True,
        },
        "database": {
            "intent": "query_database",
            "actions": ["query_database"],
            "force_refresh": False,
            "dashboard": False,
        },
        "examples": {
            "intent": "examples",
            "actions": ["analyze_sentiments", "get_examples"],
            "force_refresh": False,
            "dashboard": False,
        },
    }

    result = {
        "generated_from": "BDD réelle + templates de base",
        "real_targets_count": len(real_targets),
        "total_targets_count": len(all_targets),
        "targets": all_targets,
        "sentiments": all_sentiments,
        "templates": templates,
        "intents": intents,
    }

    return result


def main():
    print("=" * 60)
    print("🔄 Génération des données d'entraînement depuis la BDD")
    print("=" * 60)

    db = SessionLocal()
    try:
        data = generate_templates_json(db)

        # Sauvegarder
        output_path = Path(__file__).parent.parent / "data" / "planner_training_templates.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"\n✅ Fichier généré: {output_path}")
        print(f"   Cibles: {data['total_targets_count']}")
        print(f"   Templates: {sum(len(v) for v in data['templates'].values())}")
        print(f"\n   Pour entraîner: lance scripts/train_tinygpt_colab.py sur Colab")

    finally:
        db.close()


if __name__ == "__main__":
    main()
