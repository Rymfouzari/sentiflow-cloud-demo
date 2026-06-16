import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config import get_settings
from backend.app.database import engine, Base
from backend.app.routes import (
    auth_router,
    targets_router,
    tweets_router,
    analysis_router,
    alerts_router,
    twitter_router,
    admin_router,
    tasks_router,
    llm_router,
    dashboards_router,
    feedback_router,
)
from backend.app.routes.rag import router as rag_router
from backend.app.routes.assistant import router as assistant_router
from backend.app.routes.analytics import router as analytics_router
from backend.app.routes.tickets import router as tickets_router

# Configuration du logging global
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("sentiflow")

settings = get_settings()

# Activer pgvector
from sqlalchemy import text as sql_text
try:
    with engine.connect() as conn:
        conn.execute(sql_text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
except Exception:
    pass  # pgvector pas dispo, pas grave — RAG from scratch n'en a pas besoin

# Créer les tables
Base.metadata.create_all(bind=engine)

# Migrations de schema si nécessaire
try:
    from backend.app.services.demo_schema_migrations import run_demo_schema_migrations
    run_demo_schema_migrations(engine)
except ImportError:
    pass

app = FastAPI(
    title=settings.app_name,
    description="API d'analyse de sentiments Twitter avec RAG from scratch + MCP",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(targets_router)
app.include_router(tweets_router)
app.include_router(analysis_router)
app.include_router(alerts_router)
app.include_router(twitter_router)
app.include_router(admin_router)
app.include_router(tasks_router)
app.include_router(llm_router)
app.include_router(dashboards_router)
app.include_router(feedback_router)
app.include_router(rag_router)
app.include_router(assistant_router)
app.include_router(analytics_router)
app.include_router(tickets_router)


@app.get("/health")
def health():
    return {"status": "ok"}


# Servir le frontend React buildé
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

FRONTEND_BUILD = Path("/app/frontend_build")
if FRONTEND_BUILD.exists() and (FRONTEND_BUILD / "index.html").exists():
    # Fichiers statiques JS/CSS
    app.mount("/static", StaticFiles(directory=FRONTEND_BUILD / "static"), name="static")

    # Routes frontend (React Router)
    @app.get("/", include_in_schema=False)
    async def serve_root():
        return FileResponse(FRONTEND_BUILD / "index.html")

    @app.get("/login", include_in_schema=False)
    @app.get("/about", include_in_schema=False)
    @app.get("/dashboard", include_in_schema=False)
    @app.get("/cibles", include_in_schema=False)
    @app.get("/alertes", include_in_schema=False)
    @app.get("/assistant", include_in_schema=False)
    @app.get("/rag", include_in_schema=False)
    @app.get("/admin", include_in_schema=False)
    @app.get("/dashboards/generated", include_in_schema=False)
    @app.get("/dashboards/generated/{id}", include_in_schema=False)
    async def serve_spa_routes(id: str = ""):
        return FileResponse(FRONTEND_BUILD / "index.html")

    # Fichiers racine (favicon, logo, manifest)
    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        return FileResponse(FRONTEND_BUILD / "favicon.ico")

    @app.get("/logo.png", include_in_schema=False)
    async def logo():
        return FileResponse(FRONTEND_BUILD / "logo.png")

    @app.get("/manifest.json", include_in_schema=False)
    async def manifest():
        return FileResponse(FRONTEND_BUILD / "manifest.json")

    @app.get("/robots.txt", include_in_schema=False)
    async def robots():
        return FileResponse(FRONTEND_BUILD / "robots.txt")
