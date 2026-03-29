import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Claude API
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

    # Langfuse
    LANGFUSE_SECRET_KEY: str = os.environ["LANGFUSE_SECRET_KEY"]
    LANGFUSE_PUBLIC_KEY: str = os.environ["LANGFUSE_PUBLIC_KEY"]
    LANGFUSE_HOST: str = os.getenv("LANGFUSE_HOST", "http://localhost:3000")

    # Ollama
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2")

    # Encryption
    ENCRYPTION_KEY: str = os.environ["ENCRYPTION_KEY"]

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


config = Config()
