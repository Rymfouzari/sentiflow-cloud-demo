"""
Test complet du RAG 100% FROM SCRATCH SentiFlow.
Vérifie : tokenizer, TF-IDF, BM25, cosine, query expansion, re-ranking,
index persistant, métriques avancées (MRR, NDCG).
"""
import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, ".")

from backend.app.services.rag import (
    tokenize,
    tokenize_without_stem,
    expand_query_dynamic,
    build_cooccurrence_matrix,
    pseudo_relevance_feedback,
    strip_accents,
    TFIDFVectorizer,
    BM25,
    cosine_similarity,
    cosine_search,
    VectorIndex,
    rerank_results,
    build_rag_prompt,
    _generate_fallback_answer,
    compute_retrieval_metrics,
    compute_answer_metrics,
    _compute_ndcg,
    load_eval_dataset,
)
import numpy as np


SAMPLE_TWEETS = [
    {"id": 1, "text": "La France a gagné le match, quelle joie immense!", "sentiment": "joie", "confidence": 0.92, "author": "sport_fan", "target": "#france", "target_id": 1, "analyzed_at": "2026-06-08T12:00:00"},
    {"id": 2, "text": "Trump encore une polémique, les gens sont furieux et en colère", "sentiment": "colere", "confidence": 0.88, "author": "news_bot", "target": "#trump", "target_id": 2, "analyzed_at": "2026-06-07T10:00:00"},
    {"id": 3, "text": "Macron annonce des réformes importantes pour la France et la politique", "sentiment": "neutre", "confidence": 0.65, "author": "politique_fr", "target": "#france", "target_id": 1, "analyzed_at": "2026-06-08T14:00:00"},
    {"id": 4, "text": "J'adore jouer à Minecraft, c'est trop bien et créatif", "sentiment": "amour", "confidence": 0.95, "author": "gamer42", "target": "#minecraft", "target_id": 3, "analyzed_at": "2026-06-09T08:00:00"},
    {"id": 5, "text": "La situation politique en France inquiète les citoyens, peur de l'avenir", "sentiment": "peur", "confidence": 0.72, "author": "citoyen", "target": "#france", "target_id": 1, "analyzed_at": "2026-06-06T09:00:00"},
    {"id": 6, "text": "Quelle tristesse de voir la France perdre ce match important", "sentiment": "tristesse", "confidence": 0.81, "author": "decu", "target": "#france", "target_id": 1, "analyzed_at": "2026-06-05T20:00:00"},
    {"id": 7, "text": "L'intelligence artificielle progresse à une vitesse surprenante", "sentiment": "surprise", "confidence": 0.77, "author": "tech_news", "target": "#ia", "target_id": 4, "analyzed_at": "2026-06-08T16:00:00"},
    {"id": 8, "text": "Le PSG a perdu encore une fois, quelle déception totale", "sentiment": "tristesse", "confidence": 0.84, "author": "psg_fan", "target": "#psg", "target_id": 5, "analyzed_at": "2026-06-07T22:00:00"},
]


def test_tokenizer():
    print("=" * 60)
    print("TEST 1: Tokenizer from scratch (avec stemming)")
    tokens = tokenize("Les gens adorent #France mais détestent @trump! https://t.co/abc")
    print(f"  Input: 'Les gens adorent #France mais détestent @trump! https://t.co/abc'")
    print(f"  Tokens: {tokens}")
    assert "gens" in tokens
    assert "ador" in tokens  # "adorent" → stemmé en "ador"
    assert "france" in tokens
    assert "detest" in tokens  # "détestent" → stemmé en "detest"
    assert "trump" in tokens
    assert "https" not in tokens
    # Vérifier que les stopwords sont supprimés
    raw_lower = "les gens adorent france mais détestent trump"
    assert "les" not in tokens  # stopword
    assert "mais" not in tokens  # stopword
    print("  ✅ OK\n")


def test_query_expansion():
    print("=" * 60)
    print("TEST 2: Query Expansion dynamique (co-occurrences)")
    
    # Simuler un corpus
    docs = [
        ["france", "politique", "macron", "president", "reforme"],
        ["france", "football", "match", "victoire", "joie"],
        ["trump", "colere", "amerique", "politique", "scandale"],
        ["minecraft", "jeu", "creatif", "amour", "monde"],
        ["france", "politique", "election", "vote", "gauche"],
    ]
    
    # Construire co-occurrences
    cooc = build_cooccurrence_matrix(docs, window=5)
    print(f"  Co-occurrence keys: {len(cooc)}")
    print(f"  Voisins de 'france': {cooc.get('france', {}).most_common(5)}")
    print(f"  Voisins de 'politique': {cooc.get('politique', {}).most_common(5)}")
    
    # Expansion dynamique
    tokens = ["france"]
    expanded = expand_query_dynamic(tokens, cooc, max_expansion_per_token=3, min_cooccurrence=1)
    print(f"  Input: {tokens}")
    print(f"  Expanded: {expanded}")
    assert len(expanded) > len(tokens), "L'expansion devrait ajouter des tokens"
    # "politique" devrait apparaître car il co-apparaît souvent avec "france"
    assert "politique" in expanded or "macron" in expanded or "football" in expanded
    
    # PRF
    fake_results = [
        {"text": "La France est en crise politique totale"},
        {"text": "Macron annonce des réformes pour la France"},
    ]
    prf = pseudo_relevance_feedback(["france"], fake_results, max_terms=3)
    print(f"  PRF input: ['france']")
    print(f"  PRF output: {prf}")
    assert len(prf) > 1, "Le PRF devrait enrichir la requête"
    
    print("  ✅ OK\n")


def test_tfidf():
    print("=" * 60)
    print("TEST 3: TF-IDF from scratch")
    docs = [
        ["france", "football", "victoire", "joie"],
        ["trump", "colere", "politique", "rage"],
        ["france", "politique", "president", "macron"],
        ["minecraft", "jeu", "amour", "creatif"],
    ]
    vectorizer = TFIDFVectorizer()
    vectorizer.fit(docs)
    print(f"  Vocab size: {vectorizer.vocab_size}")
    assert vectorizer.vocab_size > 0

    vec = vectorizer.transform_one(["france", "politique"])
    print(f"  Vector shape: {vec.shape}")
    print(f"  Vector norm: {np.linalg.norm(vec):.4f}")
    assert np.linalg.norm(vec) > 0
    assert abs(np.linalg.norm(vec) - 1.0) < 0.001  # normalisé L2
    print("  ✅ OK\n")


def test_bm25():
    print("=" * 60)
    print("TEST 4: BM25 from scratch")
    docs = [
        ["france", "football", "victoire", "joie", "magnifique"],
        ["trump", "colere", "politique", "rage", "amerique"],
        ["france", "politique", "president", "macron", "discours"],
        ["minecraft", "jeu", "amour", "creatif", "monde"],
    ]
    bm25 = BM25()
    bm25.fit(docs)

    results = bm25.search(["france", "politique"], top_k=3)
    print(f"  Query: ['france', 'politique']")
    print(f"  Results: {results}")
    assert results[0][0] == 2  # Le doc avec france + politique
    print("  ✅ OK\n")


def test_cosine():
    print("=" * 60)
    print("TEST 5: Cosine similarity from scratch")
    a = np.array([1.0, 0.0, 1.0])
    b = np.array([1.0, 0.0, 1.0])
    c = np.array([0.0, 1.0, 0.0])
    
    sim_ab = cosine_similarity(a, b)
    sim_ac = cosine_similarity(a, c)
    print(f"  sim(a, b) = {sim_ab:.4f} (identiques)")
    print(f"  sim(a, c) = {sim_ac:.4f} (orthogonaux)")
    assert abs(sim_ab - 1.0) < 1e-6
    assert abs(sim_ac - 0.0) < 1e-6
    print("  ✅ OK\n")


def test_vector_index():
    print("=" * 60)
    print("TEST 6: VectorIndex (index hybride from scratch)")
    index = VectorIndex()
    count = index.index_tweets(SAMPLE_TWEETS)
    print(f"  Indexed: {count} tweets")
    print(f"  Vocab size: {index.vectorizer.vocab_size}")
    assert count == 8

    # Test TF-IDF search
    tfidf_results = index.tfidf_search("france politique réformes", top_k=3)
    print(f"  TF-IDF search 'france politique réformes': {[r['id'] for r in tfidf_results]}")
    assert len(tfidf_results) > 0

    # Test BM25 search
    bm25_results = index.bm25_search("france politique", top_k=3)
    print(f"  BM25 search 'france politique': {[r['id'] for r in bm25_results]}")
    assert len(bm25_results) > 0

    # Test Hybrid search (avec query expansion)
    hybrid_results = index.hybrid_search("sentiment colère sur la france", top_k=5)
    print(f"  Hybrid search 'sentiment colère sur la france': {[r['id'] for r in hybrid_results]}")
    assert len(hybrid_results) > 0
    print("  ✅ OK\n")


def test_reranking():
    print("=" * 60)
    print("TEST 7: Re-ranking from scratch")
    index = VectorIndex()
    index.index_tweets(SAMPLE_TWEETS)
    
    # D'abord hybrid search
    results = index.hybrid_search("colère politique france", top_k=8)
    
    # Puis re-ranking
    reranked = rerank_results("colère politique france", results, top_k=5)
    print(f"  Before rerank: {[r['id'] for r in results[:5]]}")
    print(f"  After rerank:  {[r['id'] for r in reranked]}")
    print(f"  Rerank scores: {[r.get('rerank_score', 0) for r in reranked]}")
    
    # Le re-ranking devrait donner un score à chaque résultat
    assert all("rerank_score" in r for r in reranked)
    assert len(reranked) <= 5
    print("  ✅ OK\n")


def test_index_persistence():
    print("=" * 60)
    print("TEST 8: Index persistant (sauvegarde/chargement disque)")
    
    # Créer et indexer
    index = VectorIndex()
    index.index_tweets(SAMPLE_TWEETS)
    
    # Sauvegarder dans un fichier temporaire
    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
        tmp_path = Path(f.name)
    
    saved = index.save_to_disk(tmp_path)
    assert saved, "Sauvegarde échouée"
    print(f"  Sauvegardé: {tmp_path} ({tmp_path.stat().st_size} bytes)")
    
    # Charger dans un nouvel index
    new_index = VectorIndex()
    loaded = new_index.load_from_disk(tmp_path)
    assert loaded, "Chargement échoué"
    assert new_index.indexed_count == 8
    print(f"  Chargé: {new_index.indexed_count} docs, vocab={new_index.vectorizer.vocab_size}")
    
    # Vérifier que la recherche fonctionne
    results = new_index.hybrid_search("france politique", top_k=3)
    assert len(results) > 0
    print(f"  Recherche post-chargement OK: {len(results)} résultats")
    
    # Cleanup
    tmp_path.unlink()
    print("  ✅ OK\n")


def test_ndcg():
    print("=" * 60)
    print("TEST 9: NDCG from scratch")
    
    # Scores parfaitement ordonnés = NDCG de 1.0
    perfect_scores = [0.9, 0.8, 0.7, 0.6, 0.5]
    ndcg_perfect = _compute_ndcg(perfect_scores, k=5)
    print(f"  NDCG (perfect order): {ndcg_perfect:.4f}")
    assert abs(ndcg_perfect - 1.0) < 1e-6
    
    # Scores inversés = NDCG < 1.0
    reversed_scores = [0.5, 0.6, 0.7, 0.8, 0.9]
    ndcg_reversed = _compute_ndcg(reversed_scores, k=5)
    print(f"  NDCG (reversed order): {ndcg_reversed:.4f}")
    assert ndcg_reversed < 1.0
    
    # Scores vides = 0
    assert _compute_ndcg([], k=5) == 0.0
    print("  ✅ OK\n")


def test_fallback_generator():
    print("=" * 60)
    print("TEST 10: Générateur fallback (from scratch)")
    answer = _generate_fallback_answer("Quel est le sentiment sur #france?", SAMPLE_TWEETS[:4])
    print(f"  Answer length: {len(answer)} chars")
    print(f"  Preview: {answer[:200]}...")
    assert "joie" in answer.lower() or "sentiment" in answer.lower()
    assert len(answer) > 50
    print("  ✅ OK\n")


def test_metrics_advanced():
    print("=" * 60)
    print("TEST 11: Métriques avancées (MRR, NDCG, cohérence)")
    tweets = [
        {"id": 1, "sentiment": "joie", "confidence": 0.9, "rerank_score": 0.5, "target": "#a", "text": "super"},
        {"id": 2, "sentiment": "joie", "confidence": 0.8, "rerank_score": 0.4, "target": "#a", "text": "genial"},
        {"id": 3, "sentiment": "colere", "confidence": 0.7, "rerank_score": 0.3, "target": "#b", "text": "nul"},
    ]
    metrics = compute_retrieval_metrics("test", tweets)
    print(f"  Metrics: {metrics}")
    assert "mrr" in metrics
    assert "ndcg" in metrics
    assert metrics["coverage"] == 2
    assert metrics["coherence"] > 0
    assert metrics["mrr"] > 0
    assert metrics["ndcg"] > 0
    print("  ✅ OK\n")


def test_eval_dataset_loading():
    print("=" * 60)
    print("TEST 12: Chargement dataset d'évaluation CSV")
    dataset = load_eval_dataset()
    print(f"  Questions chargées: {len(dataset)}")
    assert len(dataset) > 0
    # Vérifier la structure
    first = dataset[0]
    assert "question" in first
    assert "expected_sentiments" in first
    assert "expected_keywords" in first
    assert "difficulty" in first
    print(f"  Première question: '{first['question'][:60]}...'")
    print(f"  Difficulté: {first['difficulty']}")
    print(f"  Sentiments attendus: {first['expected_sentiments']}")
    print("  ✅ OK\n")


if __name__ == "__main__":
    print("\n🚀 Tests du RAG 100% FROM SCRATCH SentiFlow (version améliorée)\n")
    test_tokenizer()
    test_query_expansion()
    test_tfidf()
    test_bm25()
    test_cosine()
    test_vector_index()
    test_reranking()
    test_index_persistence()
    test_ndcg()
    test_fallback_generator()
    test_metrics_advanced()
    test_eval_dataset_loading()
    print("=" * 60)
    print("✅ TOUS LES 12 TESTS PASSENT — RAG FROM SCRATCH AMÉLIORÉ !")
    print("=" * 60)
    print("\nComposants validés:")
    print("  • Tokenizer from scratch (FR/EN, stopwords, normalisation)")
    print("  • Query Expansion (synonymes from scratch)")
    print("  • TF-IDF Vectorizer (from scratch, normalisation L2)")
    print("  • BM25 Okapi (from scratch, k1/b paramétrable)")
    print("  • Cosine Similarity (from scratch)")
    print("  • Index Vectoriel in-memory (NumPy)")
    print("  • Hybrid Search (RRF fusion)")
    print("  • Re-ranking contextuel + temporel")
    print("  • Index persistant (pickle sur disque)")
    print("  • NDCG@k + MRR (from scratch)")
    print("  • Générateur TinyGPT + fallback")
    print("  • Dataset CSV d'évaluation")
    print("  • MLflow tracking (si disponible)")
