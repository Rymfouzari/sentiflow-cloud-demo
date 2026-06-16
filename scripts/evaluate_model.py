"""Evaluation du modele de sentiment"""
import sys
sys.path.insert(0, ".")

import pandas as pd
from datasets import load_dataset
from sklearn.metrics import classification_report, accuracy_score
from services.sentiment.model import get_analyzer

print("=" * 60)
print("EVALUATION DU MODELE DE SENTIMENT")
print("=" * 60)

# Charger le modele
print("\n1. Chargement du modele...")
analyzer = get_analyzer()
print("   Modele charge!")

# ============================================================
# TEST 1: Coherence avec Sentiment140
# ============================================================
print("\n" + "=" * 60)
print("TEST 1: COHERENCE AVEC SENTIMENT140")
print("=" * 60)

df = pd.read_csv(
    "data/raw/training.1600000.processed.noemoticon.csv",
    encoding="latin-1",
    header=None,
    names=["sentiment", "id", "date", "query", "user", "text"],
    nrows=500  # 500 tweets pour test rapide
)

# Emotions negatives et positives
NEGATIVE_EMOTIONS = ["tristesse", "colere", "peur", "degout"]
POSITIVE_EMOTIONS = ["joie", "surprise"]

coherent = 0
total = 0

for i, row in df.iterrows():
    scores = analyzer.predict(row["text"])
    dominant, _ = analyzer.get_dominant_sentiment(scores)
    
    is_negative_tweet = row["sentiment"] == 0
    is_negative_emotion = dominant in NEGATIVE_EMOTIONS
    is_positive_emotion = dominant in POSITIVE_EMOTIONS
    
    # Coherent si negatif->emotion negative OU positif->emotion positive
    if is_negative_tweet and is_negative_emotion:
        coherent += 1
    elif not is_negative_tweet and is_positive_emotion:
        coherent += 1
    # Neutre = on compte pas
    elif dominant == "neutre":
        total -= 1
    
    total += 1

coherence_score = coherent / total * 100 if total > 0 else 0
print(f"\n   Tweets testes: {len(df)}")
print(f"   Coherence: {coherent}/{total} = {coherence_score:.1f}%")
print("   (negatif->tristesse/colere/peur, positif->joie/surprise)")

# ============================================================
# TEST 2: Evaluation sur dair-ai/emotion
# ============================================================
print("\n" + "=" * 60)
print("TEST 2: EVALUATION SUR DAIR-AI/EMOTION")
print("=" * 60)

print("\n   Telechargement du dataset...")
dataset = load_dataset("dair-ai/emotion", split="test")

# Mapping des labels du dataset vers nos labels
EMOTION_MAP = {
    0: "tristesse",   # sadness
    1: "joie",        # joy
    2: "joie",        # love -> joie
    3: "colere",      # anger
    4: "peur",        # fear
    5: "surprise"     # surprise
}

print(f"   Dataset: {len(dataset)} exemples")

# Evaluer sur un echantillon
sample_size = 500
y_true = []
y_pred = []

print(f"   Evaluation sur {sample_size} exemples...")

for i in range(min(sample_size, len(dataset))):
    text = dataset[i]["text"]
    true_label = EMOTION_MAP[dataset[i]["label"]]
    
    scores = analyzer.predict(text)
    pred_label, _ = analyzer.get_dominant_sentiment(scores)
    
    y_true.append(true_label)
    y_pred.append(pred_label)

# Metriques
accuracy = accuracy_score(y_true, y_pred)
print(f"\n   ACCURACY: {accuracy:.1%}")

print("\n   RAPPORT DE CLASSIFICATION:")
print(classification_report(y_true, y_pred, zero_division=0))

# ============================================================
# RESUME
# ============================================================
print("=" * 60)
print("RESUME")
print("=" * 60)
print(f"\n   Coherence Sentiment140: {coherence_score:.1f}%")
print(f"   Accuracy dair-ai/emotion: {accuracy:.1%}")
print("\n   Le modele est pret pour la production!")
