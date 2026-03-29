# Wealth Management

A self-hosted, agentic wealth management system built with Python, Streamlit, and local LLMs.

> **Disclaimer:** This app is for informational purposes only. AI-generated content does not constitute financial or investment advice. The authors accept no liability for financial losses. See [Disclaimer](#disclaimer) below.

## Requirements & Responsibility

This app **must be self-hosted**. The authors do not operate any instance of this software and have no access to your data at any time.

- You are solely responsible for your deployment, data security, and any API keys you configure.
- If you use external AI APIs (e.g. Anthropic API for Research Chat), your data is subject to that provider's terms and privacy policy.
- This project is **not affiliated** with Anthropic or any other AI provider.
- **Commercial use is strictly prohibited** — see [LICENSE](LICENSE) for details.

## Features

- **Portfolio Management** — track stocks, ETFs, funds, and precious metals
- **Live Market Data** — real-time prices via yfinance with EUR conversion
- **Portfolio Chat** — natural language interface powered by a local LLM (Ollama)
- **Research Chat** — AI-powered investment research using Claude API with web search
- **Skills System** — reusable prompt templates for research strategies
- **Demo Mode** — pre-seeded demo database for testing and demonstration
- **Bilingual UI** — German / English

## Tech Stack

- Python 3.9+, Streamlit
- SQLite (encrypted via cryptography/Fernet)
- Ollama (local LLM, e.g. llama3.2)
- Anthropic Claude API (optional, for Research Chat)
- yfinance for market data
- APScheduler for automated price fetching

## Quick Start

```bash
git clone https://github.com/esc1899/wealth_management.git
cd wealth_management
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env, then:
streamlit run app.py
```

**Demo mode:**
```bash
python scripts/seed_demo.py
DEMO_MODE=true streamlit run app.py
```

## Configuration

Copy `.env.example` to `.env`:

| Variable | Required | Description |
|---|---|---|
| `ENCRYPTION_KEY` | Yes | Fernet key for encrypting portfolio data |
| `LANGFUSE_SECRET_KEY` | Yes | Langfuse monitoring |
| `LANGFUSE_PUBLIC_KEY` | Yes | Langfuse monitoring |
| `ANTHROPIC_API_KEY` | Optional | Required for Research Chat |
| `OLLAMA_HOST` | Optional | Default: http://localhost:11434 |
| `DEMO_MODE` | Optional | Set to `true` for demo database |

## Disclaimer

This app is for informational purposes only. AI-generated content does not constitute financial or investment advice. The authors accept no liability for financial losses based on information provided by this app. This software is provided as-is with no warranties of any kind.

## Privacy

See [PRIVACY.md](PRIVACY.md) for the full privacy notice.

## License

[Business Source License 1.1](LICENSE) — commercial use prohibited.
