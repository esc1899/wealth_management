import os
from dotenv import load_dotenv

load_dotenv()
# Optional profile override: ENV_PROFILE=work loads .env.work on top of .env
_profile = os.getenv("ENV_PROFILE", "")
if _profile:
    load_dotenv(f".env.{_profile}", override=True)


class Config:
    # Claude API
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

    # Langfuse (optional monitoring — omit keys to disable)
    LANGFUSE_SECRET_KEY: str = os.getenv("LANGFUSE_SECRET_KEY", "")
    LANGFUSE_PUBLIC_KEY: str = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    LANGFUSE_HOST: str = os.getenv("LANGFUSE_HOST", "http://localhost:3000")

    # Ollama
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2")

    # Encryption
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "")

    # Demo mode
    DEMO_MODE: bool = os.getenv("DEMO_MODE", "false").lower() == "true"
    DEMO_DB_PATH: str = os.getenv("DEMO_DB_PATH", "data/demo.db")

    # Storage — in demo mode, use the demo DB
    DB_PATH: str = (
        os.getenv("DEMO_DB_PATH", "data/demo.db")
        if os.getenv("DEMO_MODE", "false").lower() == "true"
        else os.getenv("DB_PATH", "data/portfolio.db")
    )

    # Market data
    MARKET_DATA_FETCH_HOUR: int = int(os.getenv("MARKET_DATA_FETCH_HOUR", "18"))
    RATE_LIMIT_RPS: float = float(os.getenv("RATE_LIMIT_RPS", "2.0"))

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
