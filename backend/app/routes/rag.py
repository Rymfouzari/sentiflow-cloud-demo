from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel, Field
from backend.app.database import get_db
from backend.app.models.user import User
from backend.app.services.auth import get_current_user
from backend.app.services.rag import (
    chat,
    index_all_tweets,
    evaluate_rag,
    get_vector_index,
    hybrid_retrieve,
    load_eval_dataset,
)
from backend.app.services.mcp_server import execute_tool, list_tools

router = APIRouter(prefix="/rag", tags=["RAG From Scratch"])


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=3)
    target_id: Optional[int] = None
    days: int = Field(default=30, ge=1, le=90)
    enable_mcp: bool = Field(default=True, description="Si True, cherche sur Twitter en temps réel quand la BDD n'a pas assez de données")


class IndexRequest(BaseModel):
    target_id: Optional[int] = None
    days: int = Field(default=30, ge=1, le=90)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=2)
    top_k: int = Field(default=10, ge=1, le=50)
    target_id: Optional[int] = None


@router.get("/info")
def rag_info():
    """Informations sur le RAG from scratch (état de l'index, composants)."""
    index = get_vector_index()
    return {
        "from_scratch": True,
        "components": {
            "retriever": "TF-IDF + BM25 (codés à la main, pas de sklearn)",
            "vector_store": "Index NumPy in-memory (pas de pgvector/FAISS)",
            "fusion": "Reciprocal Rank Fusion (RRF)",
            "generator": "TinyGPT from scratch (Transformer PyTorch) + fallback déterministe",
        },
        "index": {
            "is_fitted": index.is_fitted,
            "indexed_count": index.indexed_count,
            "vocab_size": index.vectorizer.vocab_size if index.is_fitted else 0,
        },
    }


@router.post("/chat")
async def rag_chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Chat RAG from scratch + MCP.
    Si enable_mcp=True et que la BDD n'a pas assez de résultats,
    le RAG va chercher en temps réel sur Twitter via le serveur MCP.
    """
    result = await chat(db, request.question, request.target_id, enable_mcp=request.enable_mcp, user_id=current_user.id)
    return result


@router.post("/index")
def rag_index(
    request: IndexRequest = IndexRequest(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Indexe les tweets analysés dans le VectorIndex from scratch.
    Reconstruit l'index TF-IDF + BM25 en mémoire, puis le sauvegarde sur disque.
    """
    count = index_all_tweets(db, target_id=request.target_id, days=request.days)
    index = get_vector_index()
    # Sauvegarder sur disque pour persistance
    saved = index.save_to_disk()
    return {
        "indexed": count,
        "vocab_size": index.vectorizer.vocab_size,
        "saved_to_disk": saved,
        "from_scratch": True,
    }


@router.post("/search")
def rag_search(
    request: SearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recherche hybride seule (sans génération), utile pour debug/test."""
    results = hybrid_retrieve(
        db, request.query, top_k=request.top_k, target_id=request.target_id
    )
    return {
        "query": request.query,
        "results": results,
        "total": len(results),
        "from_scratch": True,
    }


class EvalRequest(BaseModel):
    log_mlflow: bool = True
    run_name: Optional[str] = None


@router.post("/evaluate")
async def rag_evaluate(
    request: EvalRequest = EvalRequest(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Évalue le RAG from scratch sur le dataset CSV.
    Log les métriques dans MLflow si disponible.
    """
    result = await evaluate_rag(db, log_mlflow=request.log_mlflow, run_name=request.run_name)
    return result


@router.get("/eval-dataset")
def get_eval_dataset():
    """Retourne le dataset d'évaluation actuellement chargé."""
    questions = load_eval_dataset()
    return {
        "total_questions": len(questions),
        "questions": questions,
    }


# ============================================
# ENDPOINTS MCP (outils exposés au LLM)
# ============================================


class MCPCallRequest(BaseModel):
    tool_name: str = Field(..., description="Nom de l'outil MCP à appeler")
    arguments: dict = Field(default_factory=dict, description="Arguments de l'outil")


@router.get("/mcp/tools")
def mcp_list_tools():
    """Liste tous les outils MCP disponibles pour le RAG."""
    return {
        "tools": list_tools(),
        "description": "Outils MCP from scratch — permettent au RAG d'accéder à Twitter en temps réel",
    }


@router.post("/mcp/call")
async def mcp_call_tool(
    request: MCPCallRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Appelle un outil MCP manuellement.
    Utile pour tester ou forcer une recherche Twitter temps réel.
    """
    result = await execute_tool(request.tool_name, request.arguments)
    return result
