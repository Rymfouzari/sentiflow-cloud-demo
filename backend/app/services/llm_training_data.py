from __future__ import annotations
import json
import random
from dataclasses import dataclass


TARGET_POOL = [
    "#france", "#minecraft", "#love", "#trump", "#psg", "#ia", "#openai",
    "#football", "#politique", "#cinema", "#music", "#paris", "#ecologie",
    "@elonmusk", "@openai", "@nasa", "@x", "@minecraft", "@netflixfr",
]

SENTIMENTS = ["joie", "colere", "tristesse", "peur", "surprise", "amour", "neutre"]


@dataclass(frozen=True)
class TrainingExample:
    user_text: str
    plan: dict

    def to_prompt(self) -> str:
        return build_prompt(self.user_text)

    def to_completion(self) -> str:
        return json.dumps(self.plan, ensure_ascii=False, separators=(",", ":"))

    def to_lm_text(self) -> str:
        return self.to_prompt() + self.to_completion() + "\n<END>"


def build_prompt(question: str) -> str:
    return (
        "Tu es le planner LLM de SentiFlow. "
        "Transforme la demande utilisateur en JSON strict.\n"
        "Actions autorisées: create_missing_targets, collect_tweets, "
        "analyze_sentiments, summarize, compare_targets, get_timeline, "
        "get_examples, generate_dashboard.\n"
        f"Demande: {question}\n"
        "JSON:"
    )


def _target_type(target: str) -> str:
    return "account" if target.startswith("@") else "hashtag"


def _plan(
    intent: str,
    targets: list[str],
    actions: list[str],
    days: int = 7,
    dashboard: bool = True,
    sentiment_filter: str | None = None,
    force_refresh: bool = False,
) -> dict:
    return {
        "intent": intent,
        "targets": targets,
        "target_types": {target: _target_type(target) for target in targets},
        "days": days,
        "actions": actions,
        "dashboard": dashboard,
        "sentiment_filter": sentiment_filter,
        "force_refresh": force_refresh,
    }


def generate_synthetic_examples(n: int = 8000, seed: int = 42) -> list[TrainingExample]:
    rng = random.Random(seed)
    examples: list[TrainingExample] = []

    collect_templates = [
        "récupère les tweets avec {a}",
        "collecte {a} puis analyse les sentiments",
        "analyse les nouveaux tweets de {a}",
        "crée la cible {a} et donne moi les résultats",
        "lance une collecte twitter sur {a}",
        "je veux savoir ce que les gens pensent de {a}",
        "ajoute {a}, récupère les tweets et résume l'activité",
    ]
    summary_templates = [
        "résume l'activité de {a}",
        "quel est le sentiment dominant sur {a}",
        "fais une synthèse de {a} sur {days} jours",
        "comment les gens réagissent à {a}",
        "donne moi le bilan sentiment de {a}",
        "analyse en profondeur les sentiments de {a}",
        "quels sont les signaux importants sur {a}",
        "donne une lecture détaillée de {a}",
        "est-ce que les résultats de {a} sont fiables",
        "quels sujets ressortent dans les tweets sur {a}",
    ]
    compare_templates = [
        "compare {a} et {b}",
        "qui est le plus positif entre {a} et {b}",
        "compare les sentiments de {a} avec {b} sur {days} jours",
        "fais un dashboard comparatif entre {a} et {b}",
        "est-ce que {a} est plus négatif que {b}",
        "quelle cible a le plus de signaux négatifs entre {a} et {b}",
        "compare la confiance et la tendance entre {a} et {b}",
        "compare les sujets qui ressortent sur {a} et {b}",
    ]
    timeline_templates = [
        "montre l'évolution temporelle de {a}",
        "est-ce que la colère augmente sur {a}",
        "donne la tendance des sentiments sur {a} pendant {days} jours",
        "analyse temporelle de {a}",
        "comment évolue la joie sur {a}",
        "est-ce que la perception se dégrade sur {a}",
        "analyse la variation du négatif sur {a}",
        "est-ce que les sentiments deviennent plus positifs sur {a}",
    ]
    examples_templates = [
        "montre des exemples de tweets sur {a}",
        "donne moi les tweets les plus {sentiment} sur {a}",
        "affiche quelques tweets représentatifs de {a}",
        "récupère des tweets {sentiment} avec {a}",
    ]
    dashboard_templates = [
        "génère un dashboard pour {a}",
        "prépare un tableau de bord sur {a}",
        "fais des graphiques pour {a}",
        "dashboard sentiment de {a} sur {days} jours",
    ]

    for _ in range(n):
        kind = rng.choice(["collect", "summary", "compare", "timeline", "examples", "dashboard"])
        a, b = rng.sample(TARGET_POOL, 2)
        days = rng.choice([1, 3, 7, 14, 30])
        sentiment = rng.choice(SENTIMENTS)

        if kind == "collect":
            text = rng.choice(collect_templates).format(a=a, days=days, sentiment=sentiment)
            plan = _plan(
                intent="collect_analyze_summarize",
                targets=[a],
                days=days,
                actions=[
                    "create_missing_targets",
                    "collect_tweets",
                    "analyze_sentiments",
                    "summarize",
                    "generate_dashboard",
                ],
                dashboard=True,
                force_refresh=True,
            )
        elif kind == "summary":
            text = rng.choice(summary_templates).format(a=a, days=days, sentiment=sentiment)
            plan = _plan(
                intent="summarize",
                targets=[a],
                days=days,
                actions=["analyze_sentiments", "summarize", "generate_dashboard"],
                dashboard=True,
            )
        elif kind == "compare":
            text = rng.choice(compare_templates).format(a=a, b=b, days=days, sentiment=sentiment)
            plan = _plan(
                intent="compare",
                targets=[a, b],
                days=days,
                actions=[
                    "create_missing_targets",
                    "collect_tweets",
                    "analyze_sentiments",
                    "compare_targets",
                    "generate_dashboard",
                ],
                dashboard=True,
            )
        elif kind == "timeline":
            text = rng.choice(timeline_templates).format(a=a, days=days, sentiment=sentiment)
            plan = _plan(
                intent="timeline",
                targets=[a],
                days=days,
                actions=["analyze_sentiments", "get_timeline", "generate_dashboard"],
                dashboard=True,
                sentiment_filter=sentiment if sentiment in text else None,
            )
        elif kind == "examples":
            text = rng.choice(examples_templates).format(a=a, days=days, sentiment=sentiment)
            plan = _plan(
                intent="examples",
                targets=[a],
                days=days,
                actions=["create_missing_targets", "collect_tweets", "analyze_sentiments", "get_examples"],
                dashboard=False,
                sentiment_filter=sentiment,
                force_refresh="récupère" in text or "tweets" in text,
            )
        else:  # dashboard
            text = rng.choice(dashboard_templates).format(a=a, days=days, sentiment=sentiment)
            plan = _plan(
                intent="dashboard",
                targets=[a],
                days=days,
                actions=["analyze_sentiments", "summarize", "generate_dashboard"],
                dashboard=True,
            )

        examples.append(TrainingExample(text, plan))

    fixed = [
        TrainingExample(
            "récupère les tweets avec le #france",
            _plan(
                "collect_analyze_summarize",
                ["#france"],
                ["create_missing_targets", "collect_tweets", "analyze_sentiments", "get_examples", "generate_dashboard"],
                force_refresh=True,
            ),
        ),
        TrainingExample(
            "compare #france et #minecraft",
            _plan(
                "compare",
                ["#france", "#minecraft"],
                ["create_missing_targets", "collect_tweets", "analyze_sentiments", "compare_targets", "generate_dashboard"],
            ),
        ),
        TrainingExample(
            "analyse #love sans refaire la collecte",
            _plan(
                "summarize",
                ["#love"],
                ["analyze_sentiments", "summarize", "generate_dashboard"],
                force_refresh=False,
            ),
        ),
        TrainingExample(
            "analyse en profondeur #france et donne les signaux importants",
            _plan(
                "summarize",
                ["#france"],
                ["analyze_sentiments", "summarize", "generate_dashboard"],
                force_refresh=False,
            ),
        ),
        TrainingExample(
            "est-ce que la perception de #minecraft se dégrade",
            _plan(
                "timeline",
                ["#minecraft"],
                ["analyze_sentiments", "get_timeline", "generate_dashboard"],
                force_refresh=False,
            ),
        ),
        TrainingExample(
            "compare les sujets et les signaux négatifs entre #france et #minecraft",
            _plan(
                "compare",
                ["#france", "#minecraft"],
                ["analyze_sentiments", "compare_targets", "generate_dashboard"],
                force_refresh=False,
            ),
        ),
        # === EXEMPLES QUESTIONS BDD (pour ré-entraînement) ===
        TrainingExample(
            "quels sont mes cibles",
            _plan("query_database", [], ["query_database"], dashboard=False),
        ),
        TrainingExample(
            "combien de tweets j'ai en base",
            _plan("query_database", [], ["query_database"], dashboard=False),
        ),
        TrainingExample(
            "quelle est la répartition des langues dans mes tweets",
            _plan("query_database", [], ["query_database"], dashboard=False),
        ),
        TrainingExample(
            "quels comptes génèrent le plus de colère",
            _plan("query_database", [], ["query_database"], dashboard=False),
        ),
        TrainingExample(
            "statistiques globales de mes données",
            _plan("query_database", [], ["query_database"], dashboard=False),
        ),
        TrainingExample(
            "combien de tweets analysés par cible",
            _plan("query_database", [], ["query_database"], dashboard=False),
        ),
    ]

    return fixed + examples
