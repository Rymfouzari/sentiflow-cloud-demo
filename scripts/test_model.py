"""Script pour tester le modele de sentiment sur le dataset Sentiment140"""
import pandas as pd
import sys
sys.path.insert(0, ".")
from services.sentiment.model import get_analyzer

print("Chargement du dataset...")
df = pd.read_csv(
    "data/raw/training.1600000.processed.noemoticon.csv",
    encoding="latin-1",
    header=None,
    names=["sentiment", "id", "date", "query", "user", "text"],
    nrows=100
)

print(f"Dataset: {len(df)} tweets")

print("Chargement du modele...")
analyzer = get_analyzer()
print("Modele charge!")

print("=" * 60)
print("TEST SUR 10 TWEETS")
print("=" * 60)

for i, row in df.head(10).iterrows():
    text = row["text"]
    scores = analyzer.predict(text)
    dominant, confidence = analyzer.get_dominant_sentiment(scores)
    print(f"\nTweet: {text[:70]}...")
    print(f"Emotion: {dominant.upper()} ({confidence:.1%})")
