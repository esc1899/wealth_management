"""
Wealth Management CLI — interactive chat with the Portfolio Agent.
"""

import asyncio

from config import config
from core.storage.base import build_encryption_service, get_connection, init_db
from core.storage.portfolio import PortfolioRepository
from core.storage.watchlist import WatchlistRepository
from core.llm.local import OllamaProvider
from agents.portfolio_agent import PortfolioAgent


def build_agent() -> PortfolioAgent:
    conn = get_connection(config.DB_PATH)
    init_db(conn)
    enc = build_encryption_service(config.ENCRYPTION_KEY, "data/salt.bin")
    llm = OllamaProvider(host=config.OLLAMA_HOST, model=config.OLLAMA_MODEL)
    return PortfolioAgent(
        portfolio_repo=PortfolioRepository(conn, enc),
        watchlist_repo=WatchlistRepository(conn, enc),
        llm=llm,
    )


async def main() -> None:
    agent = build_agent()
    print("Portfolio Agent ready. Type 'quit' to exit.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_input or user_input.lower() in {"quit", "exit"}:
            break

        response = await agent.chat(user_input)
        print(f"Agent: {response}\n")


if __name__ == "__main__":
    asyncio.run(main())
