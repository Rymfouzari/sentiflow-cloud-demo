from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from backend.app.database import get_db
from backend.app.models.user import User
from backend.app.models.target import Target
from backend.app.models.tweet import Tweet
from backend.app.models.alert import Alert
from backend.app.services.auth import get_current_user

router = APIRouter(prefix="/admin", tags=["Admin"])


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Vérifie que l'utilisateur est admin"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    return current_user


@router.get("/stats")
def get_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Statistiques globales (admin only)"""
    return {
        "users": db.query(func.count(User.id)).scalar(),
        "targets": db.query(func.count(Target.id)).filter(Target.user_id == current_user.id).scalar(),
        "tweets": db.query(func.count(Tweet.id)).join(Target).filter(Target.user_id == current_user.id).scalar(),
        "alerts": db.query(func.count(Alert.id)).filter(Alert.user_id == current_user.id).scalar()
    }


@router.get("/collect-timer")
def get_collect_timer():
    """Endpoint public pour le timer de collecte (pas besoin d'être admin)."""
    import redis
    from backend.app.config import get_settings
    try:
        r = redis.from_url(get_settings().redis_url)
        paused = r.get("sentiflow:collect_paused")
        interval = r.get("sentiflow:collect_interval")
        return {
            "active": paused is None,
            "interval_minutes": int(interval) if interval else 15,
        }
    except Exception:
        return {"active": True, "interval_minutes": 15}


@router.delete("/tweets/{target_id}")
def delete_tweets_by_target(
    target_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Supprime tous les tweets d'une cible"""
    # Vérifier que la cible appartient à l'admin
    target = db.query(Target).filter(Target.id == target_id, Target.user_id == current_user.id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Cible non trouvée")
    
    deleted = db.query(Tweet).filter(Tweet.target_id == target_id).delete()
    db.commit()
    
    return {"deleted": deleted, "target": target.name}


@router.delete("/tweets/all")
def delete_all_tweets(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Supprime tous les tweets de l'utilisateur admin"""
    # Récupérer les IDs des cibles de l'admin
    target_ids = [t.id for t in db.query(Target).filter(Target.user_id == current_user.id).all()]
    
    if not target_ids:
        return {"deleted": 0}
    
    deleted = db.query(Tweet).filter(Tweet.target_id.in_(target_ids)).delete(synchronize_session=False)
    db.commit()
    
    return {"deleted": deleted}


@router.get("/users")
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Liste tous les utilisateurs avec leurs cibles et stats"""
    from sqlalchemy import func as sqlfunc

    users = db.query(User).all()
    result = []
    for u in users:
        targets = db.query(Target).filter(Target.user_id == u.id).all()
        target_list = []
        for t in targets:
            tweet_count = db.query(sqlfunc.count(Tweet.id)).filter(Tweet.target_id == t.id).scalar() or 0
            analyzed_count = db.query(sqlfunc.count(Tweet.id)).filter(
                Tweet.target_id == t.id, Tweet.sentiment.isnot(None)
            ).scalar() or 0
            target_list.append({
                "id": t.id,
                "name": t.name,
                "type": t.target_type.value if hasattr(t.target_type, 'value') else str(t.target_type),
                "tweets": tweet_count,
                "analyzed": analyzed_count,
            })

        result.append({
            "id": u.id,
            "email": u.email,
            "username": u.username,
            "is_admin": u.is_admin,
            "plan": getattr(u, "plan", "free") or "free",
            "ai_calls_today": getattr(u, "ai_calls_today", 0) or 0,
            "targets": target_list,
            "total_targets": len(target_list),
            "total_tweets": sum(t["tweets"] for t in target_list),
        })
    return result


class SetPlanRequest(BaseModel):
    plan: str = Field(..., description="free | standard | premium")


@router.patch("/users/{user_id}/plan")
def set_user_plan(
    user_id: int,
    request: SetPlanRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Change l'offre d'abonnement d'un utilisateur (admin only)."""
    from backend.app.services.plans import PLANS
    if request.plan not in PLANS:
        raise HTTPException(status_code=400, detail=f"Plan invalide. Choix: {list(PLANS.keys())}")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    user.plan = request.plan
    db.commit()
    return {"id": user.id, "username": user.username, "plan": user.plan}


@router.get("/question-logs")
def get_question_logs(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Liste les questions posées par les utilisateurs (logs)."""
    try:
        from backend.app.models.question_log import QuestionLog
    except ImportError:
        return []
    logs = (
        db.query(QuestionLog)
        .order_by(QuestionLog.id.desc())
        .limit(min(limit, 500))
        .all()
    )
    return [
        {
            "id": q.id,
            "question": q.question,
            "intent_detected": q.intent_detected,
            "mode_used": q.mode_used,
            "targets_detected": q.targets_detected,
            "response_time_ms": q.response_time_ms,
            "created_at": str(q.created_at) if q.created_at else None,
        }
        for q in logs
    ]


@router.patch("/users/{user_id}/toggle-admin")
def toggle_admin(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Promouvoir/rétrograder un utilisateur admin"""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas modifier votre propre statut")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    
    user.is_admin = not user.is_admin
    db.commit()
    
    return {"id": user.id, "username": user.username, "is_admin": user.is_admin}


# ============================================
# CONTROLE PIPELINE ENTRAINEMENT
# ============================================

class RetrainRequest(BaseModel):
    epochs: int = Field(default=4, ge=1, le=20)
    synthetic_examples: int = Field(default=6000, ge=1000, le=20000)
    lr: float = Field(default=3e-4)


@router.post("/pipeline/retrain")
def trigger_retrain(
    request: RetrainRequest,
    current_user: User = Depends(require_admin),
):
    """Lance le ré-entraînement du TinyGPT planner manuellement."""
    import subprocess
    import threading

    cmd = (
        f"python scripts/auto_retrain_pipeline.py "
        f"--epochs {request.epochs} "
        f"--synthetic-examples {request.synthetic_examples} "
        f"--lr {request.lr}"
    )

    # Lancer en background pour ne pas bloquer la requête
    def run_in_background():
        subprocess.run(cmd, shell=True, cwd="/app")

    thread = threading.Thread(target=run_in_background, daemon=True)
    thread.start()

    return {
        "message": "Pipeline de ré-entraînement lancée en arrière-plan",
        "params": {"epochs": request.epochs, "synthetic_examples": request.synthetic_examples, "lr": request.lr},
    }


@router.get("/pipeline/status")
def get_pipeline_status(
    current_user: User = Depends(require_admin),
):
    """Retourne le statut du dernier entraînement (résultats d'évaluation)."""
    from pathlib import Path
    import json

    results_path = Path("/app/data/retrain_eval_results.json")
    if not results_path.exists():
        return {"status": "no_training_yet", "last_eval": None}

    try:
        data = json.loads(results_path.read_text(encoding="utf-8"))
        return {"status": "ok", "last_eval": data}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.get("/pipeline/timer")
def get_pipeline_timer():
    """Endpoint public : prochain entraînement + dernier résultat."""
    from pathlib import Path
    from datetime import datetime, timedelta
    import json
    import redis
    from backend.app.config import get_settings

    result = {"next_train_in": None, "last_result": None}

    # Dernier résultat
    results_path = Path("/app/data/retrain_eval_results.json")
    if results_path.exists():
        try:
            data = json.loads(results_path.read_text(encoding="utf-8"))
            result["last_result"] = {
                "replaced": data.get("replaced", False),
                "new_score": data.get("new_score", 0),
                "old_score": data.get("old_score", 0),
                "evaluated_at": data.get("evaluated_at"),
            }
        except Exception:
            pass

    # Prochain entraînement : tous les 2 jours à 4h UTC
    now = datetime.utcnow()
    # Trouver le prochain créneau (jours pairs à 4h)
    today_4h = now.replace(hour=4, minute=0, second=0, microsecond=0)
    if now >= today_4h:
        # Prochain = demain ou après-demain selon parité
        next_train = today_4h + timedelta(days=1)
        while next_train.day % 2 != 0:
            next_train += timedelta(days=1)
    else:
        if now.day % 2 == 0:
            next_train = today_4h
        else:
            next_train = today_4h + timedelta(days=1)
            while next_train.day % 2 != 0:
                next_train += timedelta(days=1)

    # Vérifier si l'admin a lancé un train manuellement (override)
    try:
        r = redis.from_url(get_settings().redis_url)
        last_train = r.get("sentiflow:last_train_time")
        if last_train:
            last_dt = datetime.fromisoformat(last_train.decode())
            manual_next = last_dt + timedelta(days=2)
            if manual_next > now:
                next_train = manual_next
    except Exception:
        pass

    diff = next_train - now
    total_sec = max(0, int(diff.total_seconds()))
    hours = total_sec // 3600
    minutes = (total_sec % 3600) // 60

    if hours >= 24:
        days = hours // 24
        h = hours % 24
        result["next_train_in"] = f"{days}j {h}h"
    elif hours > 0:
        result["next_train_in"] = f"{hours}h{minutes:02d}"
    else:
        result["next_train_in"] = f"{minutes}min"

    return result


@router.get("/pipeline/model-info")
def get_model_info(
    current_user: User = Depends(require_admin),
):
    """Retourne les infos du modèle TinyGPT actuellement chargé."""
    try:
        from backend.app.services.llm_from_scratch import get_planner
        planner = get_planner()
        return planner.model_info()
    except Exception as e:
        return {"error": str(e)}


# ============================================
# CONTROLE CELERY (COLLECTE / ANALYSE)
# ============================================

class CeleryScheduleUpdate(BaseModel):
    collect_interval_minutes: Optional[int] = Field(default=None, ge=5, le=1440, description="Intervalle collecte en minutes (5-1440)")
    analyze_interval_minutes: Optional[int] = Field(default=None, ge=5, le=1440, description="Intervalle analyse en minutes (5-1440)")
    alerts_interval_minutes: Optional[int] = Field(default=None, ge=10, le=1440, description="Intervalle alertes en minutes")


@router.get("/celery/schedule")
def get_celery_schedule(
    current_user: User = Depends(require_admin),
):
    """Retourne le schedule Celery actuel."""
    import redis
    from backend.app.config import get_settings
    from backend.app.celery_app import celery_app

    r = redis.from_url(get_settings().redis_url)
    paused = r.get("sentiflow:collect_paused")
    interval = r.get("sentiflow:collect_interval")

    schedule = celery_app.conf.beat_schedule
    result = {}
    for name, config in schedule.items():
        sched = config.get("schedule")
        if hasattr(sched, "total_seconds"):
            interval_sec = sched.total_seconds()
        elif isinstance(sched, (int, float)):
            interval_sec = sched
        else:
            interval_sec = str(sched)
        result[name] = {
            "task": config.get("task"),
            "interval_seconds": interval_sec,
            "interval_minutes": round(interval_sec / 60, 1) if isinstance(interval_sec, (int, float)) else interval_sec,
        }

    result["_collect_status"] = {
        "active": paused is None,
        "interval_minutes": int(interval) if interval else 15,
    }
    return result


@router.post("/celery/schedule")
def update_celery_schedule(
    request: CeleryScheduleUpdate,
    current_user: User = Depends(require_admin),
):
    """Met à jour les intervalles du schedule Celery (appliqué au prochain restart du beat)."""
    from backend.app.celery_app import celery_app

    changes = []

    if request.collect_interval_minutes is not None:
        celery_app.conf.beat_schedule["collect-all-targets"]["schedule"] = request.collect_interval_minutes * 60.0
        changes.append(f"collect: {request.collect_interval_minutes}min")

    if request.analyze_interval_minutes is not None:
        celery_app.conf.beat_schedule["analyze-all-targets"]["schedule"] = request.analyze_interval_minutes * 60.0
        changes.append(f"analyze: {request.analyze_interval_minutes}min")

    if request.alerts_interval_minutes is not None:
        celery_app.conf.beat_schedule["check-alerts"]["schedule"] = request.alerts_interval_minutes * 60.0
        changes.append(f"alerts: {request.alerts_interval_minutes}min")

    return {
        "message": "Schedule mis à jour (effectif au prochain cycle du beat)",
        "changes": changes,
    }


@router.post("/celery/collect-now")
def trigger_collect_now(
    current_user: User = Depends(require_admin),
):
    """Force une collecte immédiate de toutes les cibles."""
    from backend.app.tasks import collect_all_targets
    result = collect_all_targets.delay()
    return {"message": "Collecte lancée", "task_id": str(result.id)}


@router.post("/celery/analyze-now")
def trigger_analyze_now(
    current_user: User = Depends(require_admin),
):
    """Force une analyse immédiate de tous les tweets non analysés."""
    from backend.app.tasks import analyze_all_targets
    result = analyze_all_targets.delay()
    return {"message": "Analyse lancée", "task_id": str(result.id)}


@router.post("/celery/stop-collect")
def stop_collect(
    current_user: User = Depends(require_admin),
):
    """Désactive la collecte automatique via Redis flag."""
    import redis
    from backend.app.config import get_settings
    r = redis.from_url(get_settings().redis_url)
    r.set("sentiflow:collect_paused", "1")
    return {"message": "Collecte automatique désactivée"}


@router.post("/celery/start-collect")
def start_collect(
    interval_minutes: int = 15,
    current_user: User = Depends(require_admin),
):
    """Réactive la collecte automatique."""
    import redis
    from backend.app.config import get_settings
    r = redis.from_url(get_settings().redis_url)
    r.delete("sentiflow:collect_paused")
    r.set("sentiflow:collect_interval", str(interval_minutes))
    return {"message": f"Collecte automatique activée toutes les {interval_minutes} minutes"}


@router.get("/celery/status")
def get_collect_status(
    current_user: User = Depends(require_admin),
):
    """Retourne l'état actuel de la collecte (active/paused, intervalle)."""
    import redis
    from backend.app.config import get_settings
    r = redis.from_url(get_settings().redis_url)
    paused = r.get("sentiflow:collect_paused")
    interval = r.get("sentiflow:collect_interval")
    return {
        "active": paused is None,
        "interval_minutes": int(interval) if interval else 15,
    }


# ============================================
# CONTROLE BDD / TRAINING DATA
# ============================================

@router.get("/training-data/stats")
def get_training_data_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Statistiques sur les données d'entraînement disponibles."""
    from backend.app.models.feedback import Feedback
    from pathlib import Path
    import json

    # Question logs
    question_count = 0
    try:
        from backend.app.models.question_log import QuestionLog
        question_count = db.query(func.count(QuestionLog.id)).scalar() or 0
    except Exception:
        pass

    # Feedbacks
    feedback_count = db.query(func.count(Feedback.id)).scalar() or 0
    corrections = db.query(func.count(Feedback.id)).filter(
        Feedback.vote == -1, Feedback.corrected_label.isnot(None)
    ).scalar() or 0

    # LLM Feedbacks
    llm_feedback_count = 0
    try:
        from backend.app.models.llm_feedback import LLMFeedback
        llm_feedback_count = db.query(func.count(LLMFeedback.id)).scalar() or 0
    except Exception:
        pass

    # Export existant
    export_path = Path("/app/data/training_data_from_db.json")
    export_exists = export_path.exists()
    export_count = 0
    if export_exists:
        try:
            data = json.loads(export_path.read_text(encoding="utf-8"))
            export_count = len(data)
        except Exception:
            pass

    # Date du dernier entraînement (depuis les résultats d'éval)
    from datetime import datetime as _dt
    last_training_at = None
    eval_path = Path("/app/data/retrain_eval_results.json")
    if eval_path.exists():
        try:
            ev = json.loads(eval_path.read_text(encoding="utf-8"))
            last_training_at = ev.get("evaluated_at")
        except Exception:
            pass

    # Nouveaux tweets analysés depuis le dernier entraînement (qui alimenteront la BDD d'entraînement)
    total_analyzed = db.query(func.count(Tweet.id)).filter(Tweet.sentiment.isnot(None)).scalar() or 0
    new_tweets_for_training = total_analyzed
    if last_training_at:
        try:
            cutoff = _dt.fromisoformat(str(last_training_at).replace("Z", ""))
            new_tweets_for_training = db.query(func.count(Tweet.id)).filter(
                Tweet.sentiment.isnot(None), Tweet.analyzed_at >= cutoff
            ).scalar() or 0
        except Exception:
            pass

    return {
        "question_logs": question_count,
        "sentiment_feedbacks": feedback_count,
        "user_corrections": corrections,
        "llm_feedbacks": llm_feedback_count,
        "total_training_examples_available": question_count + corrections + llm_feedback_count,
        "last_export": {"exists": export_exists, "examples": export_count},
        "total_analyzed_tweets": total_analyzed,
        "new_tweets_for_training": new_tweets_for_training,
        "last_training_at": last_training_at,
        "training_source_file": "scripts/auto_retrain_pipeline.py",
    }


@router.post("/training-data/export")
def export_training_data(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Force l'export des données d'entraînement depuis la BDD vers le JSON."""
    try:
        import sys
        sys.path.insert(0, "/app")
        from scripts.auto_retrain_pipeline import export_training_data_from_db
        examples = export_training_data_from_db()
        return {"message": f"{len(examples)} exemples exportés", "count": len(examples)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/db/overview")
def get_db_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Vue d'ensemble de la BDD pour l'admin."""
    from backend.app.models.tweet import VALID_SENTIMENTS
    import redis
    from backend.app.config import get_settings

    total_tweets = db.query(func.count(Tweet.id)).scalar() or 0
    analyzed_tweets = db.query(func.count(Tweet.id)).filter(Tweet.sentiment.isnot(None)).scalar() or 0
    pending_tweets = total_tweets - analyzed_tweets
    total_targets = db.query(func.count(Target.id)).scalar() or 0
    total_users = db.query(func.count(User.id)).scalar() or 0
    total_alerts = db.query(func.count(Alert.id)).scalar() or 0

    # Distribution des sentiments
    sentiment_dist = {}
    if analyzed_tweets > 0:
        rows = db.query(Tweet.sentiment, func.count(Tweet.id)).filter(
            Tweet.sentiment.isnot(None)
        ).group_by(Tweet.sentiment).all()
        for sentiment, count in rows:
            sentiment_dist[sentiment] = count

    # Usage API (tracké dans Redis)
    api_usage = {"groq_calls": 0, "twitter_calls": 0}
    try:
        r = redis.from_url(get_settings().redis_url)
        groq_calls = r.get("sentiflow:usage:groq_calls")
        twitter_calls = r.get("sentiflow:usage:twitter_calls")
        api_usage["groq_calls"] = int(groq_calls) if groq_calls else 0
        api_usage["twitter_calls"] = int(twitter_calls) if twitter_calls else 0
    except Exception:
        pass

    return {
        "tweets": {"total": total_tweets, "analyzed": analyzed_tweets, "pending": pending_tweets},
        "targets": total_targets,
        "users": total_users,
        "alerts": total_alerts,
        "sentiment_distribution": sentiment_dist,
        "api_usage": api_usage,
    }


@router.get("/dashboards")
def get_all_dashboards(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Liste tous les dashboards générés de tous les utilisateurs."""
    from backend.app.models.generated_dashboard import GeneratedDashboard

    dashboards = (
        db.query(GeneratedDashboard, User.username)
        .join(User, User.id == GeneratedDashboard.user_id)
        .order_by(GeneratedDashboard.id.desc())
        .limit(50)
        .all()
    )

    return [
        {
            "id": d.id,
            "title": d.title,
            "question": d.question,
            "user": username,
            "user_id": d.user_id,
            "target_ids": d.target_ids,
            "created_at": str(d.created_at) if d.created_at else None,
        }
        for d, username in dashboards
    ]


@router.post("/usage/reset")
def reset_usage_counters(
    current_user: User = Depends(require_admin),
):
    """Reset les compteurs d'usage API."""
    import redis
    from backend.app.config import get_settings
    r = redis.from_url(get_settings().redis_url)
    r.set("sentiflow:usage:groq_calls", 0)
    r.set("sentiflow:usage:twitter_calls", 0)
    return {"message": "Compteurs remis a zero"}


@router.get("/tweets/{target_id}")
def admin_get_tweets(
    target_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin : voir les tweets d'une cible (peu importe le propriétaire)."""
    tweets = (
        db.query(Tweet)
        .filter(Tweet.target_id == target_id)
        .order_by(Tweet.id.desc())
        .limit(20)
        .all()
    )
    return [
        {
            "id": t.id,
            "text": t.text,
            "author_username": t.author_username,
            "sentiment": t.sentiment,
            "confidence": float(t.confidence) if t.confidence else None,
            "analyzed_at": str(t.analyzed_at) if t.analyzed_at else None,
        }
        for t in tweets
    ]


@router.get("/all-targets")
def admin_get_all_targets(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin : liste toutes les cibles de tous les utilisateurs."""
    targets = (
        db.query(Target, User.username)
        .join(User, User.id == Target.user_id)
        .order_by(Target.id.desc())
        .all()
    )
    return [
        {
            "id": t.id,
            "name": t.name,
            "target_type": t.target_type.value if hasattr(t.target_type, 'value') else str(t.target_type),
            "query": t.query,
            "user_id": t.user_id,
            "owner": username,
        }
        for t, username in targets
    ]
