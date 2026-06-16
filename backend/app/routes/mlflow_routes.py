from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Dict, Optional
from backend.app.models.user import User
from backend.app.services.auth import get_current_user
from backend.app.services.mlflow_tracking import log_finetuning_run, get_model_versions

router = APIRouter(prefix="/mlflow", tags=["MLflow"])


class FinetuningLog(BaseModel):
    run_name: str
    model_name: str
    params: Dict
    metrics: Dict
    tags: Optional[Dict] = None


@router.post("/log-run")
def log_run(
    data: FinetuningLog,
    current_user: User = Depends(get_current_user),
):
    """Log un run de fine-tuning dans MLflow"""
    success = log_finetuning_run(
        data.run_name, data.model_name, data.params, data.metrics, data.tags
    )
    return {"success": success}


@router.get("/versions")
def list_versions(
    current_user: User = Depends(get_current_user),
):
    """Liste les versions de modeles"""
    return get_model_versions()
