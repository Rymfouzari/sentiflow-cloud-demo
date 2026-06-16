# SentiFlow - Technologies Utilisées

## 1. Vue d'ensemble de la stack

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           STACK TECHNIQUE                                    │
│                                                                             │
│   FRONTEND          BACKEND           ML/AI            INFRA               │
│   ─────────         ───────           ─────            ─────               │
│   Streamlit         FastAPI           PyTorch          Docker              │
│   Plotly            PostgreSQL        CamemBERT        AWS EC2             │
│   Altair            Redis             Transformer      AWS RDS             │
│                     Celery            Stable-Baselines AWS S3              │
│                     JWT               FastMCP          GitHub Actions      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 2. Détail par catégorie

### FRONTEND

| Technologie | Version | Rôle | Justification | Alternatives écartées |
|-------------|---------|------|---------------|----------------------|
| **Streamlit** | 1.31+ | Interface utilisateur | Python natif, rapide à développer, widgets data intégrés | React (trop complexe), Dash (moins flexible) |
| **Plotly** | 5.18+ | Graphiques interactifs | Interactif, beau, intégré Streamlit | Matplotlib (statique), Bokeh (moins intuitif) |
| **Altair** | 5.2+ | Graphiques déclaratifs | Syntaxe simple, bon pour séries temporelles | Chart.js (JavaScript) |

### BACKEND

| Technologie | Version | Rôle | Justification | Alternatives écartées |
|-------------|---------|------|---------------|----------------------|
| **FastAPI** | 0.109+ | API REST | Async natif, rapide, documentation auto (Swagger), validation Pydantic | Flask (pas async), Django (trop lourd) |
| **PostgreSQL** | 15+ | Base de données | Robuste, requêtes temporelles, JSON support, gratuit | MongoDB (moins adapté relations), MySQL (moins features) |
| **Redis** | 7+ | Cache + Message broker | Ultra rapide, broker Celery, cache sessions | RabbitMQ (plus complexe), Memcached (moins features) |
| **Celery** | 5.3+ | Tâches asynchrones | Standard Python, planification, workers | APScheduler (moins robuste), RQ (moins features) |
| **SQLAlchemy** | 2.0+ | ORM | Standard Python, migrations Alembic | Django ORM (couplé Django), Peewee (moins complet) |
| **Pydantic** | 2.5+ | Validation données | Intégré FastAPI, typage fort | Marshmallow (moins intégré) |
| **JWT (PyJWT)** | 2.8+ | Authentification | Standard, stateless, sécurisé | Sessions (stateful), OAuth (overkill) |

### MACHINE LEARNING

| Technologie | Version | Rôle | Justification | Alternatives écartées |
|-------------|---------|------|---------------|----------------------|
| **PyTorch** | 2.1+ | Framework ML | Flexible, dynamique, communauté active, from scratch possible | TensorFlow (plus rigide), JAX (moins mature) |
| **CamemBERT** | - | Modèle sentiment | Pré-entraîné français, fine-tuning facile | BERT multilingue (moins bon français), FlauBERT (moins populaire) |
| **Transformers (HuggingFace)** | 4.36+ | Librairie NLP | Accès modèles pré-entraînés, tokenizers | Spacy (moins deep learning) |
| **Stable-Baselines3** | 2.2+ | Deep RL | Référence, bien documenté, PyTorch natif | RLlib (trop complexe), custom (trop long) |

### LLM FROM SCRATCH

| Composant | Implémentation | Description |
|-----------|----------------|-------------|
| **Tokenizer** | Custom BPE | Byte Pair Encoding adapté au domaine Twitter/sentiments |
| **Embeddings** | PyTorch nn.Embedding | Représentation vectorielle des tokens |
| **Positional Encoding** | Sinusoidal | Encodage position dans la séquence |
| **Multi-Head Attention** | Custom PyTorch | Mécanisme d'attention (cœur du Transformer) |
| **Feed-Forward** | PyTorch nn.Linear | Couches denses |
| **Layer Norm** | PyTorch nn.LayerNorm | Normalisation |

### MCP (Model Context Protocol)

| Technologie | Version | Rôle | Justification |
|-------------|---------|------|---------------|
| **FastMCP** | 0.4+ | Serveur MCP | Python natif, simple, standard ouvert |

**Outils MCP exposés :**
```python
@mcp.tool()
def search_tweets(query: str, limit: int) -> list
    """Recherche des tweets"""

@mcp.tool()
def get_sentiment_analysis(target_id: int, period: str) -> dict
    """Récupère l'analyse de sentiment"""

@mcp.tool()
def generate_dashboard(data: dict) -> str
    """Génère un dashboard"""

@mcp.tool()
def create_alert(target_id: int, sentiment: str, threshold: float) -> dict
    """Crée une alerte"""

@mcp.tool()
def post_tweet(content: str) -> dict
    """Publie sur Twitter"""
```

### INFRASTRUCTURE

| Technologie | Version | Rôle | Justification | Alternatives écartées |
|-------------|---------|------|---------------|----------------------|
| **Docker** | 24+ | Conteneurisation | Portabilité, reproductibilité, déploiement simple | VM directe (pas portable), Podman (moins répandu) |
| **Docker Compose** | 2.23+ | Orchestration locale | Multi-conteneurs, dev simple | Kubernetes (overkill pour ce projet) |
| **GitHub Actions** | - | CI/CD | Gratuit, intégré GitHub, simple | Jenkins (à héberger), GitLab CI (migration repo) |

### CLOUD AWS

| Service | Tier | Rôle | Coût |
|---------|------|------|------|
| **EC2 t2.micro** | Free | Serveur principal | 0€ (750h/mois) |
| **RDS PostgreSQL db.t2.micro** | Free | Base de données | 0€ (750h/mois) |
| **S3** | Free | Stockage fichiers | 0€ (5 Go) |
| **SES** | Free | Emails alertes | 0€ (62k/mois) |
| **Lambda** | Free | Fonctions serverless | 0€ (1M req/mois) |
| **CloudWatch** | Free | Logs/monitoring | 0€ (basique) |
| **ECR** | Free | Registry Docker | 0€ (500 Mo) |

### API EXTERNES

| API | Usage | Coût |
|-----|-------|------|
| **Twitter API v2** | Extraction tweets | Free tier: 500k tweets/mois |

## 3. Versions et compatibilité

```
Python >= 3.10
├── fastapi >= 0.109.0
├── streamlit >= 1.31.0
├── sqlalchemy >= 2.0.0
├── celery >= 5.3.0
├── redis >= 5.0.0
├── torch >= 2.1.0
├── transformers >= 4.36.0
├── stable-baselines3 >= 2.2.0
├── fastmcp >= 0.4.0
├── plotly >= 5.18.0
├── altair >= 5.2.0
├── pydantic >= 2.5.0
├── pyjwt >= 2.8.0
├── httpx >= 0.26.0
├── alembic >= 1.13.0
└── pytest >= 7.4.0
```

## 4. Pourquoi cette stack ?

### Cohérence Python
Tout est en Python : frontend, backend, ML. Pas de changement de contexte, une seule équipe peut tout maintenir.

### Écosystème ML
Python est le standard pour le ML. PyTorch, HuggingFace, tout est disponible et bien documenté.

### Rapidité de développement
Streamlit + FastAPI = prototype fonctionnel en quelques jours. Idéal pour un projet avec deadline serrée.

### Scalabilité
Celery + Redis permettent de scaler les workers. PostgreSQL gère des millions de tweets. AWS permet de grandir si besoin.

### Coût
100% free tier possible pour le développement et la démo. Pas de surprise de facturation.

## 5. Schéma des dépendances

```
                    ┌─────────────┐
                    │   Python    │
                    │   3.10+     │
                    └──────┬──────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
         ▼                 ▼                 ▼
   ┌───────────┐    ┌───────────┐    ┌───────────┐
   │  FastAPI  │    │ Streamlit │    │  PyTorch  │
   └─────┬─────┘    └─────┬─────┘    └─────┬─────┘
         │                │                │
         ▼                ▼                ▼
   ┌───────────┐    ┌───────────┐    ┌───────────┐
   │SQLAlchemy │    │  Plotly   │    │Transformers│
   │ Pydantic  │    │  Altair   │    │   FastMCP │
   │  Celery   │    └───────────┘    │    SB3    │
   └─────┬─────┘                     └───────────┘
         │
         ▼
   ┌───────────┐
   │PostgreSQL │
   │   Redis   │
   └───────────┘
```
