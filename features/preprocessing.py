import re
from typing import List
import pandas as pd


def clean_tweet(text: str) -> str:
    """Nettoie un tweet pour l'analyse"""
    if not isinstance(text, str):
        return ""
    
    # Supprimer URLs
    text = re.sub(r'http\S+|www\S+|https\S+', '', text)
    # Supprimer mentions
    text = re.sub(r'@\w+', '', text)
    # Supprimer hashtags (garder le mot)
    text = re.sub(r'#(\w+)', r'\1', text)
    # Supprimer RT
    text = re.sub(r'^RT\s+', '', text)
    # Supprimer caractères spéciaux sauf accents
    text = re.sub(r'[^\w\sàâäéèêëïîôùûüç]', ' ', text, flags=re.IGNORECASE)
    # Normaliser espaces
    text = ' '.join(text.split())
    
    return text.strip().lower()


def clean_dataframe(df: pd.DataFrame, text_column: str = "text") -> pd.DataFrame:
    """Nettoie une colonne de texte dans un DataFrame"""
    df = df.copy()
    df["clean_text"] = df[text_column].apply(clean_tweet)
    df = df[df["clean_text"].str.len() > 10]  # Filtrer textes trop courts
    return df


def prepare_training_data(df: pd.DataFrame, text_col: str, label_col: str) -> tuple:
    """Prépare les données pour l'entraînement"""
    df = clean_dataframe(df, text_col)
    texts = df["clean_text"].tolist()
    labels = df[label_col].tolist()
    return texts, labels
