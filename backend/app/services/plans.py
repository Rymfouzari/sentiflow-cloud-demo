"""
Gestion des abonnements SentiFlow : Free / Standard / Premium.

Centralise :
- la définition des limites et fonctionnalités par plan ;
- le quota journalier d'appels à l'assistant IA ;
- les helpers de gating (autorisation d'une fonctionnalité).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.app.models.user import User


# Définition des plans. ai_calls_per_day = None signifie illimité.
PLANS: dict[str, dict[str, Any]] = {
    "free": {
        "label": "Free",
        "price_eur": 0,
        "ai_calls_per_day": 5,
        "auto_collect": False,
        "interactive_dashboard": False,
        "advanced_dashboard": False,
        "alerts": False,
        "pdf_export": True,
        "features": [
            "5 appels assistant IA par jour",
            "Recherche RAG + MCP",
            "Export PDF des réponses",
        ],
        "limitations": [
            "Pas de dashboard interactif",
            "Pas de collecte automatique",
            "Pas d'alertes",
        ],
    },
    "standard": {
        "label": "Standard",
        "price_eur": 19,
        "ai_calls_per_day": 30,
        "auto_collect": True,
        "interactive_dashboard": True,
        "advanced_dashboard": False,
        "alerts": False,
        "pdf_export": True,
        "features": [
            "30 appels assistant IA par jour",
            "Collecte automatique des tweets",
            "Dashboard interactif",
            "Export PDF",
        ],
        "limitations": [
            "Pas d'alertes",
            "Analyses avancées (corrélation, ACP) limitées",
        ],
    },
    "premium": {
        "label": "Premium",
        "price_eur": 49,
        "ai_calls_per_day": None,  # illimité
        "auto_collect": True,
        "interactive_dashboard": True,
        "advanced_dashboard": True,
        "alerts": True,
        "pdf_export": True,
        "features": [
            "Appels assistant IA illimités",
            "Collecte automatique",
            "Dashboard interactif avancé (corrélations, ACP, réseau)",
            "Alertes temps réel",
            "Export PDF",
        ],
        "limitations": [],
    },
}

DEFAULT_PLAN = "free"


def get_plan_name(user: Optional[User]) -> str:
    if user is None:
        return DEFAULT_PLAN
    plan = getattr(user, "plan", None) or DEFAULT_PLAN
    return plan if plan in PLANS else DEFAULT_PLAN


def get_plan_config(plan_name: str) -> dict[str, Any]:
    return PLANS.get(plan_name, PLANS[DEFAULT_PLAN])


def get_features(user: Optional[User]) -> dict[str, Any]:
    """Retourne la config de plan d'un utilisateur (pour le frontend)."""
    plan = get_plan_name(user)
    return {"plan": plan, **get_plan_config(plan)}


def has_feature(user: Optional[User], feature: str) -> bool:
    config = get_plan_config(get_plan_name(user))
    return bool(config.get(feature, False))


def require_feature(user: Optional[User], feature: str, message: Optional[str] = None) -> None:
    """Lève une 403 si le plan de l'utilisateur n'inclut pas la fonctionnalité."""
    if not has_feature(user, feature):
        plan = get_plan_name(user)
        raise HTTPException(
            status_code=403,
            detail=message or (
                f"Cette fonctionnalité n'est pas incluse dans votre offre ({PLANS[plan]['label']}). "
                f"Passez à une offre supérieure pour y accéder."
            ),
        )


def _today_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def get_ai_quota_status(user: User) -> dict[str, Any]:
    """Retourne l'état du quota d'appels IA du jour (sans incrémenter)."""
    plan = get_plan_name(user)
    limit = get_plan_config(plan)["ai_calls_per_day"]
    today = _today_str()
    used = user.ai_calls_today or 0
    if user.ai_calls_date != today:
        used = 0
    remaining = None if limit is None else max(0, limit - used)
    return {
        "plan": plan,
        "limit": limit,
        "used": used,
        "remaining": remaining,
        "unlimited": limit is None,
    }


def consume_ai_call(db: Session, user: User) -> dict[str, Any]:
    """
    Incrémente le compteur d'appels IA du jour et bloque si le quota est dépassé.
    Lève une 429 si la limite quotidienne est atteinte.
    """
    plan = get_plan_name(user)
    limit = get_plan_config(plan)["ai_calls_per_day"]
    today = _today_str()

    # Réinitialisation quotidienne
    if user.ai_calls_date != today:
        user.ai_calls_today = 0
        user.ai_calls_date = today

    if limit is not None and (user.ai_calls_today or 0) >= limit:
        db.commit()
        raise HTTPException(
            status_code=429,
            detail=(
                f"Quota journalier atteint ({limit} appels assistant IA pour l'offre "
                f"{PLANS[plan]['label']}). Réessayez demain ou passez à une offre supérieure."
            ),
        )

    user.ai_calls_today = (user.ai_calls_today or 0) + 1
    user.ai_calls_date = today
    db.commit()

    remaining = None if limit is None else max(0, limit - user.ai_calls_today)
    return {"plan": plan, "limit": limit, "used": user.ai_calls_today, "remaining": remaining}
