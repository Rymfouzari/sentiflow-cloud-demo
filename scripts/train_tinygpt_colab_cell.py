"""
CELLULE UNIQUE COLAB - Fine-tuning TinyGPT SentiFlow
Upload d'abord : sentiflow_tiny_llm.pt + planner_training_templates.json
"""
import json, math, os, random, string, time
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader

# === TOKENIZER ===
SPECIAL_TOKENS = ["<pad>", "<bos>", "<eos>", "<unk>"]
DEFAULT_ALPHABET = (string.ascii_letters + string.digits + string.punctuation
    + " \n\t" + "àâäçéèêëîïôöùûüÿœæÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸŒÆ" + "€'«»—–…")

class CharTokenizer:
    def __init__(self, stoi, itos):
        self.stoi = stoi
        self.itos = itos
    @classmethod
    def build_default(cls):
        chars = list(dict.fromkeys(DEFAULT_ALPHABET))
        vocab = SPECIAL_TOKENS + chars
        stoi = {t: i for i, t in enumerate(vocab)}
        itos = {i: t for t, i in stoi.items()}
        return cls(stoi, itos)
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
        if add_bos: ids.append(self.bos_id)
        ids.extend(self.stoi.get(ch, self.unk_id) for ch in text)
        if add_eos: ids.append(self.eos_id)
        return ids
    def decode(self, ids):
        return "".join(self.itos.get(int(i), "") for i in ids if self.itos.get(int(i), "") not in SPECIAL_TOKENS)

# === MODELE ===
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
        x = self.blocks(x, mask=mask)
        return self.lm_head(self.ln_f(x))

# === DONNEES ===
def build_prompt(q):
    return (f"Tu es le planner LLM de SentiFlow. Transforme la demande utilisateur en JSON strict.\n"
            f"Actions autorisées: create_missing_targets, collect_tweets, analyze_sentiments, summarize, compare_targets, get_timeline, get_examples, generate_dashboard, query_database.\n"
            f"Demande: {q}\nJSON:")

def load_templates():
    for p in ["planner_training_templates.json", "/content/planner_training_templates.json"]:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError("Upload planner_training_templates.json!")

def generate_training_data(n=10000, seed=42):
    data = load_templates()
    targets, sentiments, templates, intents = data["targets"], data["sentiments"], data["templates"], data["intents"]
    rng = random.Random(seed)
    examples = []
    def _plan(key, tgts, days=7, sf=None):
        cfg = intents[key]
        return {"intent":cfg["intent"],"targets":tgts,"target_types":{t:("account" if t.startswith("@") else "hashtag") for t in tgts},"days":days,"actions":cfg["actions"],"dashboard":cfg["dashboard"],"sentiment_filter":sf,"force_refresh":cfg["force_refresh"]}
    for _ in range(n):
        kind = rng.choice(["collect","summary","summary","compare","timeline","database","examples"])
        a, b = rng.sample(targets, 2)
        days = rng.choice([1,3,7,14,30])
        sent = rng.choice(sentiments)
        if kind == "collect":
            text = rng.choice(templates["collect"]).format(a=a, days=days, sentiment=sent)
            plan = _plan("collect", [a], days)
        elif kind == "summary":
            text = rng.choice(templates["summary"]).format(a=a, days=days, sentiment=sent)
            plan = _plan("summary", [a], days)
        elif kind == "compare":
            text = rng.choice(templates["compare"]).format(a=a, b=b, days=days)
            plan = _plan("compare", [a, b], days)
        elif kind == "timeline":
            text = rng.choice(templates["timeline"]).format(a=a, days=days)
            plan = _plan("timeline", [a], days)
        elif kind == "database":
            text = rng.choice(templates["database"])
            plan = _plan("database", [])
        else:
            text = rng.choice(templates["examples"]).format(a=a, sentiment=sent)
            plan = _plan("examples", [a], sf=sent)
        examples.append((text, plan))
    return examples

# === DATASET ===
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

# === ENTRAINEMENT ===
print("="*60)
print("🚀 Fine-tuning TinyGPT SentiFlow")
print("="*60)

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Device: {device}")

tokenizer = CharTokenizer.build_default()
checkpoint_path = "sentiflow_tiny_llm.pt"
config = {}

if os.path.exists(checkpoint_path):
    print(f"📦 Chargement checkpoint: {checkpoint_path}")
    payload = torch.load(checkpoint_path, map_location="cpu")
    tok_data = payload.get("tokenizer")
    if tok_data:
        stoi = {str(k):int(v) for k,v in tok_data["stoi"].items()}
        itos = {i:t for t,i in stoi.items()}
        tokenizer = CharTokenizer(stoi, itos)
        print(f"  Tokenizer: vocab={tokenizer.vocab_size}")
    config = payload.get("config", {})
else:
    print("⚠️ Pas de checkpoint, entraînement from scratch")
    payload = None

print("Génération données...")
examples = generate_training_data(n=10000)
print(f"Exemples: {len(examples)}")

block_size = int(config.get("block_size", 512))
dataset = PlannerDataset(examples, tokenizer, block_size)
print(f"Séquences valides: {len(dataset)}")
dataloader = DataLoader(dataset, batch_size=32, shuffle=True, collate_fn=collate_fn)

model = TinyGPT(tokenizer.vocab_size, block_size, int(config.get("n_embd",192)), int(config.get("n_head",4)), int(config.get("n_layer",4)), 0.1).to(device)
if payload:
    model.load_state_dict(payload["model_state_dict"])
    print("✅ Poids chargés")

print(f"Params: {sum(p.numel() for p in model.parameters()):,}")

optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4, weight_decay=0.01)
scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=15)

epochs = 15
print(f"\nFine-tuning ({epochs} epochs)...")
start = time.time()

for epoch in range(epochs):
    model.train()
    total_loss, nb = 0, 0
    for x, y in dataloader:
        x, y = x.to(device), y.to(device)
        loss = nn.functional.cross_entropy(model(x).view(-1, tokenizer.vocab_size), y.view(-1), ignore_index=-100)
        optimizer.zero_grad(); loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        total_loss += loss.item(); nb += 1
    scheduler.step()
    avg = total_loss/nb
    if (epoch+1)%3==0 or epoch==0:
        print(f"  Epoch {epoch+1:2d}/{epochs} | Loss: {avg:.4f} | {time.time()-start:.0f}s")

print(f"\n✅ Terminé en {time.time()-start:.0f}s | Loss: {avg:.4f}")

torch.save({"model_state_dict":model.state_dict(),"tokenizer":{"stoi":tokenizer.stoi},"config":{"block_size":block_size,"n_embd":int(config.get("n_embd",192)),"n_head":int(config.get("n_head",4)),"n_layer":int(config.get("n_layer",4))},"training_info":{"epochs":epochs,"examples":len(examples),"final_loss":avg}}, "sentiflow_tiny_llm.pt")
print(f"📦 Sauvegardé: sentiflow_tiny_llm.pt ({os.path.getsize('sentiflow_tiny_llm.pt')/1024/1024:.1f} MB)")

# === TEST ===
print("\n🧪 Test:")
model.eval()
for q in ["quel est le sentiment sur #bts ?","compare #france et #trump","récupère les tweets de @bts_twt","quels sont mes cibles"]:
    ids = tokenizer.encode(build_prompt(q), add_bos=True)
    idx = torch.tensor([ids], dtype=torch.long).to(device)
    with torch.no_grad():
        for _ in range(200):
            logits = model(idx[:, -model.block_size:])
            nid = torch.multinomial(torch.softmax(logits[:,-1,:]/0.7, dim=-1), 1)
            idx = torch.cat([idx, nid], dim=1)
            if int(nid.item()) == tokenizer.eos_id: break
    out = tokenizer.decode(idx[0].tolist())[len(build_prompt(q)):]
    print(f"  Q: {q}\n  → {out[:120]}\n")

# Télécharger
from google.colab import files
files.download("sentiflow_tiny_llm.pt")
