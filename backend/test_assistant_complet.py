"""
Test complet de l'assistant unifié via /assistant/chat
Teste : collecte, analyse, temporalité, comparaison, question SQL
"""
import asyncio
import sys
import time
sys.path.insert(0, "/app")

import httpx

BASE = "http://localhost:8000"

# Login
r = httpx.post(f"{BASE}/auth/login", json={"email": "test@test.fr", "password": "azerty"})
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}


def ask(question):
    print(f"\n{'='*60}")
    print(f"Q: {question}")
    print("-" * 60)
    r = httpx.post(
        f"{BASE}/assistant/chat",
        json={"question": question, "enable_mcp": True},
        headers=headers,
        timeout=120,
    )
    data = r.json()
    print(f"Mode: {data.get('mode')}")
    if data.get("mcp_used"):
        print(f"MCP: oui ({data.get('mcp_tweets_fetched', '?')} tweets)")
    if data.get("sources"):
        print(f"Sources: {len(data.get('sources', []))} tweets")
    if data.get("dashboard_url"):
        print(f"Dashboard: {data.get('dashboard_url')}")
    print(f"Réponse: {data.get('answer', '')[:400]}")
    return data


print("\n" + "=" * 60)
print("🧪 TEST COMPLET ASSISTANT UNIFIÉ")
print("=" * 60)

# 1. COLLECTE
print("\n\n📥 TEST 1: COLLECTE (Agent)")
ask("récupère les tweets avec #BTS")

time.sleep(2)

# 2. ANALYSE SENTIMENT
print("\n\n🔍 TEST 2: ANALYSE SENTIMENT (RAG)")
ask("quel est le sentiment dominant sur #BTS ?")

# 3. TEMPORALITÉ
print("\n\n📈 TEST 3: TEMPORALITÉ")
ask("est-ce que la joie augmente sur #france ces derniers jours ?")

# 4. COMPARAISON
print("\n\n⚖️ TEST 4: COMPARAISON")
ask("compare les sentiments entre #BTS et #france")

# 5. QUESTION SQL (quelles cibles)
print("\n\n🗄️ TEST 5: QUESTION BASE DE DONNÉES")
ask("quels sont mes cibles et combien de tweets j'ai ?")

# 6. QUESTION HARD (compte Twitter)
print("\n\n💪 TEST 6: QUESTION HARD (compte)")
ask("quels comptes génèrent le plus de colère parmi mes données ?")

# 7. RÉPARTITION DES LANGUES
print("\n\n🌍 TEST 7: RÉPARTITION DES LANGUES")
ask("quelle est la répartition des langues dans mes tweets ?")

# 8. FILTRE TEMPOREL
print("\n\n📅 TEST 8: FILTRE TEMPOREL (7 derniers jours)")
ask("quels sont les sentiments sur #france des 7 derniers jours ?")

print("\n\n" + "=" * 60)
print("✅ TEST TERMINÉ")
print("=" * 60)
