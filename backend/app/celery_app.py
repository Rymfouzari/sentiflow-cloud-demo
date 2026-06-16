from celery import Celery
from celery.schedules import crontab
from backend.app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "sentiflow",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["backend.app.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# Planification des tâches périodiques (Celery Beat)
celery_app.conf.beat_schedule = {
    # Collecte auto toutes les 15 minutes (20 tweets les plus récents par cible, sans doublons)
    "collect-all-targets": {
        "task": "backend.app.tasks.collect_all_targets",
        "schedule": 900.0,  # 15 minutes
    },
    # Analyse auto toutes les 20 minutes (juste après la collecte)
    "analyze-all-targets": {
        "task": "backend.app.tasks.analyze_all_targets",
        "schedule": 1200.0,  # 20 minutes
    },
    # Vérifier les alertes toutes les 30 minutes
    "check-alerts": {
        "task": "backend.app.tasks.check_all_alerts",
        "schedule": 1800.0,  # 30 minutes
    },
    # Agréger les sentiments toutes les 6h
    "aggregate-sentiments": {
        "task": "backend.app.tasks.aggregate_sentiments",
        "schedule": 21600.0,  # 6h
    },
    # Feedback loop : export des corrections et hook de réentraînement chaque semaine.
    "weekly-feedback-retraining": {
        "task": "backend.app.tasks.retrain_sentiment_from_feedback",
        "schedule": crontab(day_of_week="sun", hour=3, minute=0),
    },
    # Pipeline TinyGPT : ré-entraînement tous les 2 jours à 4h du matin
    "tinygpt-retrain": {
        "task": "backend.app.tasks.retrain_tinygpt_pipeline",
        "schedule": crontab(hour=4, minute=0, day_of_week="*/2"),
    },
}
