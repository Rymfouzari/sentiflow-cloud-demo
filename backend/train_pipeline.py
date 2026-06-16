"""
Pipeline complet : génère données BDD → entraîne TinyGPT → sauvegarde.
Lance avec: docker compose exec api python /app/backend/train_pipeline.py
Temps estimé : ~30-60 min sur CPU
"""
import json, os, random, string, time, sys
sys.path.insert(0, "/app")

import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader

# === ÉTAPE 1 : GÉNÉRER LES DONNÉES DEPUIS LA BDD ===
print("=" * 60)
print("📊 ÉTAPE 1 : Génération des données depuis la BDD")
print("=" * 60)

from backend.app.database import SessionLocal
from backend.app.models.target import Target
from backend.app.models.tweet import Tweet
from sqlalchemy import func

db = SessionLocal()
real_targets = [t.name.lower() for t in db.query(Target).all()]
real_sentiments = [s for s, in db.query(Tweet.sentiment).filter(Tweet.sentiment.isnot(None)).distinct().all()]
db.close()

base_targets = [
    "#france", "#minecraft", "#love", "#trump", "#psg", "#ia", "#openai",
    "#football", "#politique", "#cinema", "#music", "#paris", "#ecologie",
    "#bts", "#kpop", "#crypto", "#sport", "#tech",
    "@elonmusk", "@openai", "@nasa", "@bts_twt", "@netflixfr",
]
all_targets = list(dict.fromkeys(real_targets + base_targets))
all_sentiments = list(dict.fromkeys(real_sentiments + ["joie", "colere", "tristesse", "peur", "surprise", "amour", "neutre"]))

print(f"  Cibles réelles: {real_targets}")
print(f"  Total cibles: {len(all_targets)}")
print(f"  Sentiments: {all_sentiments}")

# === ÉTAPE 2 : CONSTRUIRE LE DATASET ===
print("\n" + "=" * 60)
print("🔧 ÉTAPE 2 : Construction du dataset d'entraînement")
print("=" * 60)

SPECIAL_TOKENS = ["<pad>", "<bos>", "<eos>", "<unk>"]
DEFAULT_ALPHABET = (string.ascii_letters + string.digits + string.punctuation
    + " \n\t" + "àâäçéèêëîïôöùûüÿœæÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸŒÆ" + "€'«»—–…")

class CharTokenizer:
    def __init__(self, stoi, itos):
        self.stoi, self.itos = stoi, itos
    @classmethod
    def build_default(cls):
        chars = list(dict.fromkeys(DEFAULT_ALPHABET))
        vocab = SPECIAL_TOKENS + chars
        stoi = {t:i for i,t in enumerate(vocab)}
        return cls(stoi, {i:t for t,i in stoi.items()})
    @property
    def vocab_size(self): return len(self.stoi)
    @property
    def bos_id(self): return self.stoi["<bos>"]
    @property
    def eos_id(self): return self.stoi["<eos>"]
    @property
    def unk_id(self): return self.stoi["<unk>"]
    def encode(self, text, add_bos=False, add_eos=False):
        ids = []
        if add_bos: ids.append(self.bos_id)
        ids.extend(self.stoi.get(ch, self.unk_id) for ch in text)
        if add_eos: ids.append(self.eos_id)
        return ids
    def decode(self, ids):
        return "".join(self.itos.get(int(i),"") for i in ids if self.itos.get(int(i),"") not in SPECIAL_TOKENS)

def build_prompt(q):
    return (f"Tu es le planner LLM de SentiFlow. Transforme la demande utilisateur en JSON strict.\n"
            f"Actions autorisées: create_missing_targets, collect_tweets, analyze_sentiments, summarize, "
            f"compare_targets, get_timeline, get_examples, generate_dashboard, query_database.\n"
            f"Demande: {q}\nJSON:")

# Templates ÉQUILIBRÉS (fix du problème database)
templates = {
    "collect": ["récupère les tweets avec {a}", "collecte {a}", "lance une collecte sur {a}",
                "ajoute {a} et récupère les tweets", "va chercher les tweets de {a}",
                "crée la cible {a} et analyse", "je veux les tweets de {a}"],
    "summary": ["résume {a}", "sentiment sur {a}", "analyse {a}", "c'est quoi le sentiment de {a}",
                "quel est le sentiment dominant sur {a}", "comment les gens réagissent à {a}",
                "les gens pensent quoi de {a}", "avis sur {a}", "synthèse de {a}",
                "donne moi le bilan sentiment de {a}", "signaux importants sur {a}"],
    "compare": ["compare {a} et {b}", "différence entre {a} et {b}", "{a} vs {b}",
                "qui est le plus positif entre {a} et {b}", "lequel est mieux {a} ou {b}"],
    "timeline": ["évolution de {a}", "tendance sur {a}", "est-ce que ça augmente sur {a}",
                 "comment évolue {a}", "la perception de {a} se dégrade ?"],
    "database": ["quels sont mes cibles", "combien de tweets j'ai", "mes données en base",
                 "répartition des langues", "statistiques globales"],
    "examples": ["exemples de tweets sur {a}", "montre des tweets de {a}",
                 "tweets les plus {sentiment} sur {a}"],
}

intents_config = {
    "collect": {"intent":"collect_analyze_summarize","actions":["create_missing_targets","collect_tweets","analyze_sentiments","summarize","generate_dashboard"],"dashboard":True,"force_refresh":True},
    "summary": {"intent":"summarize","actions":["analyze_sentiments","summarize","generate_dashboard"],"dashboard":True,"force_refresh":False},
    "compare": {"intent":"compare","actions":["analyze_sentiments","compare_targets","generate_dashboard"],"dashboard":True,"force_refresh":False},
    "timeline": {"intent":"timeline","actions":["analyze_sentiments","get_timeline","generate_dashboard"],"dashboard":True,"force_refresh":False},
    "database": {"intent":"query_database","actions":["query_database"],"dashboard":False,"force_refresh":False},
    "examples": {"intent":"examples","actions":["analyze_sentiments","get_examples"],"dashboard":False,"force_refresh":False},
}

# Distribution ÉQUILIBRÉE : summary dominant, database rare
kinds_distribution = ["collect"]*15 + ["summary"]*30 + ["compare"]*20 + ["timeline"]*15 + ["database"]*10 + ["examples"]*10

rng = random.Random(42)
examples = []
for _ in range(10000):
    kind = rng.choice(kinds_distribution)
    a, b = rng.sample(all_targets, 2)
    days = rng.choice([1,3,7,14,30])
    sent = rng.choice(all_sentiments)
    cfg = intents_config[kind]
    
    text = rng.choice(templates[kind]).format(a=a, b=b, days=days, sentiment=sent)
    plan = {"intent":cfg["intent"],"targets":([a,b] if kind=="compare" else ([] if kind=="database" else [a])),
            "target_types":{t:("account" if t.startswith("@") else "hashtag") for t in ([a,b] if kind=="compare" else [a])},
            "days":days,"actions":cfg["actions"],"dashboard":cfg["dashboard"],
            "sentiment_filter":(sent if kind=="examples" else None),"force_refresh":cfg["force_refresh"]}
    if kind == "database":
        plan["targets"] = []
        plan["target_types"] = {}
    examples.append((text, plan))

print(f"  Exemples générés: {len(examples)}")

# === ÉTAPE 3 : CHARGER CHECKPOINT + ENTRAÎNER ===
print("\n" + "=" * 60)
print("🚀 ÉTAPE 3 : Entraînement TinyGPT")
print("=" * 60)

device = "cpu"
print(f"  Device: {device} (CPU, ~30-60 min)")

# Charger tokenizer depuis le checkpoint
checkpoint_path = "/app/backend/app/ml/sentiflow_tiny_llm.pt"
tokenizer = CharTokenizer.build_default()
config = {}

if os.path.exists(checkpoint_path):
    print(f"  📦 Checkpoint trouvé: {checkpoint_path}")
    payload = torch.load(checkpoint_path, map_location="cpu")
    tok_data = payload.get("tokenizer")
    if tok_data:
        stoi = {str(k):int(v) for k,v in tok_data["stoi"].items()}
        tokenizer = CharTokenizer(stoi, {i:t for t,i in stoi.items()})
    config = payload.get("config", {})
else:
    print("  ⚠️ Pas de checkpoint, entraînement from scratch")
    payload = None

# Dataset
class PlannerDataset(Dataset):
    def __init__(self, examples, tokenizer, block_size=512):
        self.data = []
        for text, plan in examples:
            full = build_prompt(text) + json.dumps(plan, ensure_ascii=False, separators=(",",":"))
            ids = tokenizer.encode(full, add_bos=True, add_eos=True)
            if len(ids) <= block_size: self.data.append(ids)
    def __len__(self): return len(self.data)
    def __getitem__(self, idx):
        ids = self.data[idx]
        return torch.tensor(ids[:-1], dtype=torch.long), torch.tensor(ids[1:], dtype=torch.long)

def collate_fn(batch):
    ml = max(len(x) for x,_ in batch)
    xs = [torch.cat([x, torch.zeros(ml-len(x), dtype=torch.long)]) for x,_ in batch]
    ys = [torch.cat([y, torch.full((ml-len(y),), -100, dtype=torch.long)]) for _,y in batch]
    return torch.stack(xs), torch.stack(ys)

block_size = int(config.get("block_size", 512))
dataset = PlannerDataset(examples, tokenizer, block_size)
print(f"  Séquences: {len(dataset)}")
dataloader = DataLoader(dataset, batch_size=16, shuffle=True, collate_fn=collate_fn)

# Modèle
class TinyGPT(nn.Module):
    def __init__(self, vocab_size, block_size=512, n_embd=192, n_head=4, n_layer=4, dropout=0.1):
        super().__init__()
        self.block_size = block_size
        self.token_embedding = nn.Embedding(vocab_size, n_embd)
        self.position_embedding = nn.Embedding(block_size, n_embd)
        layer = nn.TransformerEncoderLayer(d_model=n_embd, nhead=n_head, dim_feedforward=4*n_embd, dropout=dropout, batch_first=True, activation="gelu")
        self.blocks = nn.TransformerEncoder(layer, num_layers=n_layer)
        self.ln_f = nn.LayerNorm(n_embd)
        self.lm_head = nn.Linear(n_embd, vocab_size, bias=False)
    def forward(self, idx):
        B, T = idx.shape
        if T > self.block_size: idx = idx[:, -self.block_size:]; T = self.block_size
        pos = torch.arange(T, device=idx.device).unsqueeze(0)
        x = self.token_embedding(idx) + self.position_embedding(pos)
        mask = torch.triu(torch.ones(T, T, device=idx.device, dtype=torch.bool), diagonal=1)
        return self.lm_head(self.ln_f(self.blocks(x, mask=mask)))

model = TinyGPT(tokenizer.vocab_size, block_size, int(config.get("n_embd",192)), int(config.get("n_head",4)), int(config.get("n_layer",4)), 0.1)
if payload:
    model.load_state_dict(payload["model_state_dict"])
    print("  ✅ Poids chargés")
print(f"  Params: {sum(p.numel() for p in model.parameters()):,}")

# Entraînement (10 epochs pour CPU)
optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4, weight_decay=0.01)
epochs = 10
print(f"\n  Fine-tuning ({epochs} epochs sur CPU)...")
start = time.time()

for epoch in range(epochs):
    model.train()
    total_loss, nb = 0, 0
    for x, y in dataloader:
        loss = nn.functional.cross_entropy(model(x).view(-1, tokenizer.vocab_size), y.view(-1), ignore_index=-100)
        optimizer.zero_grad(); loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        total_loss += loss.item(); nb += 1
    avg = total_loss/nb
    elapsed = time.time()-start
    print(f"  Epoch {epoch+1:2d}/{epochs} | Loss: {avg:.4f} | {elapsed:.0f}s")

# Sauvegarder
save_path = "/app/backend/app/ml/sentiflow_tiny_llm.pt"
torch.save({"model_state_dict":model.state_dict(),"tokenizer":{"stoi":tokenizer.stoi},
    "config":{"block_size":block_size,"n_embd":int(config.get("n_embd",192)),"n_head":int(config.get("n_head",4)),"n_layer":int(config.get("n_layer",4))},
    "training_info":{"epochs":epochs,"examples":len(examples),"final_loss":avg,"balanced":True}}, save_path)
print(f"\n✅ Sauvegardé: {save_path} ({os.path.getsize(save_path)/1024/1024:.1f} MB)")

# Test
print("\n🧪 Test:")
model.eval()
for q in ["sentiment sur #bts", "compare #france et #trump", "récupère @bts_twt", "quels sont mes cibles", "évolution de #football"]:
    ids = tokenizer.encode(build_prompt(q), add_bos=True)
    idx = torch.tensor([ids], dtype=torch.long)
    with torch.no_grad():
        for _ in range(200):
            logits = model(idx[:, -model.block_size:])
            nid = torch.multinomial(torch.softmax(logits[:,-1,:]/0.7, dim=-1), 1)
            idx = torch.cat([idx, nid], dim=1)
            if int(nid.item()) == tokenizer.eos_id: break
    out = tokenizer.decode(idx[0].tolist())[len(build_prompt(q)):]
    print(f"  Q: {q}")
    print(f"  → {out[:120]}\n")

print("=" * 60)
print("✅ PIPELINE TERMINÉ")
print("=" * 60)
