# Wealth Management

A self-hosted, agentic wealth management system built with Python, Streamlit, and local LLMs.

> **Disclaimer:** This app is for informational purposes only. AI-generated content does not constitute financial or investment advice. The authors accept no liability for financial losses. See [Disclaimer](#disclaimer) below.

> **Tip — Setup with Claude Code:** This project was built with and is optimized for [Claude Code](https://claude.ai/code). Using it for initial setup, configuration, and troubleshooting is recommended — but entirely optional.

## Requirements & Responsibility

This app **must be self-hosted**. The authors do not operate any instance of this software and have no access to your data at any time.

- You are solely responsible for your deployment, data security, and any API keys you configure.
- If you use external AI APIs (e.g. Anthropic API for Research Chat), your data is subject to that provider's terms and privacy policy.
- This project is **not affiliated** with Anthropic or any other AI provider.
- **Commercial use is strictly prohibited** — see [LICENSE](LICENSE) for details.

## Features

- **Portfolio Management** — track 11 asset types: stocks, ETFs, funds, precious metals, crypto, bonds, fixed deposits, cash, real estate, and land
- **Live Market Data** — automatic and on-demand prices via yfinance with EUR conversion
- **Portfolio Chat** — natural language interface powered by a local LLM (Ollama); data stays on your machine
- **Invest / Rebalance** — portfolio rebalancing analysis via local LLM
- **Research Chat** — AI-powered investment research using Claude API with web search
- **News Digest** — recent news for all portfolio positions, filtered by strategy
- **Investment Search** — screen for new opportunities using Claude + web search
- **Manage Positions** — full CRUD for portfolio and watchlist without any AI assistant
- **Skills System** — reusable prompt templates for research strategies; AI-assisted generation
- **Model Selection** — choose Ollama and Claude models at runtime in Settings
- **Recommendation & Story** — configurable recommendation labels and investment thesis per position
- **Detail View** — dialog drawer for each position with estimated value update for manual types
- **Demo Mode** — pre-seeded database with 20 realistic positions for testing
- **Bilingual UI** — German / English, switchable in Settings
- **System Status** — health checks for Ollama connectivity, privacy mode, and demo mode

## What You Can Learn Here

This project is a hands-on introduction to building real AI-powered applications.

### Running a local LLM with Ollama
Install Ollama and pull a model (e.g. `qwen3:8b`). Learn what running an LLM on your own hardware means: model size vs. RAM, context windows, cold start latency, and when a local model is good enough vs. when you need a cloud API.

### Using a cloud LLM API
The research and news features use the Anthropic Claude API. Get an API key, set it in `.env`, and see tokens consumed in the Statistics page. Learn what a token costs and why model choice (Haiku vs. Sonnet) matters.

### Privacy and where your data goes
The app has a live privacy indicator on every agent page. See the difference between a local model (portfolio data never leaves your machine) and a cloud API call (tickers go to Anthropic's servers). Health checks warn you if something is less private than expected.

### Keeping secrets with `.env`
API keys, encryption keys, and database paths live in `.env`, which is gitignored. Learn why this file must never be committed, what happens if it leaks, and how to manage multiple environments.

### Encrypted local storage
Portfolio data (quantities, prices, notes, investment thesis) is encrypted at rest with a Fernet key you generate yourself. Demo mode deliberately skips encryption — a useful contrast.

### Skills as reusable prompts
The Skills system lets you save and edit prompt templates for each agent. Learn that a well-written system prompt dramatically changes LLM output quality, and that externalising prompts from code makes them easier to iterate on.

### Monitoring with Langfuse
Optionally connect Langfuse to trace every LLM call — full prompt, response, latency, and token counts.

### Agent design trade-offs
The app has six agents with different characteristics: stateful vs. stateless, local vs. cloud, one-shot vs. conversational. Comparing Portfolio Chat, Rebalance, Research Chat, and News Digest shows the practical trade-offs: privacy, cost, speed, and capability.

---

## Tech Stack

- Python 3.9+, Streamlit
- SQLite (encrypted via cryptography/Fernet)
- Ollama (local LLM, e.g. qwen3:8b)
- Anthropic Claude API (optional, for Research/News/Search)
- yfinance for market data
- APScheduler for automated price fetching

## Quick Start

```bash
git clone https://github.com/esc1899/wealth_management.git
cd wealth_management
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env — set ENCRYPTION_KEY at minimum
streamlit run app.py
```

**Demo mode** (no encryption key required):
```bash
python scripts/seed_demo.py
DEMO_MODE=true streamlit run app.py
```

## Configuration

Copy `.env.example` to `.env` and fill in your values.

| Variable | Required | Description |
|---|---|---|
| `ENCRYPTION_KEY` | Yes | Fernet key — generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `ANTHROPIC_API_KEY` | See below | Direct Anthropic API key (for Research Chat, News Digest, Investment Search) |
| `ANTHROPIC_BASE_URL` | See below | LLM proxy URL — use instead of `ANTHROPIC_API_KEY` |
| `OLLAMA_HOST` | Optional | Default: `http://localhost:11434` |
| `OLLAMA_MODEL` | Optional | Default model for Portfolio Chat and Rebalance (overridable in Settings UI) |
| `LANGFUSE_SECRET_KEY` | Optional | Langfuse monitoring (omit to disable) |
| `LANGFUSE_PUBLIC_KEY` | Optional | Langfuse monitoring (omit to disable) |
| `DEMO_MODE` | Optional | Set to `true` to use the demo database |
| `DB_PATH` | Optional | Default: `data/portfolio.db` |
| `MARKET_DATA_FETCH_HOUR` | Optional | Hour (0–23) for automatic price refresh, default `18` |

At least one of `ANTHROPIC_API_KEY` or `ANTHROPIC_BASE_URL` is required to use Research Chat, News Digest, or Investment Search.

### LLM Proxy (corporate environments)

```env
ANTHROPIC_BASE_URL=https://your-llm-proxy.example.com
```

The proxy must expose an Anthropic-compatible API.

### Multi-Environment Setup

Use environment profiles to maintain separate configs for different machines:

```bash
# .env.work — only the values that differ
ANTHROPIC_BASE_URL=https://corp-proxy.example.com
OLLAMA_HOST=http://workstation.local:11434
DB_PATH=data/work.db
```

```bash
ENV_PROFILE=work streamlit run app.py
```

## Disclaimer

This app is for informational purposes only. AI-generated content does not constitute financial or investment advice. The authors accept no liability for financial losses based on information provided by this app. This software is provided as-is with no warranties of any kind.

## Privacy

See [PRIVACY.md](PRIVACY.md) for the full privacy notice.

## License

[Business Source License 1.1](LICENSE) — commercial use prohibited.
