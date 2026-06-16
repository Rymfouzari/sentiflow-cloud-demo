"""
RAG (Retrieval-Augmented Generation) 100% FROM SCRATCH pour SentiFlow.

Aucune dépendance externe pour le retrieval ou la génération :
- PAS de sentence-transformers (on utilise TF-IDF codé à la main)
- PAS de pgvector (on utilise un index NumPy/cosine maison)
- PAS d'API Mistral (on utilise le TinyGPT from scratch + fallback template)

Pipeline avancé :
1. Question -> tokenization + query expansion (synonymes from scratch)
2. Hybrid search: TF-IDF cosine (sémantique) + BM25 (mots-clés) - tout codé main
3. Reciprocal Rank Fusion (RRF) pour fusionner les résultats
4. Re-ranking (second passage avec scoring contextuel)
5. Pondération temporelle (tweets récents favorisés)
6. Construction du prompt avec les tweets pertinents
7. Génération de la réponse avec le TinyGPT from scratch + fallback intelligent
8. Métriques de qualité (relevance, cohérence, faithfulness, MRR, NDCG)
9. Tracking MLflow pour chaque évaluation
"""
from __future__ import annotations

import csv
import json
import logging
import math
import os
import pickle
import re
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import text as sql_text, func

from backend.app.config import get_settings
from backend.app.models.tweet import Tweet, VALID_SENTIMENTS
from backend.app.models.target import Target

logger = logging.getLogger("sentiflow.rag")
settings = get_settings()

# Chemin pour l'index persistant
INDEX_CACHE_PATH = Path(os.getenv(
    "RAG_INDEX_CACHE",
    str(Path(__file__).parent.parent.parent.parent / "data" / "rag_index.pkl")
))

# Chemin pour le dataset d'évaluation
EVAL_DATASET_PATH = Path(os.getenv(
    "RAG_EVAL_DATASET",
    str(Path(__file__).parent.parent.parent.parent / "data" / "rag_eval_dataset.csv")
))


# ============================================
# TOKENIZER FROM SCRATCH (pour le retrieval)
# ============================================

# Stopwords français + anglais pour le NLP
STOPWORDS_FR = {
    "le", "la", "les", "de", "du", "des", "un", "une", "et", "ou", "est",
    "sur", "en", "au", "aux", "ce", "que", "qui", "quoi", "comment", "pourquoi",
    "quel", "quelle", "quels", "quelles", "pas", "ne", "se", "sa", "son", "ses",
    "nous", "vous", "ils", "elles", "leur", "leurs", "mon", "ma", "mes", "ton",
    "ta", "tes", "dans", "par", "pour", "avec", "sans", "sous", "entre", "vers",
    "chez", "mais", "donc", "car", "ni", "si", "bien", "plus", "moins", "très",
    "trop", "tout", "tous", "toute", "toutes", "autre", "autres", "même", "aussi",
    "alors", "comme", "être", "avoir", "faire", "dire", "aller", "voir", "venir",
    "fait", "été", "sont", "ont", "peut", "cette", "ces", "cet", "dont", "où",
}

STOPWORDS_EN = {
    "the", "is", "are", "was", "were", "be", "been", "being", "have", "has",
    "had", "do", "does", "did", "will", "would", "could", "should", "may",
    "might", "shall", "can", "need", "dare", "ought", "used", "to", "of",
    "in", "for", "on", "with", "at", "by", "from", "as", "into", "through",
    "during", "before", "after", "above", "below", "between", "and", "but",
    "or", "nor", "not", "so", "yet", "both", "either", "neither", "each",
    "every", "all", "any", "few", "more", "most", "other", "some", "such",
    "no", "only", "own", "same", "than", "too", "very", "just", "because",
    "about", "this", "that", "these", "those", "it", "its", "he", "she",
    "they", "them", "his", "her", "their", "what", "which", "who", "whom",
}

STOPWORDS = STOPWORDS_FR | STOPWORDS_EN | {"rt", "amp", "https", "http", "co", "tweet", "twitter"}


# ============================================
# QUERY EXPANSION FROM SCRATCH (dynamique)
# ============================================

# Pas de dictionnaire statique — l'expansion se fait dynamiquement
# à partir des co-occurrences dans le corpus indexé.


def build_cooccurrence_matrix(tokenized_docs: List[List[str]], window: int = 5) -> Dict[str, Counter]:
    """
    Construit une matrice de co-occurrence from scratch.
    Pour chaque mot, compte combien de fois chaque autre mot apparaît
    dans une fenêtre de `window` tokens autour de lui.
    C'est 100% dynamique — appris sur les données réelles.
    """
    cooccurrences: Dict[str, Counter] = defaultdict(Counter)

    for doc in tokenized_docs:
        for i, token in enumerate(doc):
            # Fenêtre autour du mot
            start = max(0, i - window)
            end = min(len(doc), i + window + 1)
            for j in range(start, end):
                if i != j:
                    cooccurrences[token][doc[j]] += 1

    return dict(cooccurrences)


def expand_query_dynamic(
    query_tokens: List[str],
    cooccurrences: Dict[str, Counter],
    max_expansion_per_token: int = 3,
    min_cooccurrence: int = 2,
) -> List[str]:
    """
    Query expansion dynamique basée sur les co-occurrences du corpus.
    Pour chaque token de la requête, ajoute les mots qui co-apparaissent
    le plus souvent avec lui dans les tweets indexés.

    100% dynamique, 0 dictionnaire codé en dur.
    """
    expanded = list(query_tokens)
    added: set = set(query_tokens)

    for token in query_tokens:
        if token not in cooccurrences:
            continue
        # Prendre les mots les plus fréquemment associés
        neighbors = cooccurrences[token].most_common(max_expansion_per_token * 2)
        count_added = 0
        for neighbor, count in neighbors:
            if count < min_cooccurrence:
                break
            if neighbor not in added and len(neighbor) >= 3:
                expanded.append(neighbor)
                added.add(neighbor)
                count_added += 1
                if count_added >= max_expansion_per_token:
                    break

    return expanded


def pseudo_relevance_feedback(
    query_tokens: List[str],
    top_results: List[Dict[str, Any]],
    max_terms: int = 5,
) -> List[str]:
    """
    Pseudo-Relevance Feedback (PRF) from scratch.
    On prend les top-K résultats du premier passage,
    on extrait les termes les plus fréquents,
    et on les ajoute à la requête pour un second passage.

    Technique classique d'IR, codée from scratch.
    """
    if not top_results:
        return query_tokens

    # Collecter tous les tokens des top résultats
    term_freq: Counter = Counter()
    for result in top_results:
        text = result.get("text", "")
        tokens = tokenize_without_stem(text)  # on ne stem pas ici pour garder les mots originaux
        term_freq.update(tokens)

    # Retirer les tokens déjà dans la requête
    query_set = set(query_tokens)
    candidates = [
        (term, count) for term, count in term_freq.most_common(max_terms * 3)
        if term not in query_set and len(term) >= 3
    ]

    # Prendre les top termes
    expansion = [term for term, _ in candidates[:max_terms]]
    return query_tokens + expansion


def tokenize_without_stem(text: str) -> List[str]:
    """Tokenize sans stemming (pour le pseudo-relevance feedback)."""
    text = str(text or "").lower()
    text = strip_accents(text)
    text = re.sub(r"https?://\S+|www\.\S+", " ", text)
    text = re.sub(r"[@#]", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    tokens = text.split()
    return [t for t in tokens if len(t) >= 2 and t not in STOPWORDS]


def strip_accents(text: str) -> str:
    """Retire les accents d'un texte (normalisation Unicode NFD)."""
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text)
        if unicodedata.category(ch) != "Mn"
    )


def tokenize(text: str) -> List[str]:
    """
    Tokenizer from scratch :
    - lowercasing
    - suppression accents
    - suppression URLs, mentions, ponctuation
    - split sur espaces
    - filtrage stopwords et tokens courts
    - stemming français léger (from scratch)
    """
    text = str(text or "").lower()
    text = strip_accents(text)
    # Supprimer URLs
    text = re.sub(r"https?://\S+|www\.\S+", " ", text)
    # Supprimer mentions et hashtags (garder le mot)
    text = re.sub(r"[@#]", " ", text)
    # Garder uniquement alphanumérique
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    # Split et filtrage
    tokens = text.split()
    tokens = [t for t in tokens if len(t) >= 2 and t not in STOPWORDS]
    # Stemming français léger
    tokens = [french_stem(t) for t in tokens]
    return tokens


def french_stem(word: str) -> str:
    """
    Stemmer français from scratch (suppression suffixes courants).
    Pas de librairie NLTK/spaCy.
    """
    if len(word) <= 4:
        return word

    # Suffixes à retirer (du plus long au plus court)
    suffixes = [
        "issement", "ements", "ement", "ations", "ation",
        "iques", "ique", "ables", "able", "istes", "iste",
        "eurs", "eur", "euses", "euse", "ments", "ment",
        "ions", "ion", "ites", "ite", "ants", "ant",
        "ents", "ent", "eux", "aux", "ifs", "ives",
        "ees", "ee", "es", "er", "ez", "ir",
    ]

    for suffix in suffixes:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[:-len(suffix)]

    # Pluriel simple
    if word.endswith("s") and len(word) > 4:
        return word[:-1]

    return word


# ============================================
# TF-IDF FROM SCRATCH
# ============================================

class TFIDFVectorizer:
    """
    Implémentation TF-IDF entièrement from scratch.
    Pas de sklearn, pas de gensim, rien d'externe.
    """

    def __init__(self):
        self.vocab: Dict[str, int] = {}  # token -> index
        self.idf: Dict[str, float] = {}  # token -> IDF score
        self.doc_count: int = 0

    def fit(self, documents: List[List[str]]) -> "TFIDFVectorizer":
        """Calcule le vocabulaire et les scores IDF à partir d'un corpus."""
        self.doc_count = len(documents)
        if self.doc_count == 0:
            return self

        # Compter dans combien de documents chaque token apparaît (DF)
        doc_freq: Counter = Counter()
        all_tokens: set = set()

        for doc_tokens in documents:
            unique_tokens = set(doc_tokens)
            doc_freq.update(unique_tokens)
            all_tokens.update(unique_tokens)

        # Construire le vocabulaire (triés par fréquence décroissante)
        sorted_tokens = sorted(all_tokens, key=lambda t: -doc_freq[t])
        self.vocab = {token: idx for idx, token in enumerate(sorted_tokens)}

        # Calculer IDF : log(N / (1 + df)) + 1 (smooth IDF)
        for token, df in doc_freq.items():
            self.idf[token] = math.log(self.doc_count / (1 + df)) + 1.0

        return self

    def transform_one(self, tokens: List[str]) -> np.ndarray:
        """Transforme un document tokenisé en vecteur TF-IDF."""
        if not self.vocab:
            return np.zeros(1)

        vector = np.zeros(len(self.vocab), dtype=np.float32)
        tf_counts = Counter(tokens)
        doc_len = len(tokens) if tokens else 1

        for token, count in tf_counts.items():
            if token in self.vocab:
                # TF normalisé (fréquence relative)
                tf = count / doc_len
                idf = self.idf.get(token, 1.0)
                vector[self.vocab[token]] = tf * idf

        # Normalisation L2
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm

        return vector

    def transform(self, documents: List[List[str]]) -> np.ndarray:
        """Transforme plusieurs documents en matrice TF-IDF."""
        if not self.vocab:
            return np.zeros((len(documents), 1), dtype=np.float32)
        matrix = np.zeros((len(documents), len(self.vocab)), dtype=np.float32)
        for i, doc_tokens in enumerate(documents):
            matrix[i] = self.transform_one(doc_tokens)
        return matrix

    @property
    def vocab_size(self) -> int:
        return len(self.vocab)


# ============================================
# BM25 FROM SCRATCH
# ============================================

class BM25:
    """
    Implémentation BM25 (Okapi) entièrement from scratch.
    Pas de librairie externe.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_count = 0
        self.avgdl = 0.0
        self.doc_lens: List[int] = []
        self.doc_freqs: Dict[str, int] = {}  # token -> nb docs contenant le token
        self.corpus: List[List[str]] = []

    def fit(self, documents: List[List[str]]) -> "BM25":
        """Index le corpus pour la recherche BM25."""
        self.corpus = documents
        self.doc_count = len(documents)
        self.doc_lens = [len(doc) for doc in documents]
        self.avgdl = sum(self.doc_lens) / max(self.doc_count, 1)

        # Document Frequency
        self.doc_freqs = {}
        for doc in documents:
            unique_tokens = set(doc)
            for token in unique_tokens:
                self.doc_freqs[token] = self.doc_freqs.get(token, 0) + 1

        return self

    def _idf(self, token: str) -> float:
        """IDF BM25 : log((N - n + 0.5) / (n + 0.5) + 1)"""
        n = self.doc_freqs.get(token, 0)
        return math.log((self.doc_count - n + 0.5) / (n + 0.5) + 1.0)

    def score(self, query_tokens: List[str], doc_idx: int) -> float:
        """Score BM25 d'un document pour une requête."""
        doc = self.corpus[doc_idx]
        doc_len = self.doc_lens[doc_idx]
        score = 0.0

        tf_counts = Counter(doc)
        for token in query_tokens:
            if token not in tf_counts:
                continue
            tf = tf_counts[token]
            idf = self._idf(token)
            # BM25 formula
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / self.avgdl)
            score += idf * (numerator / denominator)

        return score

    def search(self, query_tokens: List[str], top_k: int = 10) -> List[Tuple[int, float]]:
        """Retourne les top_k documents les plus pertinents avec leur score."""
        scores = []
        for i in range(self.doc_count):
            s = self.score(query_tokens, i)
            if s > 0:
                scores.append((i, s))
        scores.sort(key=lambda x: -x[1])
        return scores[:top_k]


# ============================================
# COSINE SIMILARITY FROM SCRATCH
# ============================================

def cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    """Calcul de la similarité cosinus entre deux vecteurs."""
    dot = np.dot(vec_a, vec_b)
    norm_a = np.linalg.norm(vec_a)
    norm_b = np.linalg.norm(vec_b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def cosine_search(query_vector: np.ndarray, matrix: np.ndarray, top_k: int = 10) -> List[Tuple[int, float]]:
    """Recherche les top_k vecteurs les plus similaires dans la matrice."""
    if matrix.shape[0] == 0:
        return []
    # Calcul vectorisé de toutes les similarités
    query_norm = np.linalg.norm(query_vector)
    if query_norm == 0:
        return []
    query_normalized = query_vector / query_norm

    norms = np.linalg.norm(matrix, axis=1)
    # Éviter division par zéro
    norms[norms == 0] = 1.0
    matrix_normalized = matrix / norms[:, np.newaxis]

    similarities = matrix_normalized @ query_normalized
    top_indices = np.argsort(similarities)[::-1][:top_k]

    return [(int(idx), float(similarities[idx])) for idx in top_indices if similarities[idx] > 0]


# ============================================
# INDEX VECTORIEL FROM SCRATCH
# ============================================

class VectorIndex:
    """
    Index vectoriel in-memory from scratch.
    Stocke les vecteurs TF-IDF et les métadonnées associées.
    Pas de pgvector, pas de FAISS, juste NumPy.
    """

    def __init__(self):
        self.vectorizer = TFIDFVectorizer()
        self.bm25 = BM25()
        self.documents: List[Dict[str, Any]] = []  # métadonnées des tweets
        self.tokenized_docs: List[List[str]] = []
        self.tfidf_matrix: Optional[np.ndarray] = None
        self.cooccurrences: Dict[str, Counter] = {}  # co-occurrences dynamiques
        self.is_fitted = False
        self._last_indexed_count = 0

    def index_tweets(self, tweets: List[Dict[str, Any]]) -> int:
        """
        Indexe une liste de tweets (dict avec id, text, sentiment, etc.).
        Retourne le nombre de tweets indexés.
        """
        if not tweets:
            return 0

        self.documents = tweets
        self.tokenized_docs = [tokenize(t.get("text", "")) for t in tweets]

        # Fit TF-IDF
        self.vectorizer.fit(self.tokenized_docs)
        self.tfidf_matrix = self.vectorizer.transform(self.tokenized_docs)

        # Fit BM25
        self.bm25.fit(self.tokenized_docs)

        # Construire la matrice de co-occurrence (query expansion dynamique)
        self.cooccurrences = build_cooccurrence_matrix(self.tokenized_docs, window=5)

        self.is_fitted = True
        self._last_indexed_count = len(tweets)

        logger.info(
            f"[RAG] Index construit: {len(tweets)} tweets, "
            f"vocab={self.vectorizer.vocab_size}, "
            f"cooccurrence_keys={len(self.cooccurrences)}"
        )
        return len(tweets)

    def tfidf_search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Recherche par similarité cosinus TF-IDF."""
        if not self.is_fitted or self.tfidf_matrix is None:
            return []

        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        query_vector = self.vectorizer.transform_one(query_tokens)
        results = cosine_search(query_vector, self.tfidf_matrix, top_k=top_k)

        return [
            {**self.documents[idx], "tfidf_score": round(score, 4), "retrieval_method": "tfidf"}
            for idx, score in results
        ]

    def bm25_search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Recherche BM25 par mots-clés."""
        if not self.is_fitted:
            return []

        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        results = self.bm25.search(query_tokens, top_k=top_k)

        return [
            {**self.documents[idx], "bm25_score": round(score, 4), "retrieval_method": "bm25"}
            for idx, score in results
        ]

    def hybrid_search(self, query: str, top_k: int = 15) -> List[Dict[str, Any]]:
        """
        Recherche hybride: combine TF-IDF (sémantique) + BM25 (mots-clés).
        Avec query expansion dynamique (co-occurrences) + Pseudo-Relevance Feedback.
        Si la requête est trop générale (pas de résultats), retourne un échantillon global.
        """
        # Tokenize la requête
        query_tokens = tokenize(query)
        if not query_tokens:
            # Requête vide après tokenization → retourner un échantillon global
            return self._global_sample(top_k)

        # Query expansion dynamique (basée sur les co-occurrences du corpus)
        expanded_tokens = expand_query_dynamic(
            query_tokens, self.cooccurrences,
            max_expansion_per_token=2, min_cooccurrence=2,
        )
        expanded_query = " ".join(expanded_tokens)

        # Premier passage : TF-IDF + BM25
        tfidf_results = self.tfidf_search(expanded_query, top_k=top_k)
        bm25_results = self.bm25_search(expanded_query, top_k=top_k)

        # RRF: score = sum(1 / (k + rank)) pour chaque liste
        k = 60  # constante RRF standard
        scores: Dict[int, Dict[str, Any]] = {}

        for rank, result in enumerate(tfidf_results):
            tid = result["id"]
            scores[tid] = {"data": result, "rrf": 0.0}
            scores[tid]["rrf"] += 1 / (k + rank + 1)

        for rank, result in enumerate(bm25_results):
            tid = result["id"]
            if tid not in scores:
                scores[tid] = {"data": result, "rrf": 0.0}
            scores[tid]["rrf"] += 1 / (k + rank + 1)

        # Trier par score RRF décroissant
        ranked = sorted(scores.values(), key=lambda x: -x["rrf"])
        first_pass_results = []
        for item in ranked[:top_k]:
            data = item["data"]
            data["rrf_score"] = round(item["rrf"], 4)
            data["retrieval_method"] = "hybrid"
            first_pass_results.append(data)

        # Si pas assez de résultats, compléter avec un échantillon global
        if len(first_pass_results) < 3:
            global_sample = self._global_sample(top_k)
            existing_ids = {r["id"] for r in first_pass_results}
            for r in global_sample:
                if r["id"] not in existing_ids:
                    first_pass_results.append(r)
                    if len(first_pass_results) >= top_k:
                        break

        # Pseudo-Relevance Feedback (PRF) : second passage
        prf_tokens = query_tokens  # fallback
        if first_pass_results and len(first_pass_results) >= 2:
            prf_tokens = pseudo_relevance_feedback(
                query_tokens, first_pass_results[:3], max_terms=3
            )
            if len(prf_tokens) > len(query_tokens):
                prf_query = " ".join(prf_tokens)
                prf_tfidf = self.tfidf_search(prf_query, top_k=top_k // 2)
                existing_ids = {r["id"] for r in first_pass_results}
                for r in prf_tfidf:
                    if r["id"] not in existing_ids:
                        r["rrf_score"] = 0.005
                        r["retrieval_method"] = "hybrid+prf"
                        first_pass_results.append(r)
                        if len(first_pass_results) >= top_k:
                            break

        logger.info(
            f"[RAG] Hybrid: {len(tfidf_results)} TF-IDF + {len(bm25_results)} BM25 "
            f"= {len(first_pass_results)} résultats "
            f"(expanded: {len(expanded_tokens)} tokens, PRF: {len(query_tokens)} → {len(prf_tokens)})"
        )
        return first_pass_results

    def _global_sample(self, top_k: int = 15) -> List[Dict[str, Any]]:
        """Retourne un échantillon diversifié de tweets quand la requête est trop large."""
        if not self.documents:
            return []
        by_target: Dict[str, List[Dict]] = defaultdict(list)
        for doc in self.documents:
            by_target[doc.get("target", "?")].append(doc)
        sample = []
        for target, docs in by_target.items():
            sample.extend(docs[:top_k // max(len(by_target), 1)])
        for r in sample[:top_k]:
            r["rrf_score"] = 0.008
            r["retrieval_method"] = "global_sample"
        return sample[:top_k]

    @property
    def indexed_count(self) -> int:
        return self._last_indexed_count

    def save_to_disk(self, path: Optional[Path] = None) -> bool:
        """Persiste l'index sur disque (pickle)."""
        path = path or INDEX_CACHE_PATH
        if not self.is_fitted:
            return False
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "documents": self.documents,
                "tokenized_docs": self.tokenized_docs,
                "tfidf_matrix": self.tfidf_matrix,
                "vectorizer_vocab": self.vectorizer.vocab,
                "vectorizer_idf": self.vectorizer.idf,
                "vectorizer_doc_count": self.vectorizer.doc_count,
                "bm25_corpus": self.bm25.corpus,
                "bm25_doc_lens": self.bm25.doc_lens,
                "bm25_doc_freqs": self.bm25.doc_freqs,
                "bm25_avgdl": self.bm25.avgdl,
                "bm25_doc_count": self.bm25.doc_count,
                "cooccurrences": dict(self.cooccurrences),
                "saved_at": datetime.utcnow().isoformat(),
            }
            with open(path, "wb") as f:
                pickle.dump(payload, f)
            logger.info(f"[RAG] Index sauvegardé: {path} ({len(self.documents)} docs)")
            return True
        except Exception as e:
            logger.error(f"[RAG] Erreur sauvegarde index: {e}")
            return False

    def load_from_disk(self, path: Optional[Path] = None) -> bool:
        """Charge l'index depuis le disque."""
        path = path or INDEX_CACHE_PATH
        if not path.exists():
            return False
        try:
            with open(path, "rb") as f:
                payload = pickle.load(f)
            self.documents = payload["documents"]
            self.tokenized_docs = payload["tokenized_docs"]
            self.tfidf_matrix = payload["tfidf_matrix"]
            self.vectorizer.vocab = payload["vectorizer_vocab"]
            self.vectorizer.idf = payload["vectorizer_idf"]
            self.vectorizer.doc_count = payload["vectorizer_doc_count"]
            self.bm25.corpus = payload["bm25_corpus"]
            self.bm25.doc_lens = payload["bm25_doc_lens"]
            self.bm25.doc_freqs = payload["bm25_doc_freqs"]
            self.bm25.avgdl = payload["bm25_avgdl"]
            self.bm25.doc_count = payload["bm25_doc_count"]
            self.cooccurrences = payload.get("cooccurrences", {})
            self.is_fitted = True
            self._last_indexed_count = len(self.documents)
            logger.info(f"[RAG] Index chargé depuis disque: {len(self.documents)} docs")
            return True
        except Exception as e:
            logger.error(f"[RAG] Erreur chargement index: {e}")
            return False


# ============================================
# RE-RANKING FROM SCRATCH
# ============================================

def rerank_results(
    query: str,
    results: List[Dict[str, Any]],
    top_k: int = 10,
) -> List[Dict[str, Any]]:
    """
    Re-ranking from scratch (second passage).
    Score contextuel basé sur :
    - Couverture des mots de la requête dans le tweet
    - Confiance du modèle ML
    - Boost temporel (tweets récents favorisés)
    - Pénalité pour tweets trop courts
    """
    if not results:
        return []

    query_tokens = set(tokenize(query))
    now = datetime.utcnow()
    scored = []

    for result in results:
        score = result.get("rrf_score", 0.0)

        # 1. Couverture des mots de la requête (token overlap)
        tweet_tokens = set(tokenize(result.get("text", "")))
        if query_tokens:
            overlap = len(query_tokens & tweet_tokens) / len(query_tokens)
            score += overlap * 0.3

        # 2. Boost confiance ML
        confidence = result.get("confidence", 0.5)
        score += confidence * 0.15

        # 3. Boost temporel (tweets récents)
        analyzed_at = result.get("analyzed_at")
        if analyzed_at:
            try:
                dt = datetime.fromisoformat(str(analyzed_at).replace("Z", ""))
                days_ago = (now - dt).days
                # Décroissance exponentielle : score max si < 1 jour, décroit sur 30 jours
                temporal_boost = math.exp(-days_ago / 15) * 0.2
                score += temporal_boost
            except (ValueError, TypeError):
                pass

        # 4. Pénalité tweets courts (< 20 chars = peu informatif)
        text_len = len(result.get("text", ""))
        if text_len < 20:
            score -= 0.1
        elif text_len > 100:
            score += 0.05  # légèrement favoriser les tweets riches

        # 5. Bonus si sentiment mentionné dans la requête
        sentiment = result.get("sentiment", "")
        query_lower = strip_accents(query.lower())
        if sentiment and strip_accents(sentiment) in query_lower:
            score += 0.2

        result["rerank_score"] = round(score, 4)
        scored.append(result)

    scored.sort(key=lambda x: -x["rerank_score"])
    return scored[:top_k]


# ============================================
# CACHE DE REQUÊTES (optimisation vitesse)
# ============================================

class QueryCache:
    """
    Cache LRU from scratch pour les résultats de recherche.
    Évite de recalculer TF-IDF + BM25 + reranking pour des questions similaires.
    TTL configurable (défaut 5 minutes).
    """

    def __init__(self, max_size: int = 128, ttl_seconds: int = 300):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._access_order: List[str] = []
        self._hits = 0
        self._misses = 0

    def _normalize_key(self, query: str) -> str:
        return strip_accents(query.lower().strip())

    def get(self, query: str) -> Optional[List[Dict[str, Any]]]:
        key = self._normalize_key(query)
        entry = self._cache.get(key)
        if entry is None:
            self._misses += 1
            return None
        # Vérifier TTL
        if time.time() - entry["timestamp"] > self.ttl_seconds:
            del self._cache[key]
            self._misses += 1
            return None
        self._hits += 1
        # Mettre à jour l'ordre d'accès
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)
        return entry["results"]

    def put(self, query: str, results: List[Dict[str, Any]]) -> None:
        key = self._normalize_key(query)
        # Éviction LRU si plein
        while len(self._cache) >= self.max_size and self._access_order:
            oldest = self._access_order.pop(0)
            self._cache.pop(oldest, None)
        self._cache[key] = {"results": results, "timestamp": time.time()}
        self._access_order.append(key)

    def invalidate(self) -> None:
        """Vide le cache (après indexation de nouveaux tweets)."""
        self._cache.clear()
        self._access_order.clear()

    @property
    def stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 4) if total > 0 else 0.0,
        }


_QUERY_CACHE = QueryCache(max_size=128, ttl_seconds=300)


def get_query_cache() -> QueryCache:
    return _QUERY_CACHE


# ============================================
# SINGLETON DE L'INDEX
# ============================================

_VECTOR_INDEX: Optional[VectorIndex] = None


def get_vector_index() -> VectorIndex:
    global _VECTOR_INDEX
    if _VECTOR_INDEX is None:
        _VECTOR_INDEX = VectorIndex()
    return _VECTOR_INDEX


# ============================================
# CHARGEMENT DES TWEETS DEPUIS LA BDD
# ============================================

def load_tweets_for_index(
    db: Session,
    target_id: Optional[int] = None,
    days: int = 30,
    limit: int = 5000,
) -> List[Dict[str, Any]]:
    """Charge les tweets analysés depuis la BDD pour construire l'index."""
    since = datetime.utcnow() - timedelta(days=days)

    query = (
        db.query(Tweet, Target.name.label("target_name"))
        .join(Target, Target.id == Tweet.target_id)
        .filter(
            Tweet.sentiment.isnot(None),
            Tweet.analyzed_at >= since,
        )
    )
    if target_id:
        query = query.filter(Tweet.target_id == target_id)

    query = query.order_by(Tweet.analyzed_at.desc()).limit(limit)
    rows = query.all()

    tweets = []
    for tweet, target_name in rows:
        tweets.append({
            "id": tweet.id,
            "text": tweet.text or "",
            "sentiment": tweet.sentiment,
            "confidence": float(tweet.confidence) if tweet.confidence else 0.0,
            "author": tweet.author_username or "?",
            "target": target_name or "?",
            "target_id": tweet.target_id,
            "created_at": str(tweet.tweet_created_at) if tweet.tweet_created_at else None,
            "analyzed_at": str(tweet.analyzed_at) if tweet.analyzed_at else None,
        })

    return tweets


def index_all_tweets(db: Session, target_id: Optional[int] = None, days: int = 30) -> int:
    """
    Charge tous les tweets analysés et les indexe dans le VectorIndex.
    Remplace l'ancien index s'il existait.
    Invalide le cache de requêtes.
    """
    start = time.time()
    tweets = load_tweets_for_index(db, target_id=target_id, days=days)

    if not tweets:
        logger.info("[RAG] Aucun tweet à indexer")
        return 0

    index = get_vector_index()
    count = index.index_tweets(tweets)

    # Invalider le cache (les anciens résultats ne sont plus valides)
    get_query_cache().invalidate()

    elapsed = time.time() - start
    logger.info(f"[RAG] {count} tweets indexés en {elapsed:.2f}s")
    return count


# ============================================
# RETRIEVAL (interface publique)
# ============================================

def hybrid_retrieve(
    db: Session,
    query: str,
    top_k: int = 15,
    target_id: Optional[int] = None,
    days: int = 30,
    enable_mcp: bool = True,
    min_results_threshold: int = 3,
) -> List[Dict[str, Any]]:
    """
    Point d'entrée principal du retrieval.
    - Cache LRU pour éviter de recalculer (5min TTL)
    - Si l'index est vide, on le reconstruit (ou charge depuis disque)
    - Recherche hybride
    - Re-ranking (second passage)
    - SI pas assez de résultats ET enable_mcp : appelle le MCP Twitter en temps réel
    """
    # Vérifier le cache
    cache = get_query_cache()
    cache_key = f"{query}|{target_id}|{days}"
    cached = cache.get(cache_key)
    if cached is not None:
        logger.info(f"[RAG] Cache HIT pour '{query[:40]}' ({len(cached)} résultats)")
        return cached

    index = get_vector_index()

    # Tenter de charger depuis disque si l'index est vide
    if not index.is_fitted or index.indexed_count == 0:
        loaded = index.load_from_disk()
        if not loaded:
            count = index_all_tweets(db, target_id=target_id, days=days)
            if count == 0 and not enable_mcp:
                return []

    results = index.hybrid_search(query, top_k=top_k * 2)  # over-fetch pour le reranking

    # Filtrer par target_id si demandé
    if target_id:
        results = [r for r in results if r.get("target_id") == target_id]

    # Re-ranking (second passage from scratch)
    results = rerank_results(query, results, top_k=top_k)

    # MCP : si pas assez de résultats, aller chercher en temps réel sur Twitter
    if enable_mcp and len(results) < min_results_threshold:
        logger.info(
            f"[RAG] Seulement {len(results)} résultats en BDD "
            f"(seuil={min_results_threshold}), appel MCP Twitter..."
        )
        mcp_results = _mcp_enrich_sync(query, top_k=top_k)
        if mcp_results:
            # Fusionner les résultats MCP avec les résultats locaux
            existing_ids = {r.get("id") for r in results}
            for r in mcp_results:
                if r.get("id") not in existing_ids:
                    results.append(r)
            # Re-rank le tout
            results = rerank_results(query, results, top_k=top_k)

    # Mettre en cache le résultat
    cache.put(cache_key, results)

    return results


def _mcp_enrich_sync(query: str, top_k: int = 15) -> List[Dict[str, Any]]:
    """
    Appelle le MCP (search_and_analyze) de manière synchrone.
    Utilisé par le retriever quand la BDD n'a pas assez de données.
    """
    import asyncio
    try:
        from backend.app.services.mcp_server import execute_tool

        # Créer ou récupérer une event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Si on est déjà dans une boucle async, on ne peut pas run_until_complete
                # On retourne vide et le chat() (qui est async) appellera mcp_enrich directement
                return []
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        result = loop.run_until_complete(
            execute_tool("search_and_analyze", {"query": query, "limit": top_k})
        )

        if "error" in result or not result.get("tweets"):
            return []

        # Convertir au format attendu par le RAG
        tweets = []
        for t in result.get("tweets", []):
            tweets.append({
                "id": hash(t.get("id", t.get("text", "")[:30])),  # ID temporaire
                "text": t.get("text", ""),
                "sentiment": t.get("sentiment"),
                "confidence": t.get("confidence", 0.5),
                "author": t.get("author", "?"),
                "target": t.get("target", query),
                "target_id": None,
                "analyzed_at": datetime.utcnow().isoformat(),
                "source": "mcp_realtime",
                "rrf_score": 0.01,  # score de base pour le reranking
            })

        logger.info(f"[RAG-MCP] {len(tweets)} tweets récupérés en temps réel pour '{query}'")
        return tweets

    except Exception as e:
        logger.warning(f"[RAG-MCP] Erreur enrichissement MCP: {e}")
        return []


async def mcp_enrich(query: str, top_k: int = 15) -> List[Dict[str, Any]]:
    """
    Version async de l'enrichissement MCP.
    Appelée depuis le pipeline RAG async (chat()).
    Stocke les tweets en BDD si une session est fournie.
    """
    try:
        from backend.app.services.mcp_server import execute_tool

        result = await execute_tool("search_and_analyze", {"query": query, "limit": top_k})

        if "error" in result or not result.get("tweets"):
            return []

        tweets = []
        for t in result.get("tweets", []):
            tweets.append({
                "id": hash(t.get("id", t.get("text", "")[:30])),
                "text": t.get("text", ""),
                "sentiment": t.get("sentiment"),
                "confidence": t.get("confidence", 0.5),
                "author": t.get("author", "?"),
                "target": t.get("target", query),
                "target_id": None,
                "analyzed_at": datetime.utcnow().isoformat(),
                "source": "mcp_realtime",
                "rrf_score": 0.01,
                # Garder l'ID Twitter pour le stockage BDD
                "twitter_id": str(t.get("id", "")),
            })

        logger.info(f"[RAG-MCP] {len(tweets)} tweets temps réel pour '{query}'")
        return tweets

    except Exception as e:
        logger.warning(f"[RAG-MCP] Erreur: {e}")
        return []


def store_mcp_tweets_in_db(db: Session, tweets: List[Dict[str, Any]], query: str, user_id: Optional[int] = None) -> int:
    """
    Stocke les tweets récupérés par le MCP dans PostgreSQL.
    Crée la cible si elle n'existe pas, rattachée à l'utilisateur courant.
    Retourne le nombre de tweets sauvegardés.
    """
    if not tweets or not db:
        return 0

    saved = 0
    try:
        # Trouver ou créer la cible
        target_name = query.strip().lower()
        target = db.query(Target).filter(Target.name == target_name).first()

        if not target:
            from backend.app.models.target import TargetType
            target_type = TargetType.ACCOUNT if target_name.startswith("@") else TargetType.HASHTAG
            # Rattacher la cible à l'utilisateur courant si connu, sinon au premier user
            owner_id = user_id
            if not owner_id:
                from backend.app.models.user import User
                first_user = db.query(User).first()
                owner_id = first_user.id if first_user else None
            if not owner_id:
                return 0
            target = Target(
                name=target_name,
                target_type=target_type,
                query=target_name,
                user_id=owner_id,
            )
            db.add(target)
            db.flush()
            logger.info(f"[RAG-MCP] Cible créée: {target_name} (id={target.id}, user_id={owner_id})")

        # Sauvegarder chaque tweet
        for t in tweets:
            twitter_id = t.get("twitter_id", "")
            if not twitter_id:
                continue

            # Vérifier doublon
            existing = db.query(Tweet).filter(Tweet.twitter_id == twitter_id).first()
            if existing:
                continue

            text = t.get("text", "").strip()[:1000]
            if not text:
                continue

            tweet = Tweet(
                twitter_id=twitter_id,
                target_id=target.id,
                text=text,
                author_username=t.get("author"),
                sentiment=t.get("sentiment"),
                confidence=t.get("confidence"),
                analyzed_at=datetime.utcnow(),
            )
            db.add(tweet)
            saved += 1

        db.commit()
        logger.info(f"[RAG-MCP] {saved} tweets sauvegardés en BDD pour '{query}'")

    except Exception as e:
        logger.error(f"[RAG-MCP] Erreur stockage BDD: {e}")
        db.rollback()

    return saved


# ============================================
# PROMPT BUILDER FROM SCRATCH
# ============================================

def build_rag_prompt(question: str, tweets: List[Dict[str, Any]], intent: str = "summarize") -> str:
    """
    Construit le prompt pour le générateur à partir de la question
    et des tweets récupérés par le retrieval.
    Le prompt est DYNAMIQUE — il change selon l'intent détecté par le planner LLM.
    """
    if not tweets:
        return (
            "Tu es l'assistant d'analyse de sentiments SentiFlow.\n"
            "L'utilisateur pose une question mais aucun tweet pertinent n'a été trouvé.\n"
            f"Question: {question}\n"
            "Réponds que tu n'as pas assez de données."
        )

    # Construire le contexte à partir des tweets récupérés
    context_parts = []
    for i, t in enumerate(tweets[:10], 1):
        conf = f"{t['confidence']:.0%}" if t.get("confidence") else "?"
        sentiment = t.get("sentiment", "?")
        author = t.get("author", "?")
        target = t.get("target", "?")
        text = str(t.get("text", ""))[:200]
        # Inclure la date si disponible
        date_str = ""
        if t.get("created_at"):
            date_str = f" | {str(t['created_at'])[:16]}"
        elif t.get("analyzed_at"):
            date_str = f" | {str(t['analyzed_at'])[:16]}"
        context_parts.append(
            f"{i}. [{target}] @{author} | {sentiment} ({conf}){date_str} | \"{text}\""
        )

    context = "\n".join(context_parts)

    # Statistiques rapides
    sentiments = [t["sentiment"] for t in tweets if t.get("sentiment")]
    sent_counts = Counter(sentiments)
    stats = ", ".join(f"{k}: {v}" for k, v in sent_counts.most_common())
    total = len(sentiments)
    if total > 0:
        percentages = ", ".join(
            f"{k}: {v/total:.0%}" for k, v in sent_counts.most_common()
        )
    else:
        percentages = "aucun"

    # Cibles présentes dans les données
    targets_in_data = list(set(t.get("target", "?") for t in tweets))

    # Statistiques PAR CIBLE (essentiel pour les comparaisons multi-cibles)
    per_target_lines = []
    if len(targets_in_data) > 1:
        for tgt in targets_in_data:
            tgt_sentiments = [
                t["sentiment"] for t in tweets
                if t.get("sentiment") and t.get("target", "?") == tgt
            ]
            tgt_total = len(tgt_sentiments)
            if tgt_total == 0:
                per_target_lines.append(f"- {tgt} : aucun tweet")
                continue
            tgt_counts = Counter(tgt_sentiments)
            tgt_pct = ", ".join(
                f"{k}: {v/tgt_total:.0%}" for k, v in tgt_counts.most_common()
            )
            per_target_lines.append(f"- {tgt} ({tgt_total} tweets) : {tgt_pct}")
    per_target_block = (
        "## Statistiques par cible\n" + "\n".join(per_target_lines) + "\n\n"
        if per_target_lines else ""
    )

    # Instructions DYNAMIQUES selon l'intent du planner LLM
    intent_instructions = {
        "compare": (
            "Tu dois COMPARER les sentiments entre les différentes cibles.\n"
            "Fais un tableau comparatif : quelle cible est plus positive/négative.\n"
            "Donne les différences clés et une conclusion sur laquelle est mieux perçue.\n"
            "Ne liste PAS chaque cible séparément — COMPARE-les directement."
        ),
        "timeline": (
            "Tu dois analyser l'ÉVOLUTION TEMPORELLE des sentiments.\n"
            "Est-ce que ça augmente ou diminue ? Y a-t-il une tendance ?\n"
            "Base-toi sur les dates des tweets pour détecter les changements."
        ),
        "summarize": (
            "Fais une SYNTHÈSE complète des sentiments.\n"
            "Donne le sentiment dominant, les pourcentages, et des exemples concrets.\n"
            "Explique POURQUOI les gens réagissent comme ça."
        ),
        "examples": (
            "Donne des EXEMPLES concrets de tweets avec leur sentiment.\n"
            "Cite les tweets les plus représentatifs."
        ),
        "dashboard": (
            "Résume les données pour un dashboard.\n"
            "Donne les chiffres clés : distribution, tendance, top auteurs."
        ),
    }

    instruction = intent_instructions.get(intent, intent_instructions["summarize"])

    return (
        "Tu es l'assistant d'analyse de sentiments SentiFlow.\n"
        "Réponds en français, de manière claire et analytique.\n"
        "Base ta réponse UNIQUEMENT sur les tweets fournis ci-dessous.\n\n"
        f"## Intention détectée : {intent}\n"
        f"## Instruction : {instruction}\n\n"
        f"## Cibles dans les données : {', '.join(targets_in_data)}\n\n"
        f"## Tweets pertinents ({len(tweets)} résultats)\n"
        f"{context}\n\n"
        f"## Statistiques\n"
        f"Distribution: {stats}\n"
        f"Pourcentages: {percentages}\n\n"
        f"{per_target_block}"
        f"## Question de l'utilisateur\n{question}\n\n"
        f"Réponds selon l'instruction ci-dessus. Cite des exemples concrets."
    )


# ============================================
# GENERATEUR FROM SCRATCH (TinyGPT + fallback)
# ============================================

def generate_answer_from_scratch(
    question: str,
    tweets: List[Dict[str, Any]],
    prompt: str,
) -> str:
    """
    Génère une réponse en utilisant (par ordre de priorité) :
    1. Groq API (LLaMA 3 — réponses naturelles style ChatGPT)
    2. TinyGPT from scratch (si checkpoint disponible)
    3. Fallback déterministe intelligent

    Le retrieval reste 100% from scratch. Seule la génération utilise un LLM externe
    quand disponible pour améliorer la qualité des réponses.
    """
    # 1. Tenter Groq (réponses les plus naturelles)
    groq_key = settings.groq_api_key
    if groq_key and tweets:
        try:
            answer = _generate_with_groq(prompt, groq_key)
            if answer and len(answer) > 30:
                logger.info(f"[RAG] Réponse générée par Groq ({len(answer)} chars)")
                return answer
        except Exception as e:
            logger.warning(f"[RAG] Groq indisponible: {e}")

    # 2. Tenter TinyGPT from scratch
    try:
        from backend.app.services.llm_from_scratch import get_planner
        planner = get_planner()

        if planner.loaded_checkpoint and planner.model is not None:
            import torch
            ids = planner.tokenizer.encode(prompt[:400], add_bos=True)
            idx = torch.tensor([ids], dtype=torch.long)

            with torch.no_grad():
                for _ in range(300):
                    idx_cond = idx[:, -planner.model.block_size:]
                    logits = planner.model(idx_cond)
                    next_logits = logits[:, -1, :] / 0.7
                    probs = torch.softmax(next_logits, dim=-1)
                    next_id = torch.multinomial(probs, num_samples=1)
                    idx = torch.cat([idx, next_id], dim=1)
                    if int(next_id.item()) == planner.tokenizer.eos_id:
                        break

            decoded = planner.tokenizer.decode(idx[0].tolist())
            generated = decoded[len(prompt[:400]):]

            if len(generated.strip()) > 20:
                logger.info(f"[RAG] Réponse générée par TinyGPT ({len(generated)} chars)")
                return generated.strip()
    except Exception as e:
        logger.warning(f"[RAG] TinyGPT indisponible: {e}")

    # 3. Fallback déterministe
    return _generate_fallback_answer(question, tweets)


def _generate_with_groq(prompt: str, api_key: str) -> str:
    """
    Appelle l'API Groq (LLaMA 3) pour générer une réponse naturelle.
    Synchrone pour compatibilité avec le pipeline.
    """
    import httpx

    # Tracker l'usage
    try:
        import redis
        r = redis.from_url(settings.redis_url)
        r.incr("sentiflow:usage:groq_calls")
    except Exception:
        pass

    response = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "llama-3.1-8b-instant",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Tu es l'assistant d'analyse de sentiments SentiFlow. "
                        "Tu réponds en français de manière claire, structurée et analytique. "
                        "Tu cites des exemples concrets de tweets. "
                        "Tu donnes les pourcentages de chaque sentiment. "
                        "Tu es concis mais complet."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 1000,
        },
        timeout=30.0,
    )

    if response.status_code != 200:
        logger.error(f"[RAG-GROQ] Erreur: {response.status_code} {response.text[:200]}")
        return ""

    return response.json()["choices"][0]["message"]["content"]


def _generate_fallback_answer(question: str, tweets: List[Dict[str, Any]]) -> str:
    """
    Génère une réponse analytique déterministe à partir des tweets récupérés.
    C'est le fallback quand le TinyGPT n'est pas disponible.
    """
    if not tweets:
        return (
            "Je n'ai pas trouvé de tweets pertinents pour répondre à ta question. "
            "Lance d'abord une collecte sur les cibles qui t'intéressent."
        )

    # Analyse statistique
    sentiments = [t["sentiment"] for t in tweets if t.get("sentiment")]
    total = len(sentiments)
    sent_counts = Counter(sentiments)

    targets = set(t.get("target", "?") for t in tweets)
    confidences = [t["confidence"] for t in tweets if t.get("confidence")]
    avg_conf = sum(confidences) / len(confidences) if confidences else 0

    # Sentiment dominant
    dominant = sent_counts.most_common(1)[0] if sent_counts else ("inconnu", 0)
    dominant_name, dominant_count = dominant
    dominant_pct = dominant_count / total if total > 0 else 0

    # Construire la réponse
    lines = []
    lines.append(f"Analyse basée sur {total} tweets pertinents récupérés par le RAG :")
    lines.append("")

    # Distribution
    lines.append("**Distribution des sentiments :**")
    for sentiment, count in sent_counts.most_common():
        pct = count / total * 100
        lines.append(f"- {sentiment} : {count} tweets ({pct:.0f}%)")
    lines.append("")

    # Cibles couvertes
    if len(targets) > 1:
        lines.append(f"**Cibles couvertes :** {', '.join(targets)}")
        lines.append("")

    # Insight principal
    lines.append("**Lecture principale :**")
    if dominant_pct >= 0.5:
        lines.append(
            f"Le sentiment {dominant_name} domine largement ({dominant_pct:.0%}). "
            f"La tonalité est clairement orientée."
        )
    elif dominant_pct >= 0.3:
        second = sent_counts.most_common(2)[1] if len(sent_counts) > 1 else ("?", 0)
        lines.append(
            f"Le sentiment {dominant_name} est majoritaire ({dominant_pct:.0%}), "
            f"suivi de {second[0]} ({second[1]/total:.0%}). Conversation partagée."
        )
    else:
        lines.append("Les sentiments sont assez partagés, pas de tonalité dominante nette.")
    lines.append("")

    # Exemples de tweets
    lines.append("**Tweets représentatifs :**")
    shown = 0
    for t in tweets[:5]:
        text = str(t.get("text", ""))[:150].replace("\n", " ")
        if text.strip():
            lines.append(
                f"- @{t.get('author', '?')} : \"{text}\" "
                f"→ {t.get('sentiment', '?')} ({t.get('confidence', 0):.0%})"
            )
            shown += 1
            if shown >= 3:
                break
    lines.append("")

    # Confiance
    lines.append(f"**Confiance moyenne du modèle :** {avg_conf:.0%}")
    if avg_conf < 0.6:
        lines.append("⚠ Confiance faible — les résultats sont à prendre avec prudence.")

    return "\n".join(lines)


# ============================================
# MÉTRIQUES RAG FROM SCRATCH
# ============================================

def compute_retrieval_metrics(question: str, retrieved_tweets: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Métriques de qualité du retrieval (from scratch) :
    - relevance : score moyen de retrieval
    - coherence : homogénéité des sentiments
    - confidence : confiance ML moyenne
    - coverage : diversité des sources
    - mrr : Mean Reciprocal Rank (premier résultat pertinent)
    - ndcg : Normalized Discounted Cumulative Gain
    """
    if not retrieved_tweets:
        return {
            "relevance": 0, "coherence": 0, "confidence": 0,
            "coverage": 0, "total_retrieved": 0, "mrr": 0, "ndcg": 0,
        }

    # Relevance : score moyen (RRF, TF-IDF, ou BM25)
    scores = [
        t.get("rerank_score", t.get("rrf_score", t.get("tfidf_score", t.get("bm25_score", 0))))
        for t in retrieved_tweets
    ]
    avg_relevance = sum(scores) / len(scores) if scores else 0

    # Coherence : % du sentiment dominant parmi les résultats
    sentiments = [t["sentiment"] for t in retrieved_tweets if t.get("sentiment")]
    if sentiments:
        most_common_count = Counter(sentiments).most_common(1)[0][1]
        coherence = most_common_count / len(sentiments)
    else:
        coherence = 0

    # Confidence : confiance ML moyenne
    confidences = [t["confidence"] for t in retrieved_tweets if t.get("confidence")]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0

    # Coverage : nombre de cibles différentes
    targets = set(t.get("target", "") for t in retrieved_tweets)
    coverage = len(targets)

    # MRR : position du premier résultat très pertinent (score > seuil)
    threshold = 0.01
    mrr = 0.0
    for i, score in enumerate(scores):
        if score > threshold:
            mrr = 1.0 / (i + 1)
            break

    # NDCG@k (from scratch)
    ndcg = _compute_ndcg(scores, k=min(10, len(scores)))

    return {
        "relevance": round(float(avg_relevance), 4),
        "coherence": round(float(coherence), 4),
        "confidence": round(float(avg_confidence), 4),
        "coverage": coverage,
        "total_retrieved": len(retrieved_tweets),
        "mrr": round(mrr, 4),
        "ndcg": round(ndcg, 4),
    }


def _compute_ndcg(scores: List[float], k: int = 10) -> float:
    """NDCG@k (Normalized Discounted Cumulative Gain) codé from scratch."""
    if not scores:
        return 0.0
    # DCG
    dcg = 0.0
    for i, score in enumerate(scores[:k]):
        dcg += score / math.log2(i + 2)  # i+2 car log2(1) = 0
    # IDCG (scores triés parfaitement)
    ideal_scores = sorted(scores, reverse=True)
    idcg = 0.0
    for i, score in enumerate(ideal_scores[:k]):
        idcg += score / math.log2(i + 2)
    if idcg == 0:
        return 0.0
    return dcg / idcg


def compute_answer_metrics(question: str, answer: str, tweets: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Métriques de qualité de la réponse :
    - faithfulness : la réponse cite-t-elle les données fournies
    - completeness : la réponse couvre-t-elle les sentiments présents
    """
    # Faithfulness : combien d'auteurs/extraits sont cités
    cited = 0
    for t in tweets:
        author = t.get("author", "")
        if author and author != "?" and author in answer:
            cited += 1
        elif t.get("text", "")[:25] in answer:
            cited += 1
    faithfulness = cited / len(tweets) if tweets else 0

    # Completeness : sentiments présents dans la réponse
    sentiments_in_tweets = set(t["sentiment"] for t in tweets if t.get("sentiment"))
    mentioned = sum(1 for s in sentiments_in_tweets if s.lower() in answer.lower())
    completeness = mentioned / len(sentiments_in_tweets) if sentiments_in_tweets else 0

    return {
        "faithfulness": round(faithfulness, 4),
        "completeness": round(completeness, 4),
        "answer_length": len(answer),
        "cited_sources": cited,
    }


# ============================================
# PIPELINE RAG COMPLET
# ============================================

async def chat(
    db: Session,
    question: str,
    target_id: Optional[int] = None,
    enable_mcp: bool = True,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Pipeline RAG complet FUSIONNÉ :
    1. Planner LLM from scratch (TinyGPT de lseillier) → comprend l'intention + cibles
    2. Si index vide ET MCP activé → chercher sur Twitter d'abord
    3. Hybrid retrieve (TF-IDF cosine + BM25 + RRF) from scratch
    4. Re-ranking (second passage) from scratch
    5. Build prompt
    6. Generate (Groq / TinyGPT / fallback)
    7. Métriques
    """
    start = time.time()
    index = get_vector_index()
    mcp_used = False
    mcp_tweets_count = 0

    # ============================================
    # ÉTAPE 1 : PLANNER LLM FROM SCRATCH (lseillier)
    # Comprend la question, extrait l'intention et les cibles
    # ============================================
    plan = None
    try:
        from backend.app.services.llm_from_scratch import get_planner
        planner = get_planner()
        plan = planner.plan(question)
        logger.info(
            f"[RAG] Planner LLM: intent={plan.get('intent')}, "
            f"targets={plan.get('targets')}, days={plan.get('days')}, "
            f"source={plan.get('planner_source')}"
        )
    except Exception as e:
        logger.warning(f"[RAG] Planner indisponible, mode retrieval pur: {e}")

    # Extraire les cibles du plan pour améliorer la recherche
    plan_targets = plan.get("targets", []) if plan else []
    plan_intent = plan.get("intent", "summarize") if plan else "summarize"
    plan_days = plan.get("days", 7) if plan else 7
    plan_sentiment_filter = plan.get("sentiment_filter") if plan else None

    # GUARDRAIL : extraire les mentions explicites (#hashtag, @compte) de la question
    # et les utiliser en priorité sur le planner (qui peut halluciner)
    import re as _re
    explicit_targets = _re.findall(r"[#@][A-Za-z0-9_À-ÿ-]+", question)
    explicit_targets = [t.lower() for t in explicit_targets]

    # Si pas de # ou @ explicite, chercher les mots qui matchent des cibles en BDD
    if not explicit_targets and db:
        try:
            existing_targets = db.query(Target).all()
            words = set(_re.findall(r"[A-Za-z0-9_]{2,}", question.lower()))
            for target in existing_targets:
                target_name = target.name.lower().lstrip("#@")
                if target_name in words:
                    explicit_targets.append(target.name.lower())
        except Exception:
            pass

    if explicit_targets:
        plan_targets = explicit_targets
        logger.info(f"[RAG] Guardrail: cibles utilisées: {plan_targets}")

    # Construire une requête enrichie par le planner
    enriched_query = question
    if plan_targets:
        # Ajouter les cibles extraites par le planner à la requête
        enriched_query = f"{question} {' '.join(plan_targets)}"

    # ============================================
    # ÉTAPE 2 : MCP — récupère en temps réel CHAQUE cible absente de l'index
    # ============================================
    # Si l'index est vide, d'abord essayer de charger depuis la BDD
    if not index.is_fitted or index.indexed_count == 0:
        from backend.app.services.rag import index_all_tweets as _index_from_db
        db_count = _index_from_db(db, days=30)
        if db_count > 0:
            logger.info(f"[RAG] Index chargé depuis BDD: {db_count} tweets")

    def _target_present_in_index(tgt: str) -> bool:
        """Vrai si au moins un document de l'index appartient à la cible donnée."""
        if not index.is_fitted:
            return False
        needle = tgt.lower().lstrip("#@")
        for doc in index.documents:
            doc_target = str(doc.get("target", "")).lower().lstrip("#@")
            if not doc_target:
                continue
            if needle in doc_target or doc_target in needle:
                return True
        return False

    # Les cibles à vérifier : celles du plan, sinon la question brute si l'index est vide
    mcp_fetched_targets: List[str] = []
    if plan_targets:
        targets_to_fetch = list(plan_targets)
    elif not index.is_fitted or index.indexed_count == 0:
        targets_to_fetch = [question]
    else:
        targets_to_fetch = []

    if enable_mcp:
        for tgt in targets_to_fetch:
            # Pour une cible explicite (#x / @x), on ne va chercher que si elle manque.
            is_explicit_target = tgt in plan_targets
            if is_explicit_target and _target_present_in_index(tgt):
                continue
            logger.info(f"[RAG] Cible absente de l'index: '{tgt}' → appel MCP temps réel...")
            mcp_tweets = await mcp_enrich(tgt, top_k=15)
            if mcp_tweets:
                mcp_used = True
                mcp_tweets_count += len(mcp_tweets)
                if is_explicit_target:
                    mcp_fetched_targets.append(tgt)
                # Stocker en BDD (persistance) — rattaché à l'utilisateur courant
                store_mcp_tweets_in_db(db, mcp_tweets, tgt, user_id=user_id)
                # Ajouter à l'index existant
                all_docs = index.documents + mcp_tweets if index.is_fitted else mcp_tweets
                index.index_tweets(all_docs)
                logger.info(f"[RAG] {len(mcp_tweets)} tweets MCP indexés + stockés pour '{tgt}'")

        # Le cache de retrieval doit être invalidé car l'index vient de changer
        if mcp_used:
            get_query_cache().invalidate()

    # ============================================
    # ÉTAPE 3 : HYBRID RETRIEVE (from scratch)
    # ============================================
    tweets = hybrid_retrieve(
        db, enriched_query, top_k=15, target_id=target_id, enable_mcp=False
    )

    # Filtre par cibles du planner : ne garder que les tweets des cibles demandées
    if plan_targets and tweets:
        filtered_by_target = []
        for t in tweets:
            tweet_target = str(t.get("target", "")).lower().lstrip("#@")
            if any(pt.lower().lstrip("#@") in tweet_target or tweet_target in pt.lower().lstrip("#@") for pt in plan_targets):
                filtered_by_target.append(t)
        if filtered_by_target:
            tweets = filtered_by_target

    # Filtre par SENTIMENT (négatif / positif / émotion précise demandée)
    from backend.app.services.llm_from_scratch import expand_sentiment_filter
    wanted_sentiments = expand_sentiment_filter(plan_sentiment_filter)
    if wanted_sentiments:
        sent_filtered = [
            t for t in tweets
            if str(t.get("sentiment", "")).lower() in wanted_sentiments
        ]
        # Si le top-K du retrieval ne contenait pas ce sentiment, on le cherche
        # directement dans l'index complet (le tweet existe peut-être mais n'était
        # pas dans les 15 plus similaires).
        if not sent_filtered and index.is_fitted:
            pool = []
            for doc in index.documents:
                if str(doc.get("sentiment", "")).lower() not in wanted_sentiments:
                    continue
                doc_target = str(doc.get("target", "")).lower().lstrip("#@")
                if plan_targets and not any(
                    pt.lower().lstrip("#@") in doc_target or doc_target in pt.lower().lstrip("#@")
                    for pt in plan_targets
                ):
                    continue
                pool.append(doc)
            if pool:
                sent_filtered = rerank_results(enriched_query, pool, top_k=15)
        # On applique le filtre (quitte à renvoyer une liste vide : dans ce cas,
        # la réponse "aucun tweet de ce type" sera alors réellement exacte).
        tweets = sent_filtered

    # Filtre temporel : ne garder que les tweets de la période demandée
    if plan_days and plan_days < 30 and tweets:
        cutoff = datetime.utcnow() - timedelta(days=plan_days)
        filtered = []
        for t in tweets:
            date_str = t.get("analyzed_at") or t.get("created_at")
            if date_str:
                try:
                    dt = datetime.fromisoformat(str(date_str).replace("Z", ""))
                    if dt >= cutoff:
                        filtered.append(t)
                except (ValueError, TypeError):
                    filtered.append(t)  # garder si date non parsable
            else:
                filtered.append(t)  # garder si pas de date
        if filtered:  # ne pas vider complètement
            tweets = filtered

    retrieve_time = time.time() - start

    # ============================================
    # ÉTAPE 4 : MCP si pas assez de résultats (filet de sécurité, multi-cibles)
    # ============================================
    if enable_mcp and len(tweets) < 3:
        fallback_queries = list(plan_targets) if plan_targets else [question]
        for mcp_query in fallback_queries:
            logger.info(f"[RAG] {len(tweets)} résultats, appel MCP pour '{mcp_query}'...")
            mcp_tweets = await mcp_enrich(mcp_query, top_k=15)
            if mcp_tweets:
                mcp_used = True
                mcp_tweets_count += len(mcp_tweets)
                store_mcp_tweets_in_db(db, mcp_tweets, mcp_query, user_id=user_id)
                existing_ids = {r.get("id") for r in tweets}
                for t in mcp_tweets:
                    if t.get("id") not in existing_ids:
                        tweets.append(t)
        tweets = rerank_results(enriched_query, tweets, top_k=15)
        retrieve_time = time.time() - start

    # ============================================
    # ÉTAPE 5 : MÉTRIQUES RETRIEVAL
    # ============================================
    retrieval_metrics = compute_retrieval_metrics(question, tweets)

    # ============================================
    # ÉTAPE 6 : BUILD PROMPT
    # ============================================
    prompt = build_rag_prompt(question, tweets, intent=plan_intent)

    # ============================================
    # ÉTAPE 7 : GENERATE (Groq / TinyGPT / fallback)
    # ============================================
    gen_start = time.time()
    answer = generate_answer_from_scratch(question, tweets, prompt)
    gen_time = time.time() - gen_start

    # Si des cibles étaient nouvelles (aucune donnée en base), on le signale dans le chat
    if mcp_fetched_targets:
        note = (
            f"ℹ️ Nouvelle(s) cible(s) {', '.join(mcp_fetched_targets)} : "
            f"aucune donnée en base, recherche effectuée en temps réel via MCP.\n\n"
        )
        answer = note + answer

    # ============================================
    # ÉTAPE 8 : MÉTRIQUES RÉPONSE
    # ============================================
    answer_metrics = compute_answer_metrics(question, answer, tweets)

    total_time = time.time() - start
    logger.info(
        f"[RAG] Chat en {total_time:.2f}s | "
        f"planner={plan.get('planner_source', '?') if plan else 'none'} | "
        f"intent={plan_intent} | "
        f"retrieve={retrieve_time:.2f}s, generate={gen_time:.2f}s | "
        f"{len(tweets)} tweets (MCP={'oui' if mcp_used else 'non'}) | "
        f"relevance={retrieval_metrics['relevance']:.4f}"
    )

    return {
        "answer": answer,
        "sources": tweets[:5],
        "total_retrieved": len(tweets),
        "from_scratch": True,
        "mcp_used": mcp_used,
        "mcp_tweets_fetched": mcp_tweets_count,
        "mcp_fetched_targets": mcp_fetched_targets,
        "generator": _get_generator_name(),
        "plan": plan,  # Le plan du LLM from scratch
        "metrics": {
            "retrieval": retrieval_metrics,
            "answer": answer_metrics,
            "timing": {
                "total": round(total_time, 3),
                "retrieve": round(retrieve_time, 3),
                "generate": round(gen_time, 3),
            },
        },
    }


def _is_tinygpt_available() -> bool:
    """Vérifie si le TinyGPT est chargé et disponible."""
    try:
        from backend.app.services.llm_from_scratch import get_planner
        planner = get_planner()
        return planner.loaded_checkpoint and planner.model is not None
    except Exception:
        return False


def _get_generator_name() -> str:
    """Retourne le nom du générateur actif."""
    if settings.groq_api_key:
        return "groq_llama3"
    if _is_tinygpt_available():
        return "tinygpt_from_scratch"
    return "fallback_deterministic"


# ============================================
# DATASET DE TEST Q&A (chargé depuis CSV)
# ============================================

def load_eval_dataset(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Charge le dataset d'évaluation depuis le CSV."""
    path = path or EVAL_DATASET_PATH
    if not path.exists():
        logger.warning(f"[RAG] Dataset d'évaluation non trouvé: {path}")
        return _get_default_eval_questions()

    questions = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                questions.append({
                    "question": row.get("question", "").strip('"'),
                    "expected_answer_contains": [
                        w.strip() for w in row.get("expected_answer_contains", "").split(",") if w.strip()
                    ],
                    "expected_sentiments": [
                        w.strip() for w in row.get("expected_sentiments", "").split(",") if w.strip()
                    ],
                    "expected_keywords": [
                        w.strip() for w in row.get("expected_keywords", "").split(",") if w.strip()
                    ],
                    "difficulty": row.get("difficulty", "medium"),
                })
        logger.info(f"[RAG] {len(questions)} questions chargées depuis {path}")
    except Exception as e:
        logger.error(f"[RAG] Erreur lecture CSV: {e}")
        return _get_default_eval_questions()

    return questions


def _get_default_eval_questions() -> List[Dict[str, Any]]:
    """Questions de fallback si le CSV n'existe pas."""
    return [
        {
            "question": "Quel est le sentiment général sur #france ?",
            "expected_sentiments": ["joie", "colere", "tristesse"],
            "expected_keywords": ["france", "sentiment"],
            "expected_answer_contains": ["sentiment", "france"],
            "difficulty": "easy",
        },
        {
            "question": "Pourquoi les gens sont en colère sur #trump ?",
            "expected_sentiments": ["colere"],
            "expected_keywords": ["trump", "colere"],
            "expected_answer_contains": ["colere", "trump"],
            "difficulty": "easy",
        },
        {
            "question": "Les tweets sur #IA sont-ils positifs ou négatifs ?",
            "expected_sentiments": ["joie", "surprise"],
            "expected_keywords": ["IA", "positif", "negatif"],
            "expected_answer_contains": ["positif", "negatif"],
            "difficulty": "medium",
        },
        {
            "question": "Quels sont les tweets les plus tristes ?",
            "expected_sentiments": ["tristesse"],
            "expected_keywords": ["triste"],
            "expected_answer_contains": ["triste", "tristesse"],
            "difficulty": "easy",
        },
        {
            "question": "Y a-t-il de la peur dans les tweets récents ?",
            "expected_sentiments": ["peur"],
            "expected_keywords": ["peur"],
            "expected_answer_contains": ["peur"],
            "difficulty": "medium",
        },
    ]


# ============================================
# ÉVALUATION RAG + MLFLOW TRACKING
# ============================================

def _log_to_mlflow(run_name: str, params: Dict, metrics: Dict, tags: Optional[Dict] = None) -> bool:
    """Log les résultats d'évaluation dans MLflow."""
    try:
        import mlflow
        mlflow.set_tracking_uri("http://mlflow:5000")
        mlflow.set_experiment("sentiflow-rag-evaluation")

        with mlflow.start_run(run_name=run_name):
            for k, v in params.items():
                mlflow.log_param(k, v)
            for k, v in metrics.items():
                if isinstance(v, (int, float)):
                    mlflow.log_metric(k, v)
            tags = tags or {}
            tags["component"] = "rag_from_scratch"
            tags["timestamp"] = datetime.utcnow().isoformat()
            for k, v in tags.items():
                mlflow.set_tag(k, str(v))

        logger.info(f"[RAG-MLFLOW] Run '{run_name}' logged")
        return True
    except Exception as e:
        logger.warning(f"[RAG-MLFLOW] MLflow indisponible (OK en dev): {e}")
        return False


async def evaluate_rag(
    db: Session,
    log_mlflow: bool = True,
    run_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Évalue le RAG from scratch sur le dataset CSV.
    Log les métriques dans MLflow si disponible.
    Retourne un rapport détaillé.
    """
    eval_questions = load_eval_dataset()
    results = []
    start_total = time.time()

    for test in eval_questions:
        try:
            response = await chat(db, test["question"])

            # --- Métriques de retrieval ---
            retrieved_sentiments = set(
                t["sentiment"] for t in response["sources"] if t.get("sentiment")
            )
            expected_sentiments = set(test.get("expected_sentiments", []))
            sentiment_recall = (
                len(expected_sentiments & retrieved_sentiments) / len(expected_sentiments)
                if expected_sentiments else 1.0
            )

            # --- Métriques de la réponse ---
            answer_lower = response["answer"].lower()

            # Keyword recall
            expected_keywords = test.get("expected_keywords", [])
            keyword_hits = sum(1 for kw in expected_keywords if kw.lower() in answer_lower)
            keyword_recall = keyword_hits / len(expected_keywords) if expected_keywords else 1.0

            # Answer contains (vérification que la réponse contient les éléments attendus)
            expected_contains = test.get("expected_answer_contains", [])
            contains_hits = sum(1 for w in expected_contains if w.lower() in answer_lower)
            answer_precision = contains_hits / len(expected_contains) if expected_contains else 1.0

            # Score composite
            composite_score = (
                sentiment_recall * 0.3
                + keyword_recall * 0.3
                + answer_precision * 0.2
                + response["metrics"]["retrieval"].get("ndcg", 0) * 0.2
            )

            results.append({
                "question": test["question"],
                "difficulty": test.get("difficulty", "medium"),
                "sentiment_recall": round(sentiment_recall, 3),
                "keyword_recall": round(keyword_recall, 3),
                "answer_precision": round(answer_precision, 3),
                "composite_score": round(composite_score, 3),
                "retrieval_metrics": response["metrics"]["retrieval"],
                "answer_metrics": response["metrics"]["answer"],
                "timing": response["metrics"]["timing"],
                "generator_used": response["generator"],
                "retrieved_count": response["total_retrieved"],
            })
        except Exception as e:
            logger.error(f"[RAG] Erreur eval question '{test['question'][:50]}': {e}")
            results.append({
                "question": test["question"],
                "difficulty": test.get("difficulty", "medium"),
                "error": str(e),
            })

    total_time = time.time() - start_total

    # --- Agrégation des métriques ---
    valid = [r for r in results if "error" not in r]
    failed = [r for r in results if "error" in r]

    if valid:
        avg_metrics = {
            "avg_sentiment_recall": round(sum(r["sentiment_recall"] for r in valid) / len(valid), 4),
            "avg_keyword_recall": round(sum(r["keyword_recall"] for r in valid) / len(valid), 4),
            "avg_answer_precision": round(sum(r["answer_precision"] for r in valid) / len(valid), 4),
            "avg_composite_score": round(sum(r["composite_score"] for r in valid) / len(valid), 4),
            "avg_relevance": round(sum(r["retrieval_metrics"]["relevance"] for r in valid) / len(valid), 4),
            "avg_mrr": round(sum(r["retrieval_metrics"]["mrr"] for r in valid) / len(valid), 4),
            "avg_ndcg": round(sum(r["retrieval_metrics"]["ndcg"] for r in valid) / len(valid), 4),
            "avg_coherence": round(sum(r["retrieval_metrics"]["coherence"] for r in valid) / len(valid), 4),
            "avg_faithfulness": round(sum(r["answer_metrics"]["faithfulness"] for r in valid) / len(valid), 4),
            "avg_completeness": round(sum(r["answer_metrics"]["completeness"] for r in valid) / len(valid), 4),
        }

        # Métriques par difficulté
        by_difficulty = {}
        for diff in ["easy", "medium", "hard"]:
            diff_results = [r for r in valid if r.get("difficulty") == diff]
            if diff_results:
                by_difficulty[diff] = {
                    "count": len(diff_results),
                    "avg_composite": round(
                        sum(r["composite_score"] for r in diff_results) / len(diff_results), 4
                    ),
                }
    else:
        avg_metrics = {}
        by_difficulty = {}

    # --- Log MLflow ---
    mlflow_logged = False
    if log_mlflow and valid:
        run_name = run_name or f"rag_eval_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        mlflow_logged = _log_to_mlflow(
            run_name=run_name,
            params={
                "total_questions": len(eval_questions),
                "retriever": "tfidf_bm25_hybrid_rrf",
                "reranking": "contextual_temporal",
                "generator": "tinygpt_fallback",
                "query_expansion": "synonym_based",
                "index_size": get_vector_index().indexed_count,
            },
            metrics=avg_metrics,
            tags={
                "from_scratch": "true",
                "successful": str(len(valid)),
                "failed": str(len(failed)),
            },
        )

    return {
        "total_questions": len(eval_questions),
        "successful": len(valid),
        "failed": len(failed),
        "total_time": round(total_time, 2),
        "from_scratch": True,
        "mlflow_logged": mlflow_logged,
        "avg_metrics": avg_metrics,
        "by_difficulty": by_difficulty,
        "details": results,
    }
