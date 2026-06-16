"""Pipeline d'entraînement du modèle de sentiment"""
import torch
from torch.utils.data import DataLoader, Dataset
from transformers import AutoTokenizer, AutoModelForSequenceClassification, AdamW
from sklearn.model_selection import train_test_split
import pandas as pd
from pathlib import Path

from features.preprocessing import prepare_training_data


class SentimentDataset(Dataset):
    def __init__(self, texts, labels, tokenizer, max_length=128):
        self.texts = texts
        self.labels = labels
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.label_map = {"joie": 0, "colere": 1, "tristesse": 2, "peur": 3, "surprise": 4, "neutre": 5}
    
    def __len__(self):
        return len(self.texts)
    
    def __getitem__(self, idx):
        encoding = self.tokenizer(
            self.texts[idx],
            truncation=True,
            max_length=self.max_length,
            padding="max_length",
            return_tensors="pt"
        )
        return {
            "input_ids": encoding["input_ids"].squeeze(),
            "attention_mask": encoding["attention_mask"].squeeze(),
            "labels": torch.tensor(self.label_map.get(self.labels[idx], 5))
        }


def train_model(
    data_path: str,
    output_path: str = "data/models/sentiment",
    epochs: int = 3,
    batch_size: int = 16,
    learning_rate: float = 2e-5
):
    """Entraîne le modèle de sentiment"""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")
    
    # Charger données
    df = pd.read_csv(data_path)
    texts, labels = prepare_training_data(df, "text", "sentiment")
    
    # Split
    train_texts, val_texts, train_labels, val_labels = train_test_split(
        texts, labels, test_size=0.2, random_state=42
    )
    
    # Tokenizer et modèle
    tokenizer = AutoTokenizer.from_pretrained("camembert-base")
    model = AutoModelForSequenceClassification.from_pretrained(
        "camembert-base", num_labels=6
    ).to(device)
    
    # Datasets
    train_dataset = SentimentDataset(train_texts, train_labels, tokenizer)
    val_dataset = SentimentDataset(val_texts, val_labels, tokenizer)
    
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size)
    
    # Optimizer
    optimizer = AdamW(model.parameters(), lr=learning_rate)
    
    # Training loop
    for epoch in range(epochs):
        model.train()
        total_loss = 0
        
        for batch in train_loader:
            optimizer.zero_grad()
            outputs = model(
                input_ids=batch["input_ids"].to(device),
                attention_mask=batch["attention_mask"].to(device),
                labels=batch["labels"].to(device)
            )
            loss = outputs.loss
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        
        print(f"Epoch {epoch+1}/{epochs} - Loss: {total_loss/len(train_loader):.4f}")
    
    # Sauvegarder
    Path(output_path).mkdir(parents=True, exist_ok=True)
    model.save_pretrained(output_path)
    tokenizer.save_pretrained(output_path)
    print(f"Modèle sauvegardé dans {output_path}")


if __name__ == "__main__":
    train_model("data/raw/tweets_labeled.csv")
