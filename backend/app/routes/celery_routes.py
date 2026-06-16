from fastapi import APIRouter, Depends
from backend.app.models.user import User
from backend.app.services.auth import get_current_user

router = APIRouter(prefix="/tasks", tags=["Celery Tasks"])


@router.post("/collect-all")
def trigger_collect_all(current_user: User = Depends(get_current_user)):
    """Déclenche la collecte de tous les tweets manuellement"""
    from backend.app.tasks import collect_all_targets
    task = collect_all_targets.delay()
    return {"task_id": task.id, "status": "started", "message": "Collecte lancée en arrière-plan"}


@router.post("/analyze-all")
def trigger_analyze_all(current_user: User = Depends(get_current_user)):
    """Déclenche l'analyse de tous les tweets manuellement"""
    from backend.app.tasks import analyze_all_targets
    task = analyze_all_targets.delay()
    return {"task_id": task.id, "status": "started", "message": "Analyse lancée en arrière-plan"}


@router.post("/check-alerts")
def trigger_check_alerts(current_user: User = Depends(get_current_user)):
    """Déclenche la vérification des alertes manuellement"""
    from backend.app.tasks import check_all_alerts
    task = check_all_alerts.delay()
    return {"task_id": task.id, "status": "started", "message": "Vérification des alertes lancée"}


@router.get("/status/{task_id}")
def get_task_status(task_id: str, current_user: User = Depends(get_current_user)):
    """Vérifie le statut d'une tâche Celery"""
    from backend.app.celery_app import celery_app
    result = celery_app.AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status": result.status,
        "result": result.result if result.ready() else None
    }
