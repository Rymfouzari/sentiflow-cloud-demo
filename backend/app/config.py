from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from pathlib import Path
from dotenv import load_dotenv
import os

# Trouver le .env à la racine du projet (3 niveaux au-dessus de config.py)
# config.py -> app -> backend -> PROJET ANNUEL
root_dir = Path(__file__).parent.parent.parent
env_path = root_dir / ".env"

# Forcer le rechargement du .env (override=True)
load_dotenv(env_path, override=True)

# Debug: afficher si la clé est chargée
api_key = os.getenv('TWITTER_API_KEY', '')
print(f"[DEBUG] .env path: {env_path}")
print(f"[DEBUG] .env exists: {env_path.exists()}")
print(f"[DEBUG] TWITTER_API_KEY loaded: {bool(api_key)}")
print(f"[DEBUG] TWITTER_API_KEY value: {api_key[:10]}..." if api_key else "[DEBUG] TWITTER_API_KEY is empty")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    
    # App
    app_name: str = "SentiFlow"
    debug: bool = True
    
    # Database
    database_url: str = "postgresql://sentiflow:sentiflow@localhost:5432/sentiflow"
    
    # Redis
    redis_url: str = "redis://localhost:6379"
    
    # JWT
    jwt_secret: str = "your-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24
    
    # Twitter API (twitterapi.io)
    twitter_api_key: str = ""

    # Mistral API (RAG)
    mistral_api_key: str = ""

    # Groq API (RAG LLM generation)
    groq_api_key: str = ""

    # Kafka
    kafka_bootstrap_servers: str = "kafka:29092"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
