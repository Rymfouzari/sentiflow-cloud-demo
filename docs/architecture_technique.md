# SentiFlow - Architecture Technique

## 1. Vue d'ensemble

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              UTILISATEUR                                     │
│                                  │                                           │
│                    ┌─────────────┴─────────────┐                            │
│                    ▼                           ▼                            │
│           ┌───────────────┐           ┌───────────────┐                    │
│           │   DASHBOARD   │           │   CHAT LLM   │                     │
│           │  (Streamlit)  │           │  (Streamlit)  │                     │
│           └───────┬───────┘           └───────┬───────┘                    │
│                   │                           │                             │
│                   │ HTTP/REST                 │ HTTP/REST                   │
│                   ▼                           ▼                             │
│           ┌───────────────────────────────────────────┐                    │
│           │              FASTAPI (Backend)            │                    │
│           └───────────────────┬───────────────────────┘                    │
│                               │                                             │
│         ┌─────────────────────┼─────────────────────┐                      │
│         │                     │                     │                       │
│         ▼                     ▼                     ▼                       │
│  ┌─────────────┐      ┌─────────────┐      ┌─────────────┐                 │
│  │ POSTGRESQL  │      │   CELERY    │      │  LLM + MCP  │                 │
│  │   (BDD)     │      │  (Workers)  │      │  (PyTorch)  │                 │
│  └─────────────┘      └──────┬──────┘      └──────┬──────┘                 │
│         ▲                    │                    │                         │
│         │                    ▼                    │                         │
│         │            ┌─────────────┐              │                         │
│         │            │  SENTIMENT  │              │                         │
│         │            │   MODEL     │              │                         │
│         │            └─────────────┘              │                         │
│         │                    │                    │                         │
│         │                    ▼                    ▼                         │
│         │            ┌───────────────────────────────┐                     │
│         └────────────│        TWITTER API            │◄────────────────────┘
│                      └───────────────────────────────┘                      │
│                           ▲               ▲                                 │
│                           │               │                                 │
│                      Collecte auto    Requête LLM                          │
│                      (Celery)         (MCP temps réel)                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 2. Deux modes d'accès à Twitter

```
MODE 1 : COLLECTE AUTOMATIQUE (Celery)
─────────────────────────────────────────
  Celery Beat (toutes les 15 min)
       │
       ▼
  Twitter API → Tweets → Sentiment Model → PostgreSQL → Dashboard
  
  ✅ Données pré-collectées
  ✅ Réponse instantanée
  ❌ Limité aux cibles suivies


MODE 2 : REQUÊTE TEMPS RÉEL (LLM + MCP)
─────────────────────────────────────────
  User : "Sentiment de #Macron ?"
       │
       ▼
  LLM décide d'utiliser l'outil MCP
       │
       ▼
  MCP → Twitter API → Tweets → Sentiment Model → LLM → Réponse
  
  ✅ N'importe quel # ou @
  ✅ Dynamique
  ❌ Plus lent (5-10 sec)
```

## 3. Composants détaillés

### Frontend (Streamlit)
```
┌─────────────────────────────────────────┐
│              STREAMLIT                   │
│                                         │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │ Login   │ │Dashboard│ │ Alertes │   │
│  │ Page    │ │ Page    │ │ Page    │   │
│  └─────────┘ └─────────┘ └─────────┘   │
│                                         │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │ Compare │ │  Chat   │ │Settings │   │
│  │ Page    │ │  LLM    │ │ Page    │   │
│  └─────────┘ └─────────┘ └─────────┘   │
│                                         │
│  Librairies : Plotly, Altair (graphes) │
└─────────────────────────────────────────┘
```

### Backend (FastAPI)
```
┌─────────────────────────────────────────┐
│              FASTAPI                     │
│                                         │
│  Routes :                               │
│  ├─ /auth     (login, register, JWT)    │
│  ├─ /tweets   (CRUD tweets)             │
│  ├─ /analysis (sentiments)              │
│  ├─ /alerts   (CRUD alertes)            │
│  ├─ /compare  (comparaisons)            │
│  ├─ /chat     (LLM + MCP)               │
│  └─ /publish  (post Twitter)            │
│                                         │
│  Middleware : CORS, Auth JWT            │
└─────────────────────────────────────────┘
```

### Pipeline de données (Celery)
```
┌─────────────────────────────────────────┐
│              CELERY                      │
│                                         │
│  Tâches planifiées :                    │
│  ├─ collect_tweets (toutes les 15 min)  │
│  ├─ analyze_sentiment (à chaque tweet)  │
│  ├─ check_alerts (toutes les 5 min)     │
│  └─ train_drl (quotidien)               │
│                                         │
│  Broker : Redis                         │
└─────────────────────────────────────────┘
```

### Modèles ML (PyTorch)
```
┌─────────────────────────────────────────┐
│           MODÈLES ML                     │
│                                         │
│  1. Sentiment Analysis (Fine-tuning)    │
│     └─ CamemBERT fine-tuné              │
│     └─ 6 classes : joie, colère,        │
│        tristesse, peur, surprise, neutre│
│                                         │
│  2. LLM (From Scratch)                  │
│     └─ Transformer custom               │
│     └─ Tokenizer custom                 │
│     └─ RAG pour contexte                │
│                                         │
│  3. DRL (Stable-Baselines3)             │
│     └─ Optimisation publication         │
│     └─ Ajustement alertes               │
└─────────────────────────────────────────┘
```

### MCP Server
```
┌─────────────────────────────────────────┐
│           MCP SERVER                     │
│                                         │
│  Outils exposés au LLM :                │
│  ├─ search_tweets(query, limit)         │
│  ├─ get_sentiment(account/hashtag)      │
│  ├─ generate_dashboard(data)            │
│  ├─ create_alert(condition)             │
│  ├─ post_tweet(content)                 │
│  └─ compare(sources[])                  │
│                                         │
│  Le LLM décide quel outil utiliser      │
└─────────────────────────────────────────┘
```

## 3. Flux de données principal

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ Twitter  │───>│ Celery   │───>│ Sentiment│───>│PostgreSQL│───>│Dashboard │
│   API    │    │ Worker   │    │  Model   │    │   BDD    │    │Streamlit │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
     │                                               │               │
     │                                               │               │
     │         ┌──────────┐    ┌──────────┐         │               │
     │         │  Alerte  │<───│  Check   │<────────┘               │
     │         │  Email   │    │  Worker  │                         │
     │         └──────────┘    └──────────┘                         │
     │                                                              │
     │         ┌──────────┐    ┌──────────┐    ┌──────────┐        │
     └────────>│   LLM    │<───│   RAG    │<───│   Chat   │<───────┘
               │   +MCP   │    │ Context  │    │Interface │
               └──────────┘    └──────────┘    └──────────┘
```

## 4. Stack technologique

| Couche | Technologie | Justification |
|--------|-------------|---------------|
| Frontend | Streamlit | Python natif, rapide à dev, widgets data |
| Backend | FastAPI | Async, rapide, documentation auto |
| BDD | PostgreSQL | Robuste, requêtes temporelles, gratuit |
| Cache/Queue | Redis | Broker Celery, cache rapide |
| ML Sentiment | CamemBERT + PyTorch | Français, fine-tuning facile |
| LLM | Transformer PyTorch | From scratch (exigence sujet) |
| DRL | Stable-Baselines3 | Référence, bien documenté |
| MCP | FastMCP | Standard, Python natif |
| Conteneurs | Docker | Portabilité, reproductibilité |
| CI/CD | GitHub Actions | Gratuit, intégré |
| Cloud | AWS (EC2, RDS, S3) | Free tier, standard industrie |

## 5. Sécurité

- Authentification JWT (tokens signés)
- HTTPS obligatoire
- Variables d'environnement pour secrets
- Rate limiting sur les endpoints
- Validation des entrées (Pydantic)
