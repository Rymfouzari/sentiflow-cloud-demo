"""
Test des nouvelles features : temporalité, feedback loop, PDF
"""
import sys
sys.path.insert(0, "/app")
import httpx

BASE = "http://localhost:8000"

# Login
r = httpx.post(f"{BASE}/auth/login", json={"email": "test@test.fr", "password": "azerty"})
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

print("=" * 60)
print("TEST NOUVELLES FEATURES")
print("=" * 60)

# 1. TEMPORALITÉ
print("\n📅 TEST 1: TEMPORALITÉ (7 derniers jours)")
print("-" * 40)
r = httpx.post(f"{BASE}/assistant/chat",
    json={"question": "sentiment sur #france des 7 derniers jours", "enable_mcp": True},
    headers=headers, timeout=120)
data = r.json()
print(f"Mode: {data.get('mode')}")
print(f"Réponse: {data.get('answer', '')[:300]}")

# 2. FEEDBACK LOOP
print("\n\n🔁 TEST 2: FEEDBACK LOOP")
print("-" * 40)
r = httpx.post(f"{BASE}/assistant/feedback",
    json={
        "question": "quel est le sentiment sur #france ?",
        "previous_answer": "Le sentiment est positif à 60%.",
        "feedback": "réponse trop vague, je veux plus de détails et des exemples concrets",
        "regenerate_mode": "auto",
    },
    headers=headers, timeout=60)
if r.status_code == 200:
    data = r.json()
    print(f"Mode feedback: {data.get('mode')}")
    print(f"Feedback appliqué: {data.get('feedback_applied')}")
    print(f"Nouvelle réponse: {data.get('answer', '')[:300]}")
else:
    print(f"Erreur {r.status_code}: {r.text[:200]}")

# 3. PDF EXPORT
print("\n\n📄 TEST 3: EXPORT PDF")
print("-" * 40)
r = httpx.post(f"{BASE}/assistant/export-pdf",
    json={
        "question": "Quel est le sentiment sur #france ?",
        "answer": "Le sentiment dominant est la joie (60%). Les tweets positifs parlent de victoires sportives.",
        "sources": [
            {"author": "fan1", "sentiment": "joie", "confidence": 0.95, "text": "La France a gagné!"},
            {"author": "news", "sentiment": "colere", "confidence": 0.8, "text": "Scandale politique"},
        ],
        "metrics": {"retrieval": {"relevance": 0.85, "coherence": 0.7, "mrr": 1.0}, "timing": {"total": 2.5}},
    },
    timeout=30)
if r.status_code == 200:
    pdf_size = len(r.content)
    print(f"✅ PDF généré: {pdf_size} bytes")
    # Sauvegarder le PDF
    with open("/app/backend/test_rapport.pdf", "wb") as f:
        f.write(r.content)
    print(f"   Sauvegardé: /app/backend/test_rapport.pdf")
else:
    print(f"❌ Erreur {r.status_code}: {r.text[:200]}")

print("\n" + "=" * 60)
print("✅ TESTS TERMINÉS")
print("=" * 60)
