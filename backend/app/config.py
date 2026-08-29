"""Runtime configuration.

Everything degrades: no database URL falls back to SQLite, no Gemini key falls
back to local implementations, no InsightFace models fall back to a documented
image descriptor. The service starts and the pipeline returns computed results
in all of those cases — see app/services/ for the adapters.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CASEINTEL_", extra="ignore")

    app_name: str = "CASE//INTEL API"
    version: str = "1.0.0"
    debug: bool = False

    # postgresql+psycopg://user:pass@host:5432/caseintel in production
    database_url: str = f"sqlite:///{BASE_DIR / 'caseintel.db'}"

    cors_origins: list[str] = [
        "http://localhost:5173", "http://localhost:4173",
        "http://127.0.0.1:5173", "http://127.0.0.1:4173",
    ]

    media_root: Path = BASE_DIR / "media"

    # --- Gemini ---------------------------------------------------------
    # Used for: structured extraction from free-text marks, text embeddings,
    # evidence narratives, and image quality / soft-attribute reads.
    # NOT used for face identification — Gemini has no face-embedding endpoint
    # and its policy prohibits identifying individuals from images.
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    gemini_embed_model: str = "text-embedding-004"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_timeout_s: float = 20.0

    # --- Face recognition ----------------------------------------------
    # InsightFace ArcFace ("buffalo_l" bundles a ResNet-100 trained with the
    # additive angular margin loss). Falls back to a local descriptor when the
    # package or model files are absent.
    face_model_pack: str = "buffalo_l"
    face_model_root: Path = BASE_DIR / "models"
    face_embedding_dim: int = 512

    # --- Matching -------------------------------------------------------
    hard_search_geo_degrees: float = 14.0   # bounding-box prefilter, ~1500 km
    max_candidates_returned: int = 12
    min_confidence_returned: float = 0.30

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.media_root.mkdir(parents=True, exist_ok=True)
    return s


settings = get_settings()
