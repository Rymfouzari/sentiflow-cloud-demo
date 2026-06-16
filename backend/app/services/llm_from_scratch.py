"""
Mini LLM from scratch pour SentiFlow.

Il y a deux niveaux :
1. Un vrai modèle Transformer decoder-only PyTorch, entraînable avec scripts/train_sentiflow_llm.py.
2. Un fallback déterministe si aucun checkpoint n'est encore présent, pour que
   l'application fonctionne immédiatement pendant le développement.

Le rôle du LLM n'est pas de remplacer ChatGPT. Il produit un plan d'actions JSON spécialisé :
créer une cible, collecter des tweets, analyser les sentiments, comparer, générer un dashboard.
"""
from __future__ import annotations
import json
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.app.services.llm_tokenizer import CharTokenizer
from backend.app.services.llm_training_data import build_prompt

try:
    import torch
    import torch.nn as nn
except Exception:
    torch = None  # type: ignore
    nn = None  # type: ignore

DEFAULT_CHECKPOINT_PATH = Path(
    os.getenv("SENTIFLOW_LLM_CHECKPOINT", "/app/backend/app/ml/sentiflow_tiny_llm.pt")
)

ALLOWED_ACTIONS = {
    "create_missing_targets",
    "collect_tweets",
    "analyze_sentiments",
    "summarize",
    "compare_targets",
    "get_timeline",
    "get_examples",
    "generate_dashboard",
    "query_database",
}


if nn is not None:
    class TinyGPT(nn.Module):
        def __init__(
            self,
            vocab_size: int,
            block_size: int = 512,
            n_embd: int = 192,
            n_head: int = 4,
            n_layer: int = 4,
            dropout: float = 0.1,
        ):
            super().__init__()
            self.block_size = block_size
            self.token_embedding = nn.Embedding(vocab_size, n_embd)
            self.position_embedding = nn.Embedding(block_size, n_embd)
            encoder_layer = nn.TransformerEncoderLayer(
                d_model=n_embd,
                nhead=n_head,
                dim_feedforward=4 * n_embd,
                dropout=dropout,
                batch_first=True,
                activation="gelu",
            )
            self.blocks = nn.TransformerEncoder(encoder_layer, num_layers=n_layer)
            self.ln_f = nn.LayerNorm(n_embd)
            self.lm_head = nn.Linear(n_embd, vocab_size, bias=False)

        def forward(self, idx):
            batch_size, seq_len = idx.shape
            if seq_len > self.block_size:
                idx = idx[:, -self.block_size:]
                seq_len = self.block_size
            positions = torch.arange(seq_len, device=idx.device).unsqueeze(0)
            x = self.token_embedding(idx) + self.position_embedding(positions)
            causal_mask = torch.triu(
                torch.ones(seq_len, seq_len, device=idx.device, dtype=torch.bool),
                diagonal=1,
            )
            x = self.blocks(x, mask=causal_mask)
            x = self.ln_f(x)
            return self.lm_head(x)
else:
    class TinyGPT:  # type: ignore
        pass


def _strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text)
        if unicodedata.category(ch) != "Mn"
    )


def normalize(text: str) -> str:
    return _strip_accents(text).lower().strip()


def extract_mentions(text: str) -> list[str]:
    hashtags = re.findall(r"#[A-Za-z0-9_À-ÿ-]+", text)
    accounts = re.findall(r"@[A-Za-z0-9_]+", text)
    mentions = []
    for mention in hashtags + accounts:
        cleaned = mention.strip().rstrip(".,;:!?)]}").lower()
        if cleaned not in mentions:
            mentions.append(cleaned)
    return mentions


def extract_days(text: str, default: int = 7) -> int:
    q = normalize(text)
    match = re.search(r"(\d+)\s*(jour|jours|j|day|days)", q)
    if match:
        return max(1, min(90, int(match.group(1))))
    if "mois" in q:
        return 30
    if "semaine" in q:
        return 7
    if "hier" in q or "24h" in q:
        return 1
    return default


def detect_sentiment_filter(text: str) -> str | None:
    text = re.sub(r"[#@][A-Za-z0-9_À-ÿ-]+", " ", text)
    q = normalize(text)
    # Les groupes (négatif / positif) sont testés en premier : un mot comme
    # "négatif" couvre plusieurs émotions, il prime sur une émotion isolée.
    aliases = {
        "negatif": ["negatif", "negative", "negativite"],
        "positif": ["positif", "positive", "positivite"],
        "joie": ["joie", "joyeux", "heureux"],
        "colere": ["colere", "rage", "enerve", "fache", "haine"],
        "tristesse": ["tristesse", "triste", "deprime"],
        "peur": ["peur", "inquiet", "anxiete", "angoisse"],
        "surprise": ["surprise", "etonne", "wow"],
        "amour": ["amour", "love", "coeur"],
        "neutre": ["neutre", "neutral"],
    }
    for sentiment, words in aliases.items():
        if any(word in q for word in words):
            return sentiment
    return None


# Groupes de sentiments : un filtre comme "négatif" couvre plusieurs émotions.
SENTIMENT_GROUPS = {
    "negatif": ["colere", "tristesse", "peur"],
    "positif": ["joie", "amour"],
}


def expand_sentiment_filter(sentiment_filter: str | None) -> list[str]:
    """
    Transforme un filtre de sentiment en liste d'émotions concrètes.
    - "negatif" -> ["colere", "tristesse", "peur"]
    - "positif" -> ["joie", "amour"]
    - "colere"  -> ["colere"]   (émotion déjà précise)
    - None / "" -> []           (pas de filtre)
    """
    if not sentiment_filter:
        return []
    sf = str(sentiment_filter).strip().lower()
    if sf in SENTIMENT_GROUPS:
        return list(SENTIMENT_GROUPS[sf])
    return [sf]


def _safe_json_from_text(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = text[start: end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def validate_plan(raw_plan: dict[str, Any], question: str) -> dict[str, Any]:
    fallback = fallback_plan(question)
    if not isinstance(raw_plan, dict):
        return fallback

    targets = raw_plan.get("targets")
    if not isinstance(targets, list):
        targets = fallback["targets"]
    targets = [str(t).strip().lower() for t in targets if str(t).strip()]

    actions = raw_plan.get("actions")
    if not isinstance(actions, list):
        actions = fallback["actions"]
    actions = [str(a) for a in actions if str(a) in ALLOWED_ACTIONS]
    if not actions:
        actions = fallback["actions"]

    days = raw_plan.get("days", fallback["days"])
    try:
        days = max(1, min(90, int(days)))
    except Exception:
        days = fallback["days"]

    dashboard = bool(raw_plan.get("dashboard", fallback["dashboard"]))
    if "generate_dashboard" in actions:
        dashboard = True

    sentiment_filter = raw_plan.get("sentiment_filter", fallback.get("sentiment_filter"))
    if sentiment_filter is not None:
        sentiment_filter = str(sentiment_filter)

    target_types = {}
    for target in targets:
        target_types[target] = "account" if target.startswith("@") else "hashtag"

    return {
        "intent": str(raw_plan.get("intent", fallback["intent"])),
        "targets": targets,
        "target_types": target_types,
        "days": days,
        "actions": actions,
        "dashboard": dashboard,
        "sentiment_filter": sentiment_filter,
        "force_refresh": bool(raw_plan.get("force_refresh", fallback["force_refresh"])),
        "planner_source": raw_plan.get("planner_source", "tiny_transformer"),
    }


def fallback_plan(question: str) -> dict[str, Any]:
    q = normalize(question)
    targets = extract_mentions(question)
    days = extract_days(question)
    sentiment_filter = detect_sentiment_filter(question)

    collect_negated = any(phrase in q for phrase in [
        "sans refaire la collecte", "sans collecte", "ne collecte pas",
        "pas de collecte", "sans recollecter", "sans recuperer"
    ])

    wants_collect = (not collect_negated) and any(
        word in q
        for word in [
            "recupere", "recupere", "collecte", "collecter", "nouveaux", "nouveau",
            "twitter", "tweets avec", "ajoute", "cree", "cree",
        ]
    )
    wants_compare = any(word in q for word in ["compare", "comparaison", "versus", "vs", "entre"])
    wants_timeline = any(word in q for word in ["evolution", "tendance", "temps", "temporel", "augmente", "baisse"])
    wants_examples = any(word in q for word in ["exemple", "tweets", "montre", "affiche"])
    wants_dashboard = any(word in q for word in ["dashboard", "graphique", "graphiques", "visualisation", "tableau de bord"])
    wants_database = any(word in q for word in [
        "mes cibles", "ma base", "combien de tweets", "quelles cibles",
        "mes donnees", "mes données", "statistiques globales",
        "repartition", "répartition", "langues", "langue",
        "quel compte", "quels comptes", "qui genere", "qui génère",
        "stocke", "enregistre", "en base",
    ])

    if wants_compare or len(targets) >= 2:
        intent = "compare"
        actions = ["create_missing_targets", "collect_tweets", "analyze_sentiments", "compare_targets", "generate_dashboard"]
    elif wants_database:
        intent = "query_database"
        actions = ["query_database"]
    elif wants_timeline:
        intent = "timeline"
        actions = ["create_missing_targets", "analyze_sentiments", "get_timeline", "generate_dashboard"]
    elif wants_examples or wants_collect:
        intent = "collect_analyze_examples" if wants_collect else "examples"
        actions = ["create_missing_targets", "collect_tweets", "analyze_sentiments", "get_examples"]
        if wants_dashboard:
            actions.append("generate_dashboard")
    elif wants_dashboard:
        intent = "dashboard"
        actions = ["create_missing_targets", "analyze_sentiments", "summarize", "generate_dashboard"]
    else:
        intent = "summarize"
        actions = ["analyze_sentiments", "summarize", "generate_dashboard"]

    dashboard = wants_dashboard or intent in {"summarize", "compare", "timeline", "dashboard"}
    target_types = {target: "account" if target.startswith("@") else "hashtag" for target in targets}

    return {
        "intent": intent,
        "targets": targets,
        "target_types": target_types,
        "days": days,
        "actions": actions,
        "dashboard": dashboard,
        "sentiment_filter": sentiment_filter,
        "force_refresh": wants_collect,
        "planner_source": "fallback_symbolic",
    }


@dataclass
class SentiflowPlanner:
    checkpoint_path: Path = DEFAULT_CHECKPOINT_PATH
    max_new_tokens: int = 380

    def __post_init__(self):
        self.tokenizer = CharTokenizer.build_default()
        self.model = None
        self.device = "cpu"
        self.loaded_checkpoint = False
        self.load_checkpoint_if_available()

    def load_checkpoint_if_available(self) -> None:
        if torch is None:
            return
        if not self.checkpoint_path.exists():
            return
        payload = torch.load(self.checkpoint_path, map_location="cpu")
        tokenizer_payload = payload.get("tokenizer")
        if tokenizer_payload:
            stoi = {str(k): int(v) for k, v in tokenizer_payload["stoi"].items()}
            itos = {index: token for token, index in stoi.items()}
            self.tokenizer = CharTokenizer(stoi=stoi, itos=itos)

        config = payload.get("config", {})
        self.model = TinyGPT(
            vocab_size=self.tokenizer.vocab_size,
            block_size=int(config.get("block_size", 512)),
            n_embd=int(config.get("n_embd", 192)),
            n_head=int(config.get("n_head", 4)),
            n_layer=int(config.get("n_layer", 4)),
            dropout=0.0,
        )
        self.model.load_state_dict(payload["model_state_dict"])
        self.model.eval()
        self.loaded_checkpoint = True

    def generate_with_model(self, question: str) -> dict[str, Any] | None:
        if torch is None or self.model is None:
            return None
        prompt = build_prompt(question)
        ids = self.tokenizer.encode(prompt, add_bos=True)
        idx = torch.tensor([ids], dtype=torch.long)
        with torch.no_grad():
            for _ in range(self.max_new_tokens):
                idx_cond = idx[:, -self.model.block_size:]
                logits = self.model(idx_cond)
                next_logits = logits[:, -1, :] / 0.8
                probs = torch.softmax(next_logits, dim=-1)
                next_id = torch.multinomial(probs, num_samples=1)
                idx = torch.cat([idx, next_id], dim=1)
                if int(next_id.item()) == self.tokenizer.eos_id:
                    break
        decoded = self.tokenizer.decode(idx[0].tolist())
        generated = decoded[len(prompt):]
        parsed = _safe_json_from_text(generated)
        if parsed is None:
            return None
        parsed["planner_source"] = "tiny_transformer_checkpoint"
        return parsed

    def plan(self, question: str) -> dict[str, Any]:
        # Utiliser le fallback symbolique qui fonctionne correctement
        # Le TinyGPT checkpoint hallucine sur les cibles non vues à l'entraînement
        # On le réactivera après ré-entraînement avec les nouvelles données
        fallback = fallback_plan(question)
        return validate_plan(fallback, question)

    def model_info(self) -> dict[str, Any]:
        return {
            "type": "tiny_decoder_transformer_from_scratch",
            "checkpoint_loaded": self.loaded_checkpoint,
            "checkpoint_path": str(self.checkpoint_path),
            "fallback_enabled": True,
            "vocab_size": self.tokenizer.vocab_size,
        }


_PLANNER: SentiflowPlanner | None = None


def get_planner() -> SentiflowPlanner:
    global _PLANNER
    if _PLANNER is None:
        _PLANNER = SentiflowPlanner()
    return _PLANNER
