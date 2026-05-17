from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "Sistema Predictivo de Costos de Importacion"
    environment: str = "development"
    database_url: str = "sqlite:///./prediccion.db"
    model_path: Path = PROJECT_ROOT / "models" / "modelo_activo.joblib"
    models_manifest_path: Path = PROJECT_ROOT / "models" / "models.json"
    metrics_path: Path = PROJECT_ROOT / "models" / "metrics.json"
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
