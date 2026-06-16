

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset

from backend.app.services.llm_from_scratch import TinyGPT
from backend.app.services.llm_tokenizer import CharTokenizer
from backend.app.services.llm_training_data import generate_synthetic_examples


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


def train(args):
    device = "cuda" if torch.cuda.is_available() and not args.cpu else "cpu"
    print(f"Device: {device}")

    tokenizer = CharTokenizer.build_default()
    examples = generate_synthetic_examples(n=args.examples, seed=args.seed)
    texts = [example.to_lm_text() for example in examples]

    dataset = PlannerDataset(texts, tokenizer, block_size=args.block_size)
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True, drop_last=False)

    model = TinyGPT(
        vocab_size=tokenizer.vocab_size,
        block_size=args.block_size,
        n_embd=args.n_embd,
        n_head=args.n_head,
        n_layer=args.n_layer,
        dropout=args.dropout,
    ).to(device)

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)

    total_steps = args.epochs * len(loader)
    step = 0

    for epoch in range(1, args.epochs + 1):
        model.train()
        epoch_loss = 0.0

        for x, y in loader:
            x = x.to(device)
            y = y.to(device)

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

            if step % args.log_every == 0:
                ppl = math.exp(min(float(loss.item()), 20))
                print(f"step {step}/{total_steps} | epoch {epoch} | loss={loss.item():.4f} | ppl={ppl:.2f}")

        avg_loss = epoch_loss / max(len(loader), 1)
        print(f"epoch {epoch}/{args.epochs} | avg_loss={avg_loss:.4f}")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "model_state_dict": model.cpu().state_dict(),
        "tokenizer": {"stoi": tokenizer.stoi},
        "config": {
            "block_size": args.block_size,
            "n_embd": args.n_embd,
            "n_head": args.n_head,
            "n_layer": args.n_layer,
        },
        "training": {
            "epochs": args.epochs,
            "examples": args.examples,
            "batch_size": args.batch_size,
            "lr": args.lr,
        },
    }

    torch.save(payload, output_path)
    tokenizer.save(output_path.with_suffix(".tokenizer.json"))
    print(f"Checkpoint sauvegardé : {output_path}")

    # Petit test rapide.
    test_questions = [
        "récupère les tweets avec le #france",
        "compare #france et #minecraft",
        "montre l'évolution temporelle de #love",
    ]
    print("\nExemples d'entrées apprises par le dataset :")
    for q in test_questions:
        print("-", q)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="backend/app/ml/sentiflow_tiny_llm.pt")
    parser.add_argument("--epochs", type=int, default=6)
    parser.add_argument("--examples", type=int, default=8000)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--block-size", type=int, default=512)
    parser.add_argument("--n-embd", type=int, default=192)
    parser.add_argument("--n-head", type=int, default=4)
    parser.add_argument("--n-layer", type=int, default=4)
    parser.add_argument("--dropout", type=float, default=0.1)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--log-every", type=int, default=50)
    parser.add_argument("--cpu", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    train(parse_args())
