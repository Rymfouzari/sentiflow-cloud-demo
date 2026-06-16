# Changelog — Branch `fix-david-front-color`

## Contexte

Après le `git pull` de la branche lseillier (LLM from scratch + RAG), plusieurs problèmes ont été rencontrés :
- L'authentification ne fonctionnait plus (erreur 401 en boucle)
- Le frontend nginx avait des conflits avec l'API sur les ports
- Les dashboards ne se créaient pas
- La collecte Celery était désactivée
- Pas de page admin pour contrôler la pipeline

Ce document résume toutes les modifications apportées pour corriger et améliorer le projet.

---

## 1. Fix Docker : suppression du container frontend nginx

**Problème** : on avait deux façons de servir le frontend (nginx sur port 5173 + FastAPI qui servait aussi le build React sur port 8000). Les deux se battaient, le nginx servait l'ancien code.

**Solution** : le Dockerfile backend (`backend/Dockerfile`) build le React en multi-stage et FastAPI sert directement les fichiers statiques. Plus besoin du container `frontend` nginx.

**Comment lancer** :
```bash
docker compose up -d db redis zookeeper kafka mlflow api celery-worker celery-beat kafka-consumer
```
(Ne pas lancer le service `frontend`)

**URL unique** : `http://localhost:8000`

---

## 2. Fix authentification

**Problème** : 
- Le Login.js appelait `login()` (la fonction API) au lieu de `loginUser()` (la fonction du contexte React)
- Le champ retourné par l'API est `access_token`, pas `token`
- L'interceptor axios 401 redirigeait même sur la page `/auth/login`, ce qui créait une boucle

**Fichiers modifiés** :
- `frontend/src/pages/Login.js` — appelle `loginUser(res.data.access_token, res.data.user)`
- `frontend/src/services/api.js` — l'interceptor 401 exclut les routes `/auth/`

---

## 3. Fix user_id dans l'Assistant

**Problème** : la route `/assistant/chat` avait `user_id = 1` en dur. Quand un user se connectait, ses cibles et dashboards étaient créés sous le user 1 (admin), pas sous son propre compte.

**Solution** : extraction du user_id depuis le token JWT dans le header Authorization.

**Fichier** : `backend/app/routes/assistant.py`

---

## 4. Frontend redesign complet

**Couleur principale** : `#5271ff` (bleu)

**Pages refaites** :
- `Home.js` — page d'accueil avec carrousel (4 slides auto), grille features, schéma pipeline
- `About.js` — page "A propos" avec explication du pipeline étape par étape, stack technique, équipe
- `Login.js` — formulaire login/register corrigé
- `Assistant.js` — chat avec mode visible (AGENT/RAG/BDD), export PDF, feedback loop, sources
- `Dashboard.js` — graphiques recharts avec nouvelle palette
- `Cibles.js` — liste avec boutons collecter/analyser/supprimer
- `Alertes.js` — formulaire + liste
- `Admin.js` — panel admin complet (voir section 7)
- `GeneratedDashboards.js` — liste dashboards IA

**Layout** : sidebar fixe avec logo, avatar user, timer de collecte

**Design** : fond `#09090b`, cartes `#0f0f12`, bordures `#1c1c22`, pas d'emoji, typo Inter

---

## 5. Collecte automatique Celery (toutes les 15 min)

**Problème** : la collecte était désactivée dans le beat schedule.

**Solution** : activée dans `backend/app/celery_app.py`

**Schedule actuel** :
| Tâche | Intervalle |
|-------|-----------|
| Collecte tweets | 15 min |
| Analyse sentiments | 20 min |
| Vérification alertes | 30 min |
| Agrégation | 6h |
| Feedback/retraining sentiment | Dimanche 3h |
| Pipeline TinyGPT | Tous les 2 jours 4h |

La tâche `collect_all_targets` vérifie un flag Redis `sentiflow:collect_paused` — si l'admin l'a stoppée, elle skip.

**Timer sidebar** : un countdown en bas à gauche de la sidebar montre quand la prochaine collecte aura lieu. Disparaît si l'admin pause la collecte.

---

## 6. Pipeline auto-entraînement TinyGPT

**Nouveau fichier** : `scripts/auto_retrain_pipeline.py`

**Fonctionnement** (tous les 2 jours) :
1. Exporte les questions des users + feedbacks LLM depuis la BDD
2. Fusionne avec 6000 exemples synthétiques (données BDD x3 car plus représentatives)
3. Entraîne un nouveau checkpoint TinyGPT
4. Évalue l'ancien ET le nouveau sur 15 questions de test
5. Remplace le `.pt` UNIQUEMENT si le nouveau score est meilleur

**Métriques d'évaluation** : % JSON valides, % intents corrects, % cibles correctes

---

## 7. Panel Admin

**Route** : `/admin` (nécessite `is_admin = True`)

**Contrôles disponibles** :
- Vue d'ensemble BDD (tweets, analyses, cibles, users)
- Collecte : lancer maintenant, stopper, réactiver avec intervalle modifiable (5/10/15/30/60/120 min)
- Analyse : lancer maintenant
- Pipeline TinyGPT : lancer entraînement, exporter données BDD, voir résultats
- Utilisateurs : lister, promouvoir/rétrograder admin

---

## 8. Optimisation vitesse RAG

**Fichier** : `backend/app/services/rag.py`

**Ajout** : cache LRU (128 entrées, TTL 5 minutes) pour les résultats de recherche. Les requêtes similaires ne recalculent plus TF-IDF + BM25 + reranking. Invalidation automatique quand l'index est reconstruit.

---

## 9. Dashboard auto en mode RAG

**Problème** : seul le mode Agent créait un dashboard. En mode RAG, rien n'était sauvegardé.

**Solution** : le mode RAG sauvegarde aussi un dashboard quand il y a au moins 2 sources dans la réponse.

---

## 10. Feedback loop dans l'Assistant

**Bouton "Pas satisfait"** dans chaque réponse du chat :
- L'user dit ce qui ne va pas
- Le système régénère via Groq (mode `groq_only`) ou refait tout (mode `full_pipeline`)
- La réponse régénérée s'affiche dans le chat

---

## Comment déployer

```bash
# 1. Pull la branche
git checkout fix-david-front-color
git pull origin fix-david-front-color

# 2. Copier le .env
cp .env.example .env
# Remplir TWITTER_API_KEY, GROQ_API_KEY, JWT_SECRET

# 3. Build et lancer (sans le container frontend nginx)
docker compose build --no-cache api celery-worker celery-beat
docker compose up -d db redis zookeeper kafka mlflow api celery-worker celery-beat kafka-consumer

# 4. Accéder
# Frontend + API : http://localhost:8000
# MLflow : http://localhost:5000
# API docs : http://localhost:8000/docs
```

## Comptes de test

Tous les comptes ont le mot de passe `azerty` :
- `david@david.fr` (admin)
- `admin@test.fr` (admin)
- `louis@louis.fr` (admin)

Pour créer un nouveau compte : page login → "S'inscrire"
