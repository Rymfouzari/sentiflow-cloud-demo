# SentiFlow - Pipeline de Données

## 1. Vue d'ensemble du flux

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        PIPELINE DE DONNÉES SENTIFLOW                         │
│                                                                             │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐  │
│  │TWITTER  │───>│COLLECTE │───>│ANALYSE  │───>│STOCKAGE │───>│DASHBOARD│  │
│  │  API    │    │ Celery  │    │Sentiment│    │PostgreSQL│   │Streamlit│  │
│  └─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘  │
│                      │              │              │              │         │
│                      │              │              │              │         │
│                      ▼              ▼              ▼              ▼         │
│                 ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐     │
│                 │  Redis  │   │ PyTorch │   │  Cache  │   │ Plotly  │     │
│                 │  Queue  │   │  Model  │   │  Redis  │   │ Charts  │     │
│                 └─────────┘   └─────────┘   └─────────┘   └─────────┘     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 2. Étape 1 : Collecte des tweets

```
┌─────────────────────────────────────────────────────────────────┐
│                    COLLECTE (Celery Beat)                        │
│                                                                  │
│  Fréquence : toutes les 15 minutes                              │
│                                                                  │
│  Pour chaque compte/hashtag suivi :                             │
│  │                                                               │
│  ├─> Appel API Twitter                                          │
│  │   GET /2/tweets/search/recent?query=#hashtag                 │
│  │   Paramètres : since_id (dernier tweet connu)                │
│  │                                                               │
│  ├─> Réponse Twitter                                            │
│  │   {                                                           │
│  │     "data": [                                                 │
│  │       {"id": "123", "text": "...", "created_at": "..."},     │
│  │       {"id": "124", "text": "...", "created_at": "..."}      │
│  │     ]                                                         │
│  │   }                                                           │
│  │                                                               │
│  └─> Envoi vers queue Redis pour analyse                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Code simplifié :
```python
@celery.task
def collect_tweets():
    # Récupérer tous les comptes/hashtags suivis
    targets = db.query(TrackedTarget).all()
    
    for target in targets:
        # Appel API Twitter
        tweets = twitter_api.search(
            query=target.query,
            since_id=target.last_tweet_id
        )
        
        # Envoyer chaque tweet pour analyse
        for tweet in tweets:
            analyze_tweet.delay(tweet, target.id)
        
        # Mettre à jour le dernier ID
        target.last_tweet_id = tweets[0].id
        db.commit()
```

## 3. Étape 2 : Analyse de sentiment

```
┌─────────────────────────────────────────────────────────────────┐
│                    ANALYSE (Celery Worker)                       │
│                                                                  │
│  Pour chaque tweet reçu :                                       │
│  │                                                               │
│  ├─> Prétraitement                                              │
│  │   - Nettoyage (URLs, mentions, emojis)                       │
│  │   - Tokenization                                             │
│  │                                                               │
│  ├─> Modèle de sentiment (CamemBERT fine-tuné)                 │
│  │   Input : "Ce produit est génial !"                         │
│  │   Output : {                                                  │
│  │     "joie": 0.85,                                            │
│  │     "colère": 0.02,                                          │
│  │     "tristesse": 0.01,                                       │
│  │     "peur": 0.01,                                            │
│  │     "surprise": 0.08,                                        │
│  │     "neutre": 0.03                                           │
│  │   }                                                           │
│  │                                                               │
│  └─> Stockage en BDD                                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Code simplifié :
```python
@celery.task
def analyze_tweet(tweet_data, target_id):
    # Prétraitement
    clean_text = preprocess(tweet_data['text'])
    
    # Analyse sentiment
    sentiment_scores = sentiment_model.predict(clean_text)
    dominant_sentiment = max(sentiment_scores, key=sentiment_scores.get)
    
    # Stockage
    tweet = Tweet(
        twitter_id=tweet_data['id'],
        text=tweet_data['text'],
        created_at=tweet_data['created_at'],
        target_id=target_id,
        sentiment=dominant_sentiment,
        sentiment_scores=sentiment_scores,
        confidence=sentiment_scores[dominant_sentiment]
    )
    db.add(tweet)
    db.commit()
    
    # Vérifier les alertes
    check_alerts.delay(target_id)
```

## 4. Étape 3 : Vérification des alertes

```
┌─────────────────────────────────────────────────────────────────┐
│                    ALERTES (Celery Worker)                       │
│                                                                  │
│  Pour chaque alerte active de l'utilisateur :                   │
│  │                                                               │
│  ├─> Calculer le sentiment actuel                               │
│  │   SELECT sentiment, COUNT(*) FROM tweets                     │
│  │   WHERE target_id = X AND created_at > NOW() - INTERVAL '1h' │
│  │   GROUP BY sentiment                                          │
│  │                                                               │
│  ├─> Comparer avec le seuil de l'alerte                        │
│  │   Alerte : "Si colère > 60%"                                 │
│  │   Actuel : colère = 65%                                      │
│  │   → DÉCLENCHER                                                │
│  │                                                               │
│  └─> Envoyer notification                                       │
│      - Email (AWS SES)                                          │
│      - Push notification                                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## 5. Étape 4 : Affichage Dashboard

```
┌─────────────────────────────────────────────────────────────────┐
│                    DASHBOARD (Streamlit)                         │
│                                                                  │
│  Requêtes API :                                                 │
│  │                                                               │
│  ├─> GET /analysis/{target_id}?period=7d                       │
│  │   Retourne : distribution des sentiments sur 7 jours         │
│  │                                                               │
│  ├─> GET /analysis/{target_id}/timeline?period=30d             │
│  │   Retourne : évolution temporelle des sentiments             │
│  │                                                               │
│  ├─> GET /compare?targets=1,2,3                                │
│  │   Retourne : comparaison entre plusieurs cibles              │
│  │                                                               │
│  └─> Affichage avec Plotly/Altair                              │
│      - Pie chart (répartition)                                  │
│      - Line chart (évolution)                                   │
│      - Bar chart (comparaison)                                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## 6. Pipeline LLM + RAG + MCP

```
┌─────────────────────────────────────────────────────────────────┐
│                    PIPELINE LLM                                  │
│                                                                  │
│  Utilisateur : "Résume l'humeur de #IA cette semaine"          │
│  │                                                               │
│  ├─> 1. PARSING (comprendre la question)                        │
│  │   - Entité : #IA                                             │
│  │   - Action : résumer                                         │
│  │   - Période : cette semaine                                  │
│  │                                                               │
│  ├─> 2. RAG (récupérer le contexte)                            │
│  │   - Query BDD : tweets de #IA des 7 derniers jours          │
│  │   - Agrégation : 60% positif, 25% neutre, 15% négatif       │
│  │   - Top tweets représentatifs                                │
│  │                                                               │
│  ├─> 3. LLM (générer la réponse)                               │
│  │   Prompt : "Contexte: {données RAG}. Question: {user}"      │
│  │   Réponse : "Cette semaine, #IA est globalement positif..." │
│  │                                                               │
│  └─> 4. MCP (actions optionnelles)                             │
│      Si l'utilisateur demande un dashboard :                    │
│      - LLM appelle generate_dashboard(data)                     │
│      - Retourne le graphique généré                             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## 7. Schéma récapitulatif complet

```
                                    SENTIFLOW - FLUX COMPLET
                                    
     ┌──────────────────────────────────────────────────────────────────────┐
     │                                                                      │
     │   SOURCES                TRAITEMENT                 SORTIES          │
     │                                                                      │
     │   ┌────────┐            ┌──────────┐              ┌──────────┐      │
     │   │Twitter │──collect──>│  Redis   │──worker──>   │PostgreSQL│      │
     │   │  API   │            │  Queue   │              │   BDD    │      │
     │   └────────┘            └──────────┘              └────┬─────┘      │
     │                              │                         │            │
     │                              │                         │            │
     │                              ▼                         ▼            │
     │                         ┌──────────┐              ┌──────────┐      │
     │                         │Sentiment │              │Dashboard │      │
     │                         │  Model   │              │Streamlit │      │
     │                         └──────────┘              └──────────┘      │
     │                                                        │            │
     │                                                        │            │
     │   ┌────────┐            ┌──────────┐              ┌───▼──────┐      │
     │   │  User  │──question─>│ LLM+RAG  │──response──> │   Chat   │      │
     │   │  Chat  │            │   +MCP   │              │Interface │      │
     │   └────────┘            └────┬─────┘              └──────────┘      │
     │                              │                                      │
     │                              │ MCP tools                            │
     │                              ▼                                      │
     │                         ┌──────────┐              ┌──────────┐      │
     │                         │ Actions  │──publish──>  │ Twitter  │      │
     │                         │(generate,│              │   Post   │      │
     │                         │ alert...)│              └──────────┘      │
     │                         └──────────┘                                │
     │                                                                      │
     └──────────────────────────────────────────────────────────────────────┘
```
