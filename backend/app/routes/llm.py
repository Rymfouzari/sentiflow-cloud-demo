from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.user import User
from backend.app.services.auth import get_current_user
from backend.app.services.local_llm import ask_local_llm
from backend.app.services.llm_agent import AgentError, run_sentiflow_agent
from backend.app.services.llm_from_scratch import get_planner


router = APIRouter(prefix="/llm", tags=["LLM SentiFlow"])


class LLMAskRequest(BaseModel):
    """Mode analyse uniquement : utilise des cibles déjà connues et déjà collectées."""

    question: str = Field(..., min_length=3)
    target_ids: List[int]
    days: int = Field(default=7, ge=1, le=90)
    generate_dashboard: bool = True


class LLMAgentRequest(BaseModel):
    """Mode agent : le LLM peut créer/collecter/analyser si nécessaire."""

    question: str = Field(..., min_length=3)
    days: int | None = Field(default=None, ge=1, le=90)
    generate_dashboard: bool | None = True
    force_refresh: bool | None = None
    allow_auto_collect: bool = True
    allow_auto_analyze: bool = True


@router.get("/model-info")
def llm_model_info():
    planner = get_planner()
    return planner.model_info()


@router.post("/ask")
def ask_llm(
    payload: LLMAskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Ancien mode : le frontend donne déjà les target_ids.
    Utile pour analyser/comparer des cibles déjà présentes.
    """
    try:
        return ask_local_llm(
            db=db,
            user_id=current_user.id,
            question=payload.question,
            target_ids=payload.target_ids,
            days=payload.days,
            generate_dashboard=payload.generate_dashboard,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/agent")
async def ask_llm_agent(
    payload: LLMAgentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Nouveau mode agentique :
    - comprend la demande via le LLM from scratch spécialisé ;
    - crée les cibles manquantes ;
    - collecte les tweets si nécessaire ;
    - analyse uniquement les tweets non analysés ;
    - répond sur les données déjà analysées ou nouvellement analysées ;
    - génère une configuration de dashboard.
    """
    try:
        return await run_sentiflow_agent(
            db=db,
            user_id=current_user.id,
            question=payload.question,
            days=payload.days,
            generate_dashboard=payload.generate_dashboard,
            force_refresh=payload.force_refresh,
            allow_auto_collect=payload.allow_auto_collect,
            allow_auto_analyze=payload.allow_auto_analyze,
        )
    except AgentError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
