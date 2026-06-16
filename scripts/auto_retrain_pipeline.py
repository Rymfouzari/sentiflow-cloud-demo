"""
Pipeline d'entraînement automatique du TinyGPT planner.

Fonctionnement :
1. Exporte les données de la BDD (question_logs + llm_feedbacks) en exemples d'entraînement
2. Fusionne avec les exemples synthétiques existants
3. Entraîne un nouveau checkpoint
4. Évalue le nouveau modèle vs l'ancien sur un jeu de test
5. Remplace le .pt seulement si le nouveau est meilleur

Prévu pour tourner en cron tous les 2 jours :
  0 3 */2 * * cd /app && python scripts/auto_retrain_pipeline.py
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Ajouter le projet au path
sys.path.insert(0, str(Path(__file__).parent.parent))

import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset

from backend.app.services.llm_from_scratch import TinyGPT, fallback_plan, validate_plan
from backend.app.services.llm_tokenizer import CharTokenizer
from backend.app.services.llm_training_data import (
    TrainingExample,
    build_prompt,
    generate_synthetic_examples,
    _target_type,
)


# ============================================
# CHEMINS
# ============================================

PROJECT_ROOT = Path(__file__).parent.parent
CHECKPOINT_PATH = PROJECT_ROOT / "backend" / "app" / "ml" / "sentiflow_tiny_llm.pt"
CHECKPOINT_NEW = PROJECT_ROOT / "backend" / "app" / "ml" / "sentiflow_tiny_llm_candidate.pt"
CHECKPOINT_BACKUP = PROJECT_ROOT / "backend" / "app" / "ml" / "sentiflow_tiny_llm_backup.pt"
TRAINING_DATA_EXPORT = PROJECT_ROOT / "data" / "training_data_from_db.json"
EVAL_RESULTS_PATH = PROJECT_ROOT / "data" / "retrain_eval_results.json"


# ============================================
# ÉTAPE 1 : EXPORT DEPUIS LA BDD
# ============================================

def export_training_data_from_db() -> list[TrainingExample]:
    """
    Exporte les questions posées par les utilisateurs + les feedbacks
    pour enrichir les données d'entraînement du planner.
    """
    from backend.app.database import SessionLocal
    from backend.app.models.question_log import QuestionLog

    examples: list[TrainingExample] = []
    db = SessionLocal()

    try:
        # 1. Questions avec intent détecté (validées par l'usage)
        logs = (
            db.query(QuestionLog)
            .filter(
                QuestionLog.intent_detected.isnot(None),
                QuestionLog.targets_detected.isnot(None),
            )
            .order_by(QuestionLog.created_at.desc())
            .limit(5000)
            .all()
        )

        for log in logs:
            targets = log.targets_detected or []
            if not targets or not log.question:
                continue

            # Construire le plan à partir de ce que le système a détecté
            plan = {
                "intent": log.intent_detected,
                "targets": targets,
                "target_types": {t: _target_type(t) for t in targets},
                "days": 7,
                "actions": _intent_to_actions(log.intent_detected),
                "dashboard": log.intent_detected in {"summarize", "compare", "timeline", "dashboard"},
                "force_refresh": log.mode_used == "agent",
            }

            examples.append(TrainingExample(user_text=log.question, plan=plan))

        # 2. LLM Feedbacks (corrections utilisateur = données de haute qualité)
        try:
            from backend.app.models.llm_feedback import LLMFeedback

            feedbacks = (
                db.query(LLMFeedback)
                .filter(LLMFeedback.question.isnot(None))
                .order_by(LLMFeedback.created_at.desc())
                .limit(2000)
                .all()
            )

            for fb in feedbacks:
                meta = fb.metadata_json or {}
                intent = meta.get("intent")
                targets = meta.get("target_ids_from_frontend", [])
                if not intent or not fb.question:
                    continue

                # Reconstruire le plan validé
                plan = fallback_plan(fb.question)
                if intent:
                    plan["intent"] = intent
                examples.append(TrainingExample(user_text=fb.question, plan=plan))

        except Exception as e:
            print(f"[PIPELINE] LLM feedbacks indisponibles: {e}")

        print(f"[PIPELINE] {len(examples)} exemples exportés depuis la BDD")

    finally:
        db.close()

    # Sauvegarder l'export
    TRAINING_DATA_EXPORT.parent.mkdir(parents=True, exist_ok=True)
    export_data = [
        {"question": ex.user_text, "plan": ex.plan}
        for ex in examples
    ]
    TRAINING_DATA_EXPORT.write_text(
        json.dumps(export_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[PIPELINE] Export sauvegardé: {TRAINING_DATA_EXPORT}")

    return examples


def _intent_to_actions(intent: str) -> list[str]:
    """Mappe un intent vers les actions attendues."""
    mapping = {
        "collect_analyze_summarize": [
            "create_missing_targets", "collect_tweets",
            "analyze_sentiments", "summarize", "generate_dashboard",
        ],
        "summarize": ["analyze_sentiments", "summarize", "generate_dashboard"],
        "compare": [
            "create_missing_targets", "collect_tweets",
            "analyze_sentiments", "compare_targets", "generate_dashboard",
        ],
        "timeline": ["analyze_sentiments", "get_timeline", "generate_dashboard"],
        "examples": [
            "create_missing_targets", "collect_tweets",
            "analyze_sentiments", "get_examples",
        ],
        "dashboard": ["analyze_sentiments", "summarize", "generate_dashboard"],
    }
    return mapping.get(intent, ["analyze_sentiments", "summarize", "generate_dashboard"])


# ============================================
# ÉTAPE 2 : FUSION DES DONNÉES
# ============================================

def build_full_training_set(db_examples: list[TrainingExample], n_synthetic: int = 6000) -> list[TrainingExample]:
    """
    Fusionne exemples BDD (haute qualité) + exemples synthétiques.
    Les exemples BDD sont sur-échantillonnés (x3) car plus représentatifs.
    """
    synthetic = generate_synthetic_examples(n=n_synthetic, seed=int(time.time()) % 10000)

    # Sur-échantillonner les exemples BDD
    db_oversampled = db_examples * 3 if db_examples else []

    full = synthetic + db_oversampled
    print(f"[PIPELINE] Dataset final: {len(synthetic)} synthétiques + {len(db_oversampled)} BDD = {len(full)} total")
    return full


# ============================================
# ÉTAPE 3 : ENTRAÎNEMENT
# ============================================

class PlannerDataset(Dataset):
    def __init__(self, texts: list[str], tokenizer: CharTokenizer, block_size: int):
        self.samples = []
        self.tokenizer = tokenizer
        self.block_size = block_size

        for text in texts:
            ids = tokenizer.encode(text, add_bos=True, add_eos=True)
            if len(ids) < 2:
                continue
            if len(ids) > block_size + 1:
                ids = ids[: block_size + 1]
            self.samples.append(ids)

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int):
        ids = self.samples[index]
        x = ids[:-1]
        y = ids[1:]

        pad_len = self.block_size - len(x)
        if pad_len > 0:
            x = x + [self.tokenizer.pad_id] * pad_len
            y = y + [self.tokenizer.pad_id] * pad_len

        return torch.tensor(x, dtype=torch.long), torch.tensor(y, dtype=torch.long)


def train_model(
    examples: list[TrainingExample],
    output_path: Path,
    epochs: int = 6,
    batch_size: int = 32,
    block_size: int = 512,
    n_embd: int = 192,
    n_head: int = 4,
    n_layer: int = 4,
    lr: float = 3e-4,
) -> dict:
    """Entraîne un nouveau checkpoint TinyGPT."""
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[PIPELINE] Device: {device}")

    tokenizer = CharTokenizer.build_default()
    texts = [ex.to_lm_text() for ex in examples]

    dataset = PlannerDataset(texts, tokenizer, block_size=block_size)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True, drop_last=False)

    model = TinyGPT(
        vocab_size=tokenizer.vocab_size,
        block_size=block_size,
        n_embd=n_embd,
        n_head=n_head,
        n_layer=n_layer,
        dropout=0.1,
    ).to(device)

    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)

    total_steps = epochs * len(loader)
    step = 0
    losses = []

    for epoch in range(1, epochs + 1):
        model.train()
        epoch_loss = 0.0

        for x, y in loader:
            x, y = x.to(device), y.to(device)

            logits = model(x)
            loss = F.cross_entropy(
                logits.reshape(-1, logits.size(-1)),
                y.reshape(-1),
                ignore_index=tokenizer.pad_id,
            )

            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

            step += 1
            epoch_loss += float(loss.item())

            if step % 100 == 0:
                ppl = math.exp(min(float(loss.item()), 20))
                print(f"  step {step}/{total_steps} | loss={loss.item():.4f} | ppl={ppl:.2f}")

        avg_loss = epoch_loss / max(len(loader), 1)
        losses.append(avg_loss)
        print(f"  epoch {epoch}/{epochs} | avg_loss={avg_loss:.4f}")

    # Sauvegarder
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model_state_dict": model.cpu().state_dict(),
        "tokenizer": {"stoi": tokenizer.stoi},
        "config": {
            "block_size": block_size,
            "n_embd": n_embd,
            "n_head": n_head,
            "n_layer": n_layer,
        },
        "training": {
            "epochs": epochs,
            "examples": len(examples),
            "batch_size": batch_size,
            "lr": lr,
            "final_loss": losses[-1] if losses else None,
            "trained_at": datetime.utcnow().isoformat(),
        },
    }
    torch.save(payload, output_path)
    tokenizer.save(output_path.with_suffix(".tokenizer.json"))
    print(f"[PIPELINE] Checkpoint candidat sauvegardé: {output_path}")

    return {
        "final_loss": losses[-1] if losses else None,
        "total_steps": step,
        "device": device,
    }


# ============================================
# ÉTAPE 4 : ÉVALUATION COMPARATIVE
# ============================================

EVAL_QUESTIONS = [
    ("récupère les tweets avec le #france", "collect_analyze_summarize", ["#france"]),
    ("compare #france et #minecraft", "compare", ["#france", "#minecraft"]),
    ("quel est le sentiment dominant sur #psg", "summarize", ["#psg"]),
    ("montre l'évolution temporelle de #love", "timeline", ["#love"]),
    ("donne des exemples de tweets sur @elonmusk", "examples", ["@elonmusk"]),
    ("génère un dashboard pour #ia", "dashboard", ["#ia"]),
    ("est-ce que la colère augmente sur #politique", "timeline", ["#politique"]),
    ("compare @openai et @nasa", "compare", ["@openai", "@nasa"]),
    ("analyse en profondeur #ecologie", "summarize", ["#ecologie"]),
    ("collecte les tweets de @netflixfr", "collect_analyze_summarize", ["@netflixfr"]),
    ("résume l'activité de #cinema sur 14 jours", "summarize", ["#cinema"]),
    ("quels tweets sont les plus tristes sur #france", "examples", ["#france"]),
    ("fais un dashboard comparatif entre #psg et #football", "compare", ["#psg", "#football"]),
    ("est-ce que la perception de #minecraft se dégrade", "timeline", ["#minecraft"]),
    ("crée la cible #tesla et récupère les tweets", "collect_analyze_summarize", ["#tesla"]),
]


def evaluate_checkpoint(checkpoint_path: Path) -> dict:
    """
    Évalue un checkpoint sur le jeu de test.
    Retourne un score composite basé sur :
    - % de plans JSON valides générés
    - % d'intents corrects
    - % de cibles correctement extraites
    """
    if not checkpoint_path.exists():
        return {"score": 0.0, "valid_json": 0, "correct_intent": 0, "correct_targets": 0}

    # Charger le modèle
    payload = torch.load(checkpoint_path, map_location="cpu")
    tokenizer_data = payload.get("tokenizer", {})
    stoi = {str(k): int(v) for k, v in tokenizer_data.get("stoi", {}).items()}
    itos = {idx: token for token, idx in stoi.items()}
    tokenizer = CharTokenizer(stoi=stoi, itos=itos)

    config = payload.get("config", {})
    model = TinyGPT(
        vocab_size=tokenizer.vocab_size,
        block_size=int(config.get("block_size", 512)),
        n_embd=int(config.get("n_embd", 192)),
        n_head=int(config.get("n_head", 4)),
        n_layer=int(config.get("n_layer", 4)),
        dropout=0.0,
    )
    model.load_state_dict(payload["model_state_dict"])
    model.eval()

    valid_json = 0
    correct_intent = 0
    correct_targets = 0
    total = len(EVAL_QUESTIONS)

    for question, expected_intent, expected_targets in EVAL_QUESTIONS:
        prompt = build_prompt(question)
        ids = tokenizer.encode(prompt, add_bos=True)
        idx = torch.tensor([ids], dtype=torch.long)

        with torch.no_grad():
            for _ in range(380):
                idx_cond = idx[:, -model.block_size:]
                logits = model(idx_cond)
                next_logits = logits[:, -1, :] / 0.8
                probs = torch.softmax(next_logits, dim=-1)
                next_id = torch.multinomial(probs, num_samples=1)
                idx = torch.cat([idx, next_id], dim=1)
                if int(next_id.item()) == tokenizer.eos_id:
                    break

        decoded = tokenizer.decode(idx[0].tolist())
        generated = decoded[len(prompt):]

        # Essayer de parser le JSON
        try:
            start = generated.find("{")
            end = generated.rfind("}")
            if start != -1 and end > start:
                plan = json.loads(generated[start:end + 1])
                valid_json += 1

                # Vérifier l'intent
                if plan.get("intent") == expected_intent:
                    correct_intent += 1

                # Vérifier les cibles
                plan_targets = [t.lower() for t in (plan.get("targets") or [])]
                expected_lower = [t.lower() for t in expected_targets]
                if set(expected_lower).issubset(set(plan_targets)):
                    correct_targets += 1
        except (json.JSONDecodeError, ValueError):
            pass

    score = (
        (valid_json / total) * 0.4
        + (correct_intent / total) * 0.35
        + (correct_targets / total) * 0.25
    )

    return {
        "score": round(score, 4),
        "valid_json": valid_json,
        "valid_json_pct": round(valid_json / total, 4),
        "correct_intent": correct_intent,
        "correct_intent_pct": round(correct_intent / total, 4),
        "correct_targets": correct_targets,
        "correct_targets_pct": round(correct_targets / total, 4),
        "total_questions": total,
    }


# ============================================
# ÉTAPE 5 : COMPARAISON ET REMPLACEMENT
# ============================================

def compare_and_replace(old_path: Path, new_path: Path) -> dict:
    """
    Compare l'ancien et le nouveau checkpoint.
    Remplace l'ancien seulement si le nouveau est meilleur.
    """
    print("\n[PIPELINE] Évaluation de l'ancien checkpoint...")
    old_eval = evaluate_checkpoint(old_path)
    print(f"  Ancien: score={old_eval['score']:.4f} | JSON={old_eval['valid_json_pct']:.0%} | intent={old_eval['correct_intent_pct']:.0%} | targets={old_eval['correct_targets_pct']:.0%}")

    print("[PIPELINE] Évaluation du nouveau checkpoint...")
    new_eval = evaluate_checkpoint(new_path)
    print(f"  Nouveau: score={new_eval['score']:.4f} | JSON={new_eval['valid_json_pct']:.0%} | intent={new_eval['correct_intent_pct']:.0%} | targets={new_eval['correct_targets_pct']:.0%}")

    improved = new_eval["score"] > old_eval["score"]

    result = {
        "old_score": old_eval["score"],
        "new_score": new_eval["score"],
        "improved": improved,
        "delta": round(new_eval["score"] - old_eval["score"], 4),
        "old_eval": old_eval,
        "new_eval": new_eval,
        "replaced": False,
        "evaluated_at": datetime.utcnow().isoformat(),
    }

    if improved:
        print(f"\n[PIPELINE] Le nouveau modèle est meilleur (+{result['delta']:.4f}). Remplacement...")
        # Backup de l'ancien
        if old_path.exists():
            shutil.copy2(old_path, CHECKPOINT_BACKUP)
            print(f"  Backup: {CHECKPOINT_BACKUP}")
        # Remplacer
        shutil.copy2(new_path, old_path)
        result["replaced"] = True
        print(f"  Nouveau checkpoint activé: {old_path}")
    else:
        print(f"\n[PIPELINE] Le nouveau modèle n'est PAS meilleur ({result['delta']:+.4f}). Conserve l'ancien.")

    # Nettoyer le candidat
    if new_path.exists():
        new_path.unlink()

    # Sauvegarder les résultats
    EVAL_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVAL_RESULTS_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[PIPELINE] Résultats: {EVAL_RESULTS_PATH}")

    return result


# ============================================
# MAIN
# ============================================

def run_pipeline(args):
    """Pipeline complet d'entraînement automatique."""
    print("=" * 60)
    print(f"[PIPELINE] Démarrage - {datetime.utcnow().isoformat()}")
    print("=" * 60)

    start = time.time()

    # Étape 1 : Export BDD
    print("\n--- ÉTAPE 1 : Export depuis la BDD ---")
    try:
        db_examples = export_training_data_from_db()
    except Exception as e:
        print(f"[PIPELINE] BDD indisponible ({e}), utilisation des données synthétiques uniquement")
        db_examples = []

    # Étape 2 : Fusion
    print("\n--- ÉTAPE 2 : Fusion des données ---")
    full_dataset = build_full_training_set(db_examples, n_synthetic=args.synthetic_examples)

    # Étape 3 : Entraînement
    print("\n--- ÉTAPE 3 : Entraînement ---")
    train_result = train_model(
        examples=full_dataset,
        output_path=CHECKPOINT_NEW,
        epochs=args.epochs,
        batch_size=args.batch_size,
        block_size=args.block_size,
        n_embd=args.n_embd,
        n_head=args.n_head,
        n_layer=args.n_layer,
        lr=args.lr,
    )

    # Étape 4 + 5 : Évaluation et remplacement conditionnel
    print("\n--- ÉTAPE 4 : Évaluation et comparaison ---")
    compare_result = compare_and_replace(CHECKPOINT_PATH, CHECKPOINT_NEW)

    elapsed = time.time() - start
    print(f"\n{'=' * 60}")
    print(f"[PIPELINE] Terminé en {elapsed:.1f}s")
    print(f"  Résultat: {'REMPLACÉ' if compare_result['replaced'] else 'CONSERVÉ'}")
    print(f"  Score: {compare_result['old_score']:.4f} → {compare_result['new_score']:.4f} ({compare_result['delta']:+.4f})")
    print("=" * 60)

    # Sauvegarder le timestamp dans Redis pour le timer frontend
    try:
        import redis
        r = redis.from_url(os.environ.get("REDIS_URL", "redis://redis:6379"))
        r.set("sentiflow:last_train_time", datetime.utcnow().isoformat())
    except Exception:
        pass


def parse_args():
    parser = argparse.ArgumentParser(description="Pipeline auto-entraînement TinyGPT planner")
    parser.add_argument("--epochs", type=int, default=6)
    parser.add_argument("--synthetic-examples", type=int, default=6000)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--block-size", type=int, default=512)
    parser.add_argument("--n-embd", type=int, default=192)
    parser.add_argument("--n-head", type=int, default=4)
    parser.add_argument("--n-layer", type=int, default=4)
    parser.add_argument("--lr", type=float, default=3e-4)
    return parser.parse_args()


if __name__ == "__main__":
    run_pipeline(parse_args())
