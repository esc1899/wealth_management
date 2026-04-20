import os
from pathlib import Path
from dotenv import load_dotenv

from core.constants import CLAUDE_MODELS_DEFAULT_LIST

_PROJECT_ROOT = Path(__file__).parent


def _resolve_db_path(env_var: str, default: str) -> str:
    """Convert relative DB paths to absolute (relative to project root)."""
    path_str = os.getenv(env_var, default)
    path = Path(path_str)
    if not path.is_absolute():
        path = _PROJECT_ROOT / path
    return str(path)


load_dotenv()
# Optional profile override: ENV_PROFILE=work loads .env.work on top of .env
_profile = os.getenv("ENV_PROFILE", "")
if _profile:
    load_dotenv(f".env.{_profile}", override=True)


class Config:
    # Claude API
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

    # Tavily Search (optional — replaces Anthropic's built-in web_search when set)
    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")

    # Ollama
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2")
    OLLAMA_NUM_CTX: int = int(os.getenv("OLLAMA_NUM_CTX", "8192"))

    # Encryption
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "")

    # App authentication (optional — leave empty to disable login)
    APP_PASSWORD: str = os.getenv("APP_PASSWORD", "")

    # Demo mode
    DEMO_MODE: bool = os.getenv("DEMO_MODE", "false").lower() == "true"

    # Storage — in demo mode, use the demo DB (convert relative paths to absolute)
    DEMO_DB_PATH: str = _resolve_db_path("DEMO_DB_PATH", "data/demo.db")
    DB_PATH: str = (
        _resolve_db_path("DEMO_DB_PATH", "data/demo.db")
        if DEMO_MODE
        else _resolve_db_path("DB_PATH", "data/portfolio.db")
    )

    # Market data
    MARKET_DATA_FETCH_HOUR: int = int(os.getenv("MARKET_DATA_FETCH_HOUR", "18"))
    RATE_LIMIT_RPS: float = float(os.getenv("RATE_LIMIT_RPS", "2.0"))

    # Available Claude models — restrict per environment via CLAUDE_MODELS env var
    CLAUDE_MODELS: list = [
        m.strip()
        for m in os.getenv(
            "CLAUDE_MODELS",
            CLAUDE_MODELS_DEFAULT_LIST,
        ).split(",")
        if m.strip()
    ]

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Currency — EUR (default), CHF, GBP, USD, JPY
    BASE_CURRENCY: str = os.getenv("BASE_CURRENCY", "EUR")

    # Backup
    BACKUP_REPO_PATH: str = os.getenv("BACKUP_REPO_PATH", "")
    RESTIC_PASSWORD_FILE: str = os.getenv("RESTIC_PASSWORD_FILE", "")

    def validate(self) -> list[str]:
        """Return list of error messages for missing required config. Empty = OK."""
        errors = []
        if not self.DEMO_MODE and not self.ENCRYPTION_KEY:
            errors.append(
                "ENCRYPTION_KEY is not set. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        if not self.ANTHROPIC_API_KEY:
            errors.append(
                "ANTHROPIC_API_KEY is not set. "
                "Set it in your .env file."
            )
        return errors


config = Config()
