from functools import lru_cache
import os

from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseModel):
    database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./road_trip_planner.db")
    reports_dir: str = os.getenv("REPORTS_DIR", "./reports")
    rag_chroma_dir: str = os.getenv("RAG_CHROMA_DIR", "./rag/chroma_store")
    secret_key: str | None = os.getenv("SECRET_KEY")
    nvidia_api_key: str | None = os.getenv("NVIDIA_API_KEY")
    nvidia_model: str = os.getenv("NVIDIA_MODEL_NAME", os.getenv("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct"))
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    geoapify_api_key: str | None = os.getenv("GEOAPIFY_API_KEY") or os.getenv("geoapify_api_key")
    openweathermap_api_key: str | None = os.getenv("OPENWEATHERMAP_API_KEY")
    openrouteservice_api_key: str | None = os.getenv("OPENROUTESERVICE_API_KEY")
    osm_user_agent: str = os.getenv("OSM_USER_AGENT", "RoadMindAI/1.0")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
