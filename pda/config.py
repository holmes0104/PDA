"""Configuration loaded from environment (.env) and defaults."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Locate the project root .env file — works regardless of CWD
# (backend/ vs project root vs anywhere else)
_THIS_DIR = Path(__file__).resolve().parent          # pda/
_PROJECT_ROOT = _THIS_DIR.parent                     # PDA/
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM provider: openai | anthropic
    pda_llm_provider: str = "openai"

    # Embedding model: openai | sentence-transformers
    pda_embedding_model: str = "openai"

    # OpenAI
    openai_api_key: str | None = None
    pda_openai_model: str = "gpt-5.2"

    # Anthropic
    anthropic_api_key: str | None = None
    pda_anthropic_model: str = "claude-3-5-sonnet-20241022"

    # Data directory — default ./data locally, /data on hosted (Render persistent disk)
    pda_data_dir: str = "./data"

    # Output (deprecated, use pda_data_dir)
    pda_output_dir: str | None = None

    # Vector store backend: "chroma" (default) or "pgvector"
    pda_vector_backend: str = "chroma"

    # Database URL for pgvector backend (only used when pda_vector_backend=pgvector)
    pda_database_url: str | None = None

    # CORS origins (comma-separated). Defaults to localhost dev.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    # Optional regex to allow origins (e.g. https://.*\.vercel\.app for all Vercel deploys)
    cors_origin_regex: str | None = None

    # Server port (Render injects PORT)
    port: int = 8000

    # Max upload size in bytes (default 50 MB)
    max_upload_bytes: int = 50 * 1024 * 1024

    @property
    def data_dir(self) -> Path:
        """Get data directory as Path (OS-agnostic).
        
        Relative paths are resolved against the project root (not CWD),
        so the backend works whether started from project root or backend/.
        """
        p = Path(self.pda_data_dir)
        if not p.is_absolute():
            return (_PROJECT_ROOT / p).resolve()
        return p.resolve()

    @property
    def output_dir(self) -> Path:
        """Get output directory (defaults to data/output)."""
        if self.pda_output_dir:
            return Path(self.pda_output_dir).resolve()
        return self.data_dir / "output"

    @property
    def uploads_dir(self) -> Path:
        """Get uploads directory."""
        return self.data_dir / "uploads"

    @property
    def chroma_dir(self) -> Path:
        """Get ChromaDB persistence directory."""
        return self.data_dir / "chroma"

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def ensure_dirs(self) -> None:
        """Ensure all data directories exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.chroma_dir.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
