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
    # Absolute path, not ".env" — a relative env_file resolves against the current
    # working directory, so running `uvicorn app.main:app` from the repo root
    # instead of from backend/ would silently miss the file and fall back to
    # SQLite. Anchoring it to the package means the configured database is used
    # no matter where the server is started from.
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_prefix="CASEINTEL_", extra="ignore"
    )

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
    #
    # These two names are a *preference*, not a requirement. Google retires
    # model IDs faster than a hackathon project gets updated — text-embedding-004
    # was withdrawn and gemini-2.5-flash closed to new keys while this was being
    # written — so the provider asks the key which models it can actually reach
    # and picks the closest match. A stale name here costs nothing.
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.6-flash"
    gemini_embed_model: str = "gemini-embedding-001"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"

    # 20s was too tight: Gemini 3.x flash defaults to high reasoning effort and
    # a structured extraction routinely ran past it on a domestic connection.
    # Extraction now asks for minimal thinking, but the ceiling stays generous —
    # a slow answer is still an answer, and the fallback costs a whole request.
    gemini_timeout_s: float = 45.0

    # Embedding width. gemini-embedding-001 returns 3072 by default and supports
    # Matryoshka truncation; 768 keeps stored vectors a quarter the size at
    # negligible quality cost. Vectors from different models are never compared,
    # so changing this is safe — it makes old vectors unusable, not wrong.
    gemini_embed_dim: int = 768

    # Set true to pin the names above exactly and fail rather than substitute.
    gemini_pin_models: bool = False

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
