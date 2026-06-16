import torch
from transformers import pipeline
from typing import Dict, List
import re


class SentimentAnalyzer:
    """Analyseur de sentiment multilingue - Modèle fine-tuné SentiFlow"""
    
    # Labels du modèle (ordre du fine-tuning)
    LABELS_EN = ["sadness", "joy", "love", "anger", "fear", "surprise", "neutral"]
    LABELS_FR = ["tristesse", "joie", "amour", "colere", "peur", "surprise", "neutre"]
    
    def __init__(self, model_name: str = "davidiabd2/SENTIFLOW_TWEET_FEELING"):
        self.device = 0 if torch.cuda.is_available() else -1
        
        # Charger le modèle fine-tuné
        self.classifier = pipeline(
            "text-classification",
            model=model_name,
            top_k=None,
            device=self.device
        )
        self.model_name = model_name
    
    def preprocess(self, text: str) -> str:
        """Nettoie le texte du tweet"""
        # Supprimer URLs
        text = re.sub(r'http\S+|www\S+|https\S+', '', text)
        # Supprimer mentions
        text = re.sub(r'@\w+', '', text)
        # Supprimer hashtags (garder le mot)
        text = re.sub(r'#(\w+)', r'\1', text)
        # Normaliser espaces
        text = ' '.join(text.split())
        return text.strip()[:512]
    
    def predict(self, text: str) -> Dict[str, float]:
        """Prédit le sentiment d'un texte"""
        clean_text = self.preprocess(text)
        
        if not clean_text:
            return {label: 0.0 for label in self.LABELS_FR}
        
        results = self.classifier(clean_text)[0]
        
        # Convertir en dict avec labels français
        scores = {label: 0.0 for label in self.LABELS_FR}
        for item in results:
            # Format: LABEL_0, LABEL_1, etc.
            idx = int(item["label"].split("_")[-1])
            if idx < len(self.LABELS_FR):
                scores[self.LABELS_FR[idx]] = round(item["score"], 4)
        
        return scores
    
    def predict_batch(self, texts: List[str]) -> List[Dict[str, float]]:
        """Prédit le sentiment pour plusieurs textes"""
        clean_texts = [self.preprocess(t) for t in texts]
        clean_texts = [t if t else "text" for t in clean_texts]
        
        results = self.classifier(clean_texts)
        
        all_scores = []
        for result in results:
            scores = {label: 0.0 for label in self.LABELS_FR}
            for item in result:
                idx = int(item["label"].split("_")[-1])
                if idx < len(self.LABELS_FR):
                    scores[self.LABELS_FR[idx]] = round(item["score"], 4)
            all_scores.append(scores)
        
        return all_scores
    
    def get_dominant_sentiment(self, scores: Dict[str, float]) -> tuple[str, float]:
        """Retourne le sentiment dominant et son score"""
        dominant = max(scores, key=scores.get)
        return dominant, scores[dominant]


# Singleton
_analyzer = None

def get_analyzer() -> SentimentAnalyzer:
    """Retourne l'instance singleton de l'analyseur"""
    global _analyzer
    if _analyzer is None:
        _analyzer = SentimentAnalyzer()
    return _analyzer
