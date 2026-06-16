# 📊 SentiFlow - Analyse de Sentiments Twitter

Plateforme d'analyse de sentiments Twitter en temps réel avec ML, Kafka et React.

## Architecture

| Service | Technologie | Port |
|---------|------------|------|
| Frontend | React + Nginx | 3000 |
| API | FastAPI | 8000 |
| Base de données | PostgreSQL | 5432 |
| Cache/Queue | Redis | 6379 |
| Streaming | Kafka | 9092 |
| Planificateur | Celery Beat | - |
| Worker | Celery Worker | - |
| Consumer | Kafka Consumer | - |
| Zookeeper | Zookeeper | 2181 |

## Prérequis

- [Docker](https://docs.docker.com/get-docker/) et Docker Compose
- Git

C'est tout. Docker installe automatiquement toutes les dépendances (Python, Node.js, etc.).

## Installation

```bash
# 1. Cloner le repo
git clone https://github.com/votre-repo/sentiflow.git
cd sentiflow

# 2. Configurer les variables d'environnement
cp .env.example .env
# Éditer .env et remplir :
# - TWITTER_API_KEY : clé API twitterapi.io
# - JWT_SECRET : générer avec python3 -c "import secrets; print(secrets.token_hex(32))"
```

## Lancement

```bash
# Lancer tous les services (premier lancement ~10-15 min)
docker compose up -d --build

# Vérifier que tout tourne
docker compose ps
```

Ouvrir dans le navigateur :
- Frontend : http://localhost:3000
- API docs : http://localhost:8000/docs

## Développement local (frontend)

Pour le développement du frontend React sans Docker :

```bash
cd frontend
npm install
REACT_APP_API_URL=http://localhost:8000 npm start
```

Le frontend sera sur http://localhost:3000 avec hot-reload.

## Commandes utiles

```bash
# Voir les logs d'un service
docker compose logs api --tail 20
docker compose logs celery-worker --tail 20
docker compose logs kafka-consumer --tail 20

# Suivre les logs en temps réel (collecte + analyse + Kafka)
docker compose logs -f api kafka-consumer celery-worker --tail 5

# Redémarrer un service
docker compose restart api

# Accéder à la base de données
docker compose exec db psql -U sentiflow -d sentiflow

# Arrêter tout
docker compose down

# Tout reconstruire
docker compose up -d --build
```

## Vérifier les logs du pipeline

Les logs utilisent des emojis pour repérer vite ce qui se passe :
- ✅ succès, ❌ erreur, ⚠ warning
- 📥 collecte, 🤖 analyse IA, 📤 envoi Kafka, 🔔 alertes, 📊 agrégation

```bash
# Logs de collecte Twitter (Celery Worker)
docker compose logs celery-worker --tail 30 | grep COLLECTE

# Logs d'analyse IA (Kafka Consumer temps réel)
docker compose logs kafka-consumer --tail 30

# Logs d'agrégation et alertes
docker compose logs celery-worker --tail 30 | grep -E "AGREG|ALERTES"

# Vérifier quelle clé API Twitter est utilisée
docker compose logs api --tail 10 | grep TWITTER
docker compose exec api env | grep TWITTER
```

## Commandes base de données

```bash
# Voir le nombre total de tweets et combien sont analysés
docker compose exec db psql -U sentiflow -d sentiflow -c "SELECT COUNT(*) as total, COUNT(CASE WHEN sentiment IS NOT NULL THEN 1 END) as analyses FROM tweets;"

# Voir les derniers tweets avec leur sentiment
docker compose exec db psql -U sentiflow -d sentiflow -c "SELECT author_username, sentiment, ROUND(confidence::numeric,2) as conf, LEFT(text,80) as tweet FROM tweets ORDER BY id DESC LIMIT 10;"

# Voir les tweets par cible et par utilisateur
docker compose exec db psql -U sentiflow -d sentiflow -c "SELECT u.username, t.name, COUNT(tw.id) as tweets FROM targets t LEFT JOIN tweets tw ON tw.target_id = t.id JOIN users u ON u.id = t.user_id GROUP BY u.username, t.name ORDER BY tweets DESC;"

# Lister les utilisateurs
docker compose exec db psql -U sentiflow -d sentiflow -c "SELECT id, username, email, is_admin FROM users;"
```

## Modifier un mot de passe

```bash
# 1. Générer le hash bcrypt du nouveau mot de passe
docker compose exec api python -c "
from backend.app.services.auth import hash_password
print(hash_password('nouveau_mdp'))
"

# 2. Ouvrir psql en interactif
docker compose exec db psql -U sentiflow -d sentiflow

# 3. Coller la commande SQL (remplacer LE_HASH par le hash généré)
# UPDATE users SET hashed_password = 'LE_HASH' WHERE username = 'nom_utilisateur';
# \q pour quitter
```

## Créer un compte admin

```bash
# Créer un compte via le frontend, puis :
docker compose exec db psql -U sentiflow -d sentiflow -c "UPDATE users SET is_admin = true WHERE email = 'votre@email.fr';"
```

## Stack technique

- Backend : FastAPI, SQLAlchemy, JWT (Python/UV)
- Frontend : React, Axios, Recharts
- ML : XLM-RoBERTa fine-tuné (HuggingFace)
- Streaming : Apache Kafka
- Tâches : Celery + Redis
- BDD : PostgreSQL
- Conteneurisation : Docker Compose
