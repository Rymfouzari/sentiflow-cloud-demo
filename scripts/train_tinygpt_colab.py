"""
=============================================================
ENTRAÎNEMENT TinyGPT SentiFlow - À exécuter sur Google Colab
=============================================================

1. Ouvre Google Colab (colab.research.google.com)
2. Runtime → Change runtime type → GPU (T4)
3. Copie-colle tout ce code dans une cellule
4. Exécute
5. Télécharge le fichier .pt généré
6. Mets-le dans backend/app/ml/sentiflow_tiny_llm.pt

Temps : ~20-30 min sur GPU T4
"""

import json
import math
import os
import random
import string
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader

# ============================================
# 1. TOKENIZER (CharTokenizer from scratch)
# ============================================

SPECIAL_TOKENS = ["<pad>", "<bos>", "<eos>", "<unk>"]

DEFAULT_ALPHABET = (
    string.ascii_letters
    + string.digits
    + string.punctuation
    + " \n\t"
    + "àâäçéèêëîïôöùûüÿœæÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸŒÆ"
    + "€'«»—–…"
)


class CharTokenizer:
    def __init__(self, stoi, itos):
        self.stoi = stoi
        self.itos = itos

    @classmethod
    def build_default(cls):
        chars = []
        for ch in DEFAULT_ALPHABET:
            if ch not in chars:
                chars.append(ch)
        vocab = SPECIAL_TOKENS + chars
        stoi = {token: index for index, token in enumerate(vocab)}
        itos = {index: token for token, index in stoi.items()}
        return cls(stoi=stoi, itos=itos)

    @property
    def pad_id(self): return self.stoi["<pad>"]
    @property
    def bos_id(self): return self.stoi["<bos>"]
    @property
    def eos_id(self): return self.stoi["<eos>"]
    @property
    def unk_id(self): return self.stoi["<unk>"]
    @property
    def vocab_size(self): return len(self.stoi)

    def encode(self, text, add_bos=False, add_eos=False):
        ids = []
        if add_bos:
            ids.append(self.bos_id)
        ids.extend(self.stoi.get(ch, self.unk_id) for ch in text)
        if add_eos:
            ids.append(self.eos_id)
        return ids

    def decode(self, ids):
        chars = []
        for token_id in ids:
            token = self.itos.get(int(token_id), "<unk>")
            if token in SPECIAL_TOKENS:
                continue
            chars.append(token)
        return "".join(chars)


# ============================================
# 2. MODÈLE TinyGPT (Transformer from scratch)
# ============================================

class TinyGPT(nn.Module):
    def __init__(self, vocab_size, block_size=512, n_embd=192, n_head=4, n_layer=4, dropout=0.1):
        super().__init__()
        self.block_size = block_size
        self.token_embedding = nn.Embedding(vocab_size, n_embd)
        self.position_embedding = nn.Embedding(block_size, n_embd)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=n_embd, nhead=n_head,
            dim_feedforward=4 * n_embd, dropout=dropout,
            batch_first=True, activation="gelu",
        )
        self.blocks = nn.TransformerEncoder(encoder_layer, num_layers=n_layer)
        self.ln_f = nn.LayerNorm(n_embd)
        self.lm_head = nn.Linear(n_embd, vocab_size, bias=False)

    def forward(self, idx):
        B, T = idx.shape
        if T > self.block_size:
            idx = idx[:, -self.block_size:]
            T = self.block_size
        positions = torch.arange(T, device=idx.device).unsqueeze(0)
        x = self.token_embedding(idx) + self.position_embedding(positions)
        causal_mask = torch.triu(torch.ones(T, T, device=idx.device, dtype=torch.bool), diagonal=1)
        x = self.blocks(x, mask=causal_mask)
        x = self.ln_f(x)
        return self.lm_head(x)


# ============================================
# 3. DONNÉES D'ENTRAÎNEMENT (chargées depuis JSON)
# ============================================

def build_prompt(question):
    return (
        "Tu es le planner LLM de SentiFlow. "
        "Transforme la demande utilisateur en JSON strict.\n"
        "Actions autorisées: create_missing_targets, collect_tweets, "
        "analyze_sentiments, summarize, compare_targets, get_timeline, "
        "get_examples, generate_dashboard, query_database.\n"
        f"Demande: {question}\n"
        "JSON:"
    )


def load_templates(json_path="planner_training_templates.json"):
    """Charge les templates depuis le fichier JSON séparé."""
    # Chercher le fichier dans plusieurs emplacements possibles
    paths = [
        json_path,
        f"data/{json_path}",
        f"/app/data/{json_path}",
        os.path.join(os.path.dirname(__file__), "..", "data", json_path),
    ]
    for p in paths:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError(f"Templates non trouvés: {paths}")


def generate_training_data(n=10000, seed=42):
    templates_data = load_templates()

    TARGET_POOL = templates_data["targets"]
    SENTIMENTS = templates_data["sentiments"]
    templates = templates_data["templates"]
    intents_config = templates_data["intents"]

    rng = random.Random(seed)
    examples = []

    def _target_type(t):
        return "account" if t.startswith("@") else "hashtag"

    def _plan(intent_key, targets, days=7, sentiment_filter=None):
        cfg = intents_config[intent_key]
        return {
            "intent": cfg["intent"],
            "targets": targets,
            "target_types": {t: _target_type(t) for t in targets},
            "days": days,
            "actions": cfg["actions"],
            "dashboard": cfg["dashboard"],
            "sentiment_filter": sentiment_filter,
            "force_refresh": cfg["force_refresh"],
        }

    kinds = ["collect", "summary", "summary", "compare", "timeline", "database", "examples"]

    for _ in range(n):
        kind = rng.choice(kinds)
        a, b = rng.sample(TARGET_POOL, 2)
        days = rng.choice([1, 3, 7, 14, 30])
        sentiment = rng.choice(SENTIMENTS)

        if kind == "collect":
            text = rng.choice(templates["collect"]).format(a=a, days=days, sentiment=sentiment)
            plan = _plan("collect", [a], days=days)
        elif kind == "summary":
            text = rng.choice(templates["summary"]).format(a=a, days=days, sentiment=sentiment)
            plan = _plan("summary", [a], days=days)
        elif kind == "compare":
            text = rng.choice(templates["compare"]).format(a=a, b=b, days=days)
            plan = _plan("compare", [a, b], days=days)
        elif kind == "timeline":
            text = rng.choice(templates["timeline"]).format(a=a, days=days)
            plan = _plan("timeline", [a], days=days)
        elif kind == "database":
            text = rng.choice(templates["database"])
            plan = _plan("database", [])
        else:
            text = rng.choice(templates["examples"]).format(a=a, sentiment=sentiment)
            plan = _plan("examples", [a], sentiment_filter=sentiment)

        examples.append((text, plan))

    return examples


# ============================================
# 4. DATASET PYTORCH
# ============================================

class PlannerDataset(Dataset):
    def __init__(self, examples, tokenizer, block_size=512):
        self.data = []
        for text, plan in examples:
            prompt = build_prompt(text)
            completion = json.dumps(plan, ensure_ascii=False, separators=(",", ":"))
            full_text = prompt + completion
            ids = tokenizer.encode(full_text, add_bos=True, add_eos=True)
            if len(ids) <= block_size:
                self.data.append(ids)

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        ids = self.data[idx]
        x = torch.tensor(ids[:-1], dtype=torch.long)
        y = torch.tensor(ids[1:], dtype=torch.long)
        return x, y


def collate_fn(batch):
    max_len = max(len(x) for x, _ in batch)
    xs, ys = [], []
    for x, y in batch:
        pad_len = max_len - len(x)
        xs.append(torch.cat([x, torch.zeros(pad_len, dtype=torch.long)]))
        ys.append(torch.cat([y, torch.full((pad_len,), -100, dtype=torch.long)]))
    return torch.stack(xs), torch.stack(ys)


# ============================================
# 5. ENTRAÎNEMENT
# ============================================

def train():
    print("=" * 60)
    print("🚀 Fine-tuning TinyGPT SentiFlow (à partir du checkpoint lseillier)")
    print("=" * 60)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")

    # Tokenizer
    tokenizer = CharTokenizer.build_default()
    print(f"Vocab size: {tokenizer.vocab_size}")

    # Charger le checkpoint existant de lseillier
    checkpoint_path = "sentiflow_tiny_llm.pt"
    if os.path.exists(checkpoint_path):
        print(f"📦 Chargement du checkpoint existant: {checkpoint_path}")
        payload = torch.load(checkpoint_path, map_location="cpu")
        # Récupérer le tokenizer du checkpoint
        tokenizer_payload = payload.get("tokenizer")
        if tokenizer_payload:
            stoi = {str(k): int(v) for k, v in tokenizer_payload["stoi"].items()}
            itos = {index: token for token, index in stoi.items()}
            tokenizer = CharTokenizer(stoi=stoi, itos=itos)
            print(f"  Tokenizer chargé (vocab={tokenizer.vocab_size})")
        config = payload.get("config", {})
    else:
        print("⚠️ Pas de checkpoint trouvé, entraînement from scratch")
        print("   Mets le fichier sentiflow_tiny_llm.pt dans ce dossier")
        config = {}

    # Données (nouvelles + anciennes)
    print("Génération des données d'entraînement (avec query_database, #bts, etc.)...")
    examples = generate_training_data(n=10000)
    print(f"Exemples: {len(examples)}")

    # Dataset
    block_size = int(config.get("block_size", 512))
    dataset = PlannerDataset(examples, tokenizer, block_size=block_size)
    print(f"Séquences valides: {len(dataset)}")

    dataloader = DataLoader(dataset, batch_size=32, shuffle=True, collate_fn=collate_fn)

    # Modèle
    model = TinyGPT(
        vocab_size=tokenizer.vocab_size,
        block_size=block_size,
        n_embd=int(config.get("n_embd", 192)),
        n_head=int(config.get("n_head", 4)),
        n_layer=int(config.get("n_layer", 4)),
        dropout=0.1,
    ).to(device)

    # Charger les poids existants
    if os.path.exists(checkpoint_path):
        model.load_state_dict(payload["model_state_dict"])
        print("  ✅ Poids chargés depuis le checkpoint")

    params = sum(p.numel() for p in model.parameters())
    print(f"Paramètres: {params:,}")

    # Optimiseur (learning rate plus bas pour fine-tuning)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4, weight_decay=0.01)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=15)

    # Training loop (moins d'epochs car on fine-tune)
    epochs = 15
    print(f"\nDébut fine-tuning ({epochs} epochs, lr=1e-4)...")
    start = time.time()

    for epoch in range(epochs):
        model.train()
        total_loss = 0
        n_batches = 0

        for x, y in dataloader:
            x, y = x.to(device), y.to(device)
            logits = model(x)
            loss = nn.functional.cross_entropy(
                logits.view(-1, tokenizer.vocab_size),
                y.view(-1),
                ignore_index=-100,
            )
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

            total_loss += loss.item()
            n_batches += 1

        scheduler.step()
        avg_loss = total_loss / n_batches

        if (epoch + 1) % 3 == 0 or epoch == 0:
            elapsed = time.time() - start
            print(f"  Epoch {epoch+1:2d}/{epochs} | Loss: {avg_loss:.4f} | Time: {elapsed:.0f}s")

    total_time = time.time() - start
    print(f"\n✅ Entraînement terminé en {total_time:.0f}s")
    print(f"   Loss finale: {avg_loss:.4f}")

    # Sauvegarder
    checkpoint = {
        "model_state_dict": model.state_dict(),
        "tokenizer": {"stoi": tokenizer.stoi},
        "config": {
            "block_size": 512,
            "n_embd": 192,
            "n_head": 4,
            "n_layer": 4,
        },
        "training_info": {
            "epochs": epochs,
            "examples": len(examples),
            "final_loss": avg_loss,
            "time_seconds": total_time,
        },
    }

    save_path = "sentiflow_tiny_llm.pt"
    torch.save(checkpoint, save_path)
    size_mb = os.path.getsize(save_path) / 1024 / 1024
    print(f"   Checkpoint: {save_path} ({size_mb:.1f} MB)")
    print(f"\n📥 Télécharge ce fichier et place-le dans:")
    print(f"   backend/app/ml/sentiflow_tiny_llm.pt")

    # Test rapide
    print("\n🧪 Test rapide:")
    model.eval()
    test_questions = [
        "quel est le sentiment sur #bts ?",
        "compare #france et #trump",
        "récupère les tweets de @bts_twt",
        "quels sont mes cibles",
    ]
    for q in test_questions:
        prompt = build_prompt(q)
        ids = tokenizer.encode(prompt, add_bos=True)
        idx = torch.tensor([ids], dtype=torch.long).to(device)
        with torch.no_grad():
            for _ in range(200):
                idx_cond = idx[:, -model.block_size:]
                logits = model(idx_cond)
                next_logits = logits[:, -1, :] / 0.7
                probs = torch.softmax(next_logits, dim=-1)
                next_id = torch.multinomial(probs, num_samples=1)
                idx = torch.cat([idx, next_id], dim=1)
                if int(next_id.item()) == tokenizer.eos_id:
                    break
        decoded = tokenizer.decode(idx[0].tolist())
        generated = decoded[len(prompt):]
        print(f"  Q: {q}")
        print(f"  → {generated[:150]}")
        print()


if __name__ == "__main__":
    train()
