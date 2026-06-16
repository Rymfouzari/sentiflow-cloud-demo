"""
MLflow tracking pour le versioning des modeles et le suivi des experiences.

Usage:
- Depuis le notebook Colab: log les metriques de fine-tuning
- Depuis l'app: log les performances en production
- Dashboard: http://localhost:5000
"""
import logging
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger("sentiflow.mlflow")

MLFLOW_TRACKING_URI = "http://mlflow:5000"


def log_finetuning_run(
    run_name: str,
    model_name: str,
    params: Dict,
    metrics: Dict,
    tags: Optional[Dict] = None,
):
    """Log un run de fine-tuning dans MLflow"""
    try:
        import mlflow
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        mlflow.set_experiment("sentiflow-finetuning")

        with mlflow.start_run(run_name=run_name):
            # Parametres
            for k, v in params.items():
                mlflow.log_param(k, v)

            # Metriques
            for k, v in metrics.items():
                mlflow.log_metric(k, v)

            # Tags
            mlflow.set_tag("model_name", model_name)
            mlflow.set_tag("timestamp", datetime.utcnow().isoformat())
            if tags:
                for k, v in tags.items():
                    mlflow.set_tag(k, v)

        logger.info(f"[MLFLOW] Run '{run_name}' logged")
        return True
    except Exception as e:
        logger.warning(f"[MLFLOW] Erreur logging: {e}")
        return False


def log_production_metrics(metrics: Dict):
    """Log les metriques de production (monitoring)"""
    try:
        import mlflow
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        mlflow.set_experiment("sentiflow-production")

        with mlflow.start_run(run_name=f"prod_{datetime.utcnow().strftime('%Y%m%d_%H%M')}"):
            for k, v in metrics.items():
                if isinstance(v, (int, float)):
                    mlflow.log_metric(k, v)

        logger.info("[MLFLOW] Production metrics logged")
        return True
    except Exception as e:
        logger.warning(f"[MLFLOW] Erreur logging production: {e}")
        return False


def get_model_versions():
    """Liste les versions de modeles enregistrees"""
    try:
        import mlflow
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        client = mlflow.tracking.MlflowClient()

        experiment = client.get_experiment_by_name("sentiflow-finetuning")
        if not experiment:
            return []

        runs = client.search_runs(
            experiment_ids=[experiment.experiment_id],
            order_by=["start_time DESC"],
            max_results=20,
        )

        return [
            {
                "run_id": r.info.run_id,
                "run_name": r.info.run_name,
                "status": r.info.status,
                "start_time": r.info.start_time,
                "params": dict(r.data.params),
                "metrics": {k: round(v, 4) for k, v in r.data.metrics.items()},
                "tags": dict(r.data.tags),
            }
            for r in runs
        ]
    except Exception as e:
        logger.warning(f"[MLFLOW] Erreur listing: {e}")
        return []
