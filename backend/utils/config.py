from functools import lru_cache
import os

from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseModel):
    database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./road_trip_planner.db")
    secret_key: str | None = os.getenv("SECRET_KEY")
    nvidia_api_key: str | None = os.getenv("NVIDIA_API_KEY")
    nvidia_model: str = os.getenv("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct")
    openweathermap_api_key: str | None = os.getenv("OPENWEATHERMAP_API_KEY")
    openrouteservice_api_key: str | None = os.getenv("OPENROUTESERVICE_API_KEY")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
