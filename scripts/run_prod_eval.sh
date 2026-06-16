#!/bin/bash
# ============================================
# SCRIPT COMPLET : Test RAG en production
# À exécuter depuis le répertoire du projet
# ============================================

set -e

echo "============================================"
echo "🚀 SentiFlow RAG — Test en Production"
echo "============================================"
echo ""

# Couleurs
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# ============================================
# ÉTAPE 1 : Vérifier Docker
# ============================================
echo -e "${YELLOW}📦 ÉTAPE 1 : Vérification Docker${NC}"
echo "-------------------------------------------"

if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker n'est pas installé${NC}"
    exit 1
fi

if ! docker info &> /dev/null; then
    echo -e "${RED}❌ Docker daemon n'est pas démarré${NC}"
    echo "   Lance: sudo service docker start"
    exit 1
fi

echo -e "${GREEN}✅ Docker OK${NC}"
echo ""

# ============================================
# ÉTAPE 2 : Lancer les services
# ============================================
echo -e "${YELLOW}🐳 ÉTAPE 2 : Lancement des services Docker${NC}"
echo "-------------------------------------------"
echo "   (première fois ~5-10min pour build)"
echo ""

docker compose up -d --build

echo ""
echo "   Attente que les services soient prêts..."
sleep 10

# Vérifier que l'API répond
for i in {1..30}; do
    if curl -s http://localhost:8000/health | grep -q "ok"; then
        echo -e "${GREEN}✅ API prête${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}❌ L'API ne répond pas après 30 tentatives${NC}"
        echo "   Vérifie avec: docker compose logs api"
        exit 1
    fi
    echo "   Attente... ($i/30)"
    sleep 3
done

echo ""

# ============================================
# ÉTAPE 3 : Créer un compte test
# ============================================
echo -e "${YELLOW}👤 ÉTAPE 3 : Création du compte test${NC}"
echo "-------------------------------------------"

# Register (ignore l'erreur si le compte existe déjà)
curl -s -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"rag_test","email":"rag@test.fr","password":"testtest123"}' > /dev/null 2>&1 || true

# Login
LOGIN_RESPONSE=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"rag_test","password":"testtest123"}')

TOKEN=$(echo $LOGIN_RESPONSE | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
    echo -e "${RED}❌ Impossible de se connecter${NC}"
    echo "   Réponse: $LOGIN_RESPONSE"
    exit 1
fi

echo -e "${GREEN}✅ Connecté (token: ${TOKEN:0:20}...)${NC}"
echo ""

# ============================================
# ÉTAPE 4 : Vérifier l'info RAG
# ============================================
echo -e "${YELLOW}📋 ÉTAPE 4 : Info RAG${NC}"
echo "-------------------------------------------"

curl -s http://localhost:8000/rag/info \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

echo ""

# ============================================
# ÉTAPE 5 : Indexer les tweets
# ============================================
echo -e "${YELLOW}📚 ÉTAPE 5 : Indexation des tweets${NC}"
echo "-------------------------------------------"

INDEX_RESULT=$(curl -s -X POST http://localhost:8000/rag/index \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"days": 30}')

echo $INDEX_RESULT | python3 -m json.tool
echo ""

# ============================================
# ÉTAPE 6 : Tester le MCP (outils Twitter)
# ============================================
echo -e "${YELLOW}🐦 ÉTAPE 6 : Test MCP (Twitter temps réel)${NC}"
echo "-------------------------------------------"

echo "  Outils disponibles:"
curl -s http://localhost:8000/rag/mcp/tools \
  -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for tool in data.get('tools', []):
    print(f\"    • {tool['name']}: {tool['description'][:50]}...\")
"

echo ""
echo "  Test search_twitter #france:"
MCP_RESULT=$(curl -s -X POST http://localhost:8000/rag/mcp/call \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tool_name": "search_twitter", "arguments": {"query": "#france", "limit": 3}}')

echo $MCP_RESULT | python3 -c "
import sys, json
data = json.load(sys.stdin)
if 'error' in data and not data.get('tweets'):
    print(f\"    ❌ Erreur: {data.get('error','?')[:80]}\")
else:
    tweets = data.get('tweets', [])
    print(f\"    ✅ {len(tweets)} tweets récupérés\")
    for t in tweets[:2]:
        print(f\"       @{t.get('author','?')[:15]}: {t.get('text','')[:60]}...\")
"
echo ""

# ============================================
# ÉTAPE 7 : Tester le chat RAG
# ============================================
echo -e "${YELLOW}💬 ÉTAPE 7 : Test Chat RAG (question)${NC}"
echo "-------------------------------------------"

echo '  Question: "Quel est le sentiment sur #france ?"'
echo ""

CHAT_RESULT=$(curl -s -X POST http://localhost:8000/rag/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "Quel est le sentiment sur #france ?", "enable_mcp": true}')

echo $CHAT_RESULT | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f\"  📊 Résultats:\")
print(f\"     • Tweets récupérés: {data.get('total_retrieved', 0)}\")
print(f\"     • MCP utilisé: {data.get('mcp_used', False)}\")
print(f\"     • Générateur: {data.get('generator', '?')}\")
print(f\"     • Temps total: {data.get('metrics',{}).get('timing',{}).get('total',0):.2f}s\")
print(f\"\")
print(f\"  💬 Réponse:\")
answer = data.get('answer', 'Pas de réponse')
for line in answer.split(chr(10))[:8]:
    print(f\"     {line}\")
if answer.count(chr(10)) > 8:
    print(f\"     ... ({answer.count(chr(10))-8} lignes de plus)\")
"
echo ""

# ============================================
# ÉTAPE 8 : Évaluation complète + MLflow
# ============================================
echo -e "${YELLOW}🧪 ÉTAPE 8 : Évaluation RAG (20 questions + MLflow)${NC}"
echo "-------------------------------------------"
echo "  (peut prendre 30-60s...)"
echo ""

EVAL_RESULT=$(curl -s -X POST http://localhost:8000/rag/evaluate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"log_mlflow": true, "run_name": "rag_prod_eval_v1"}' \
  --max-time 120)

echo $EVAL_RESULT | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f\"  📊 RÉSULTATS ÉVALUATION RAG\")
print(f\"  ===========================\")
print(f\"  Questions: {data.get('total_questions', 0)}\")
print(f\"  Réussies: {data.get('successful', 0)}\")
print(f\"  Échouées: {data.get('failed', 0)}\")
print(f\"  Temps total: {data.get('total_time', 0):.1f}s\")
print(f\"  MLflow: {'✅ logué' if data.get('mlflow_logged') else '❌ non logué'}\")
print(f\"\")
avg = data.get('avg_metrics', {})
if avg:
    print(f\"  📈 MÉTRIQUES MOYENNES:\")
    print(f\"     • Score composite: {avg.get('avg_composite_score', 0):.2%}\")
    print(f\"     • Sentiment recall: {avg.get('avg_sentiment_recall', 0):.2%}\")
    print(f\"     • Keyword recall: {avg.get('avg_keyword_recall', 0):.2%}\")
    print(f\"     • Answer precision: {avg.get('avg_answer_precision', 0):.2%}\")
    print(f\"     • MRR: {avg.get('avg_mrr', 0):.4f}\")
    print(f\"     • NDCG: {avg.get('avg_ndcg', 0):.4f}\")
    print(f\"     • Relevance: {avg.get('avg_relevance', 0):.4f}\")
    print(f\"     • Faithfulness: {avg.get('avg_faithfulness', 0):.4f}\")
print(f\"\")
by_diff = data.get('by_difficulty', {})
if by_diff:
    print(f\"  📊 PAR DIFFICULTÉ:\")
    for diff, info in by_diff.items():
        print(f\"     [{diff}] score={info.get('avg_composite', 0):.2f} ({info.get('count', 0)} questions)\")
"
echo ""

# ============================================
# ÉTAPE 9 : Résumé final
# ============================================
echo -e "${YELLOW}============================================${NC}"
echo -e "${GREEN}✅ TEST PRODUCTION TERMINÉ${NC}"
echo -e "${YELLOW}============================================${NC}"
echo ""
echo "  📍 Services accessibles:"
echo "     • API:     http://localhost:8000/docs"
echo "     • MLflow:  http://localhost:5000"
echo "     • Frontend: http://localhost:5173"
echo ""
echo "  📍 Pour voir les logs:"
echo "     docker compose logs api --tail 20"
echo "     docker compose logs celery-worker --tail 20"
echo ""
echo "  📍 Pour arrêter:"
echo "     docker compose down"
echo ""
