"""Project configuration (chargée depuis .env)."""
from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Chemins ---
    data_dir: Path = BASE_DIR / "data"
    raw_dir: Path = BASE_DIR / "data" / "raw"
    processed_dir: Path = BASE_DIR / "data" / "processed"
    chroma_dir: Path = BASE_DIR / "data" / "chroma"
    eval_dir: Path = BASE_DIR / "data" / "eval"

    # --- Embeddings ---
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"

    # --- Retrieval ---
    top_k: int = 6
    max_distance: float = 0.85          # au-delà => hors corpus
    enable_rerank: bool = False
    rerank_model: str = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
    default_status: str = "en vigueur"

    # --- LLM (Groq, OpenAI-compatible API) ---
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    llm_model: str = "openai/gpt-oss-120b"
    llm_max_tokens: int = 1500
    llm_temperature: float = 0.0

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.raw_dir, self.processed_dir,
                  self.chroma_dir, self.eval_dir):
            p.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
