"""
Test en ligne de commande : RAG from scratch + MCP (appel Twitter réel).
Usage: .venv/bin/python scripts/test_rag_mcp_live.py

Ce script teste :
1. Le chargement du dataset CSV d'évaluation
2. L'appel MCP search_twitter (temps réel)
3. L'appel MCP search_and_analyze (temps réel + sentiment)
4. Le pipeline RAG complet avec MCP activé
"""
import sys
import asyncio
import time

sys.path.insert(0, ".")


async def main():
    print("\n" + "=" * 70)
    print("🧪 TEST LIVE : RAG FROM SCRATCH + MCP (Twitter temps réel)")
    print("=" * 70)

    # =========================================
    # TEST 1 : Dataset CSV
    # =========================================
    print("\n📋 TEST 1 : Chargement du dataset CSV d'évaluation")
    print("-" * 50)
    from backend.app.services.rag import load_eval_dataset

    dataset = load_eval_dataset()
    print(f"  ✅ {len(dataset)} questions chargées")
    for i, q in enumerate(dataset[:5], 1):
        print(f"     {i}. [{q['difficulty']}] {q['question'][:60]}")
    print(f"     ... et {len(dataset) - 5} autres")

    # =========================================
    # TEST 2 : MCP search_twitter
    # =========================================
    print("\n🐦 TEST 2 : MCP Tool 'search_twitter' (appel API réel)")
    print("-" * 50)
    from backend.app.services.mcp_server import execute_tool, list_tools

    print(f"  Outils MCP disponibles: {[t['name'] for t in list_tools()]}")

    start = time.time()
    result = await execute_tool("search_twitter", {"query": "#france", "limit": 5})
    elapsed = time.time() - start

    if "error" in result and not result.get("tweets"):
        print(f"  ❌ Erreur API Twitter: {result.get('error', 'inconnu')[:100]}")
        print("  → Vérifie ta clé TWITTER_API_KEY dans le .env")
        twitter_ok = False
    else:
        tweets = result.get("tweets", [])
        print(f"  ✅ {len(tweets)} tweets récupérés en {elapsed:.2f}s")
        for t in tweets[:3]:
            print(f"     • @{t['author'][:15]}: \"{t['text'][:80]}...\"")
        twitter_ok = True

    # =========================================
    # TEST 3 : MCP search_and_analyze
    # =========================================
    print("\n🤖 TEST 3 : MCP Tool 'search_and_analyze' (Twitter + Sentiment)")
    print("-" * 50)

    if not twitter_ok:
        print("  ⏭  Skipped (Twitter API non disponible)")
    else:
        start = time.time()
        result = await execute_tool("search_and_analyze", {"query": "#france", "limit": 5})
        elapsed = time.time() - start

        if "error" in result and not result.get("tweets"):
            print(f"  ❌ Erreur: {result.get('error', 'inconnu')[:100]}")
        else:
            analyzed = result.get("tweets", [])
            dist = result.get("sentiment_distribution", {})
            dominant = result.get("dominant_sentiment", "?")
            print(f"  ✅ {len(analyzed)} tweets analysés en {elapsed:.2f}s")
            print(f"  📊 Sentiment dominant: {dominant}")
            print(f"  📊 Distribution: {dist}")
            for t in analyzed[:3]:
                print(f"     • @{t['author'][:15]} → {t['sentiment']} ({t['confidence']:.0%})")
                print(f"       \"{t['text'][:70]}...\"")

    # =========================================
    # TEST 4 : Pipeline RAG complet + MCP
    # =========================================
    print("\n🔍 TEST 4 : Pipeline RAG complet (BDD vide → MCP activé)")
    print("-" * 50)

    if not twitter_ok:
        print("  ⏭  Skipped (Twitter API non disponible)")
    else:
        # On simule un chat RAG sans BDD (donc le MCP va se déclencher)
        from backend.app.services.rag import (
            get_vector_index,
            build_rag_prompt,
            generate_answer_from_scratch,
            rerank_results,
            compute_retrieval_metrics,
            mcp_enrich,
        )

        question = "Quel est le sentiment sur #france ?"
        print(f"  Question: \"{question}\"")
        print(f"  Index local: {get_vector_index().indexed_count} tweets indexés")

        # Appeler le MCP pour enrichir
        start = time.time()
        mcp_tweets = await mcp_enrich(question, top_k=10)
        elapsed = time.time() - start

        if not mcp_tweets:
            print(f"  ⚠  MCP n'a pas retourné de tweets ({elapsed:.2f}s)")
        else:
            print(f"  ✅ MCP a récupéré {len(mcp_tweets)} tweets en {elapsed:.2f}s")

            # Re-rank
            reranked = rerank_results(question, mcp_tweets, top_k=5)
            print(f"  📊 Après re-ranking: {len(reranked)} tweets retenus")

            # Métriques retrieval
            metrics = compute_retrieval_metrics(question, reranked)
            print(f"  📈 Métriques retrieval:")
            print(f"     • Relevance: {metrics['relevance']:.4f}")
            print(f"     • Cohérence: {metrics['coherence']:.4f}")
            print(f"     • MRR: {metrics['mrr']:.4f}")
            print(f"     • NDCG: {metrics['ndcg']:.4f}")
            print(f"     • Coverage: {metrics['coverage']} cibles")

            # Générer la réponse
            prompt = build_rag_prompt(question, reranked)
            answer = generate_answer_from_scratch(question, reranked, prompt)
            print(f"\n  💬 Réponse générée ({len(answer)} chars):")
            print("  " + "-" * 40)
            for line in answer.split("\n")[:12]:
                print(f"  {line}")
            if answer.count("\n") > 12:
                print(f"  ... ({answer.count(chr(10)) - 12} lignes de plus)")

    # =========================================
    # TEST 5 : Évaluation complète sur le CSV (mode offline)
    # =========================================
    print("\n\n📊 TEST 5 : Évaluation RAG sur le dataset CSV (mode offline)")
    print("-" * 50)
    print("  (Ce test utilise l'index local, pas le MCP)")

    from backend.app.services.rag import VectorIndex, rerank_results as rr
    from backend.app.services.rag import (
        build_rag_prompt as bp,
        generate_answer_from_scratch as gen,
        compute_retrieval_metrics as crm,
        compute_answer_metrics as cam,
    )

    # Simuler avec des tweets de test
    test_tweets = [
        {"id": 1, "text": "La France est en fête, quelle joie!", "sentiment": "joie", "confidence": 0.9, "author": "fan1", "target": "#france", "target_id": 1, "analyzed_at": "2026-06-08T12:00:00"},
        {"id": 2, "text": "Trump déclenche la colère des internautes", "sentiment": "colere", "confidence": 0.85, "author": "news", "target": "#trump", "target_id": 2, "analyzed_at": "2026-06-08T10:00:00"},
        {"id": 3, "text": "Je suis triste pour la France ce soir", "sentiment": "tristesse", "confidence": 0.8, "author": "citoyen", "target": "#france", "target_id": 1, "analyzed_at": "2026-06-07T22:00:00"},
        {"id": 4, "text": "L'IA me surprend chaque jour davantage", "sentiment": "surprise", "confidence": 0.75, "author": "dev", "target": "#ia", "target_id": 3, "analyzed_at": "2026-06-08T14:00:00"},
        {"id": 5, "text": "J'ai peur de l'avenir politique", "sentiment": "peur", "confidence": 0.7, "author": "inquiet", "target": "#politique", "target_id": 4, "analyzed_at": "2026-06-06T08:00:00"},
        {"id": 6, "text": "Le PSG me rend heureux ce soir", "sentiment": "joie", "confidence": 0.88, "author": "psg_fan", "target": "#psg", "target_id": 5, "analyzed_at": "2026-06-08T21:00:00"},
    ]

    index = VectorIndex()
    index.index_tweets(test_tweets)
    print(f"  Index simulé: {index.indexed_count} tweets, vocab={index.vectorizer.vocab_size}")

    # Évaluer sur 5 premières questions du CSV
    scores = []
    for q_data in dataset[:5]:
        question = q_data["question"]
        results = index.hybrid_search(question, top_k=5)
        results = rr(question, results, top_k=3)

        # Vérifier sentiments
        retrieved_sents = set(r.get("sentiment", "") for r in results)
        expected_sents = set(q_data.get("expected_sentiments", []))
        sent_recall = len(expected_sents & retrieved_sents) / len(expected_sents) if expected_sents else 1.0

        # Générer réponse
        prompt = bp(question, results)
        answer = gen(question, results, prompt)

        # Keyword recall
        expected_kw = q_data.get("expected_keywords", [])
        kw_hits = sum(1 for kw in expected_kw if kw.lower() in answer.lower())
        kw_recall = kw_hits / len(expected_kw) if expected_kw else 1.0

        score = sent_recall * 0.5 + kw_recall * 0.5
        scores.append(score)

        status = "✅" if score >= 0.5 else "⚠ "
        print(f"  {status} [{q_data['difficulty']}] \"{question[:50]}...\"")
        print(f"      sent_recall={sent_recall:.2f}, kw_recall={kw_recall:.2f}, score={score:.2f}")

    avg_score = sum(scores) / len(scores) if scores else 0
    print(f"\n  📊 Score moyen: {avg_score:.2f}/1.00")

    # =========================================
    # RÉSUMÉ
    # =========================================
    print("\n" + "=" * 70)
    print("📋 RÉSUMÉ DES TESTS")
    print("=" * 70)
    print(f"  1. Dataset CSV         : ✅ {len(dataset)} questions chargées")
    print(f"  2. MCP search_twitter  : {'✅' if twitter_ok else '❌'}")
    print(f"  3. MCP search+analyze  : {'✅' if twitter_ok else '❌'}")
    print(f"  4. RAG + MCP pipeline  : {'✅' if twitter_ok else '⏭ '}")
    print(f"  5. Évaluation CSV      : ✅ score={avg_score:.2f}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
