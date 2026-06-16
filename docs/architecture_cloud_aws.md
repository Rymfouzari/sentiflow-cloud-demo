# SentiFlow - Architecture Cloud AWS

## 1. Vue d'ensemble Infrastructure

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              AWS CLOUD                                       │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                           VPC (Virtual Private Cloud)                │   │
│  │                                                                      │   │
│  │   ┌─────────────┐                                                   │   │
│  │   │    ALB      │◄──────── Internet (HTTPS)                        │   │
│  │   │(Load Bal.)  │                                                   │   │
│  │   └──────┬──────┘                                                   │   │
│  │          │                                                          │   │
│  │          ▼                                                          │   │
│  │   ┌─────────────────────────────────────────┐                      │   │
│  │   │              EC2 (t2.micro)              │                      │   │
│  │   │                                          │                      │   │
│  │   │  ┌─────────┐  ┌─────────┐  ┌─────────┐ │                      │   │
│  │   │  │ Docker  │  │ Docker  │  │ Docker  │ │                      │   │
│  │   │  │FastAPI  │  │Streamlit│  │ Celery  │ │                      │   │
│  │   │  └─────────┘  └─────────┘  └─────────┘ │                      │   │
│  │   │                                          │                      │   │
│  │   └─────────────────────────────────────────┘                      │   │
│  │          │                   │                                      │   │
│  │          ▼                   ▼                                      │   │
│  │   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐           │   │
│  │   │     RDS     │    │ElastiCache  │    │     S3      │           │   │
│  │   │ PostgreSQL  │    │   Redis     │    │  (Storage)  │           │   │
│  │   │ (db.t2.micro)│   │(optionnel)  │    │             │           │   │
│  │   └─────────────┘    └─────────────┘    └─────────────┘           │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                    │
│  │ CloudWatch  │    │     SES     │    │   Lambda    │                    │
│  │   (Logs)    │    │  (Emails)   │    │ (Alertes)   │                    │
│  └─────────────┘    └─────────────┘    └─────────────┘                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 2. Services AWS utilisés

| Service | Usage | Free Tier |
|---------|-------|-----------|
| EC2 t2.micro | Serveur principal (Docker) | ✅ 750h/mois |
| RDS PostgreSQL | Base de données | ✅ 750h/mois |
| S3 | Stockage fichiers (PDF, modèles) | ✅ 5 Go |
| CloudWatch | Logs et monitoring | ✅ Basique gratuit |
| SES | Envoi emails alertes | ✅ 62k emails/mois |
| Lambda | Fonctions serverless alertes | ✅ 1M requêtes/mois |
| ElastiCache | Redis (optionnel) | ❌ Payant |
| ALB | Load balancer | ❌ Payant (~15€/mois) |

### Option 100% Free Tier :
- EC2 avec Nginx comme reverse proxy (pas d'ALB)
- Redis en container Docker sur EC2 (pas d'ElastiCache)

## 3. Pipeline CI/CD

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CI/CD PIPELINE                                     │
│                                                                             │
│   DÉVELOPPEUR                                                               │
│       │                                                                     │
│       │ git push                                                            │
│       ▼                                                                     │
│   ┌─────────┐                                                               │
│   │ GitHub  │                                                               │
│   │  Repo   │                                                               │
│   └────┬────┘                                                               │
│        │ trigger                                                            │
│        ▼                                                                    │
│   ┌─────────────────────────────────────────────────────────┐              │
│   │              GITHUB ACTIONS                              │              │
│   │                                                          │              │
│   │  1. Checkout code                                        │              │
│   │  2. Run tests (pytest)                                   │              │
│   │  3. Build Docker images                                  │              │
│   │  4. Push to ECR (ou Docker Hub)                         │              │
│   │  5. Deploy to EC2 (SSH + docker-compose pull)           │              │
│   │                                                          │              │
│   └─────────────────────────────────────────────────────────┘              │
│        │                                                                    │
│        ▼                                                                    │
│   ┌─────────┐         ┌─────────┐         ┌─────────┐                     │
│   │   ECR   │────────>│   EC2   │────────>│  LIVE   │                     │
│   │ (Images)│  pull   │ (Docker)│  run    │  APP    │                     │
│   └─────────┘         └─────────┘         └─────────┘                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 4. Fichier docker-compose.yml

```yaml
version: '3.8'

services:
  # Backend API
  api:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/sentiflow
      - REDIS_URL=redis://redis:6379
      - TWITTER_API_KEY=${TWITTER_API_KEY}
      - JWT_SECRET=${JWT_SECRET}
    depends_on:
      - db
      - redis

  # Frontend Streamlit
  frontend:
    build: ./frontend
    ports:
      - "8501:8501"
    environment:
      - API_URL=http://api:8000
    depends_on:
      - api

  # Worker Celery
  worker:
    build: ./backend
    command: celery -A app.celery worker --loglevel=info
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/sentiflow
      - REDIS_URL=redis://redis:6379
    depends_on:
      - db
      - redis

  # Celery Beat (tâches planifiées)
  beat:
    build: ./backend
    command: celery -A app.celery beat --loglevel=info
    depends_on:
      - worker

  # Base de données (dev local uniquement)
  db:
    image: postgres:15
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
      - POSTGRES_DB=sentiflow
    volumes:
      - postgres_data:/var/lib/postgresql/data

  # Redis
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  postgres_data:
```

## 5. Coûts estimés

### Option Free Tier (recommandé pour projet étudiant) :
| Service | Coût mensuel |
|---------|--------------|
| EC2 t2.micro | 0€ |
| RDS db.t2.micro | 0€ |
| S3 (< 5Go) | 0€ |
| SES | 0€ |
| Lambda | 0€ |
| **TOTAL** | **0€** |

### Option Production légère :
| Service | Coût mensuel |
|---------|--------------|
| EC2 t3.small | ~15€ |
| RDS db.t3.micro | ~15€ |
| ElastiCache | ~15€ |
| ALB | ~15€ |
| S3 + transfert | ~5€ |
| **TOTAL** | **~65€** |

## 6. Sécurité AWS

- Security Groups : ports 80, 443, 22 uniquement
- IAM roles pour accès services
- Secrets Manager pour clés API
- RDS dans subnet privé
- HTTPS via certificat ACM (gratuit)
