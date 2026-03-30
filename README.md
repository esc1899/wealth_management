# Wealth Management

A self-hosted, agentic wealth management system built with Python, Streamlit, and local LLMs.

> **Disclaimer:** This app is for informational purposes only. AI-generated content does not constitute financial or investment advice. The authors accept no liability for financial losses. See [Disclaimer](#disclaimer) below.

> **Tip — Setup with Claude Code:** This project was built with and is optimized for [Claude Code](https://claude.ai/code). Using it for initial setup, configuration, and troubleshooting is recommended — but entirely optional. All setup steps can be followed manually without it.

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

## What You Can Learn Here

This project is a hands-on introduction to building real AI-powered applications. By setting it up and using it you will encounter — and have to solve — most of the practical challenges that come up in production AI projects.

### Running a local LLM with Ollama

You will install Ollama and pull a model (e.g. `qwen3:8b`). This teaches you what it means for an LLM to run *on your hardware*: how model size relates to RAM and performance, what a "context window" feels like in practice, and why a local model can be slower on first call (model load). You will develop an intuition for when a local model is good enough and when you need something more capable.

### Using a cloud LLM API

The research and news features use the Anthropic Claude API. You will get an API key, set it in `.env`, and see tokens being consumed in the Statistics page. This makes abstract concepts concrete: what is a token, what does a call cost, why does model choice (Haiku vs. Sonnet) matter for cost and quality.

### Privacy and where your data goes

The app has a live privacy indicator on every agent page. You will see the difference between a locally running model (your portfolio data never leaves your machine) and a cloud API call (your tickers go to Anthropic's servers). This is not theoretical — the setup health checks will warn you if something is not as private as you expect.

### Keeping secrets with `.env`

API keys, encryption keys, and database paths live in `.env`, which is gitignored. You will learn why this file must never be committed, what happens if it leaks, and how to manage different configs for home vs. work using environment profiles.

### Encrypted local storage

Portfolio data (quantities, prices, notes) is encrypted at rest with a Fernet key you generate yourself. You will see what "encrypted at rest" means in practice: who holds the key, what an attacker gets without it, and why demo mode deliberately skips encryption.

### Skills as reusable prompts

The Skills system lets you save and edit prompt templates for each agent. This is a lightweight version of prompt engineering in production: you will learn that a well-written system prompt dramatically changes the quality of LLM output, and that externalising prompts from code makes them easier to iterate on.

### Monitoring with Langfuse

Optionally connect Langfuse to trace every LLM call. You will see the full prompt, the response, latency, and token counts — exactly what observability looks like for AI applications.

### Understanding agent design trade-offs

The app has five agents with different characteristics: stateful vs. stateless, local vs. cloud, one-shot vs. conversational. Comparing how Portfolio Chat, Rebalance, Research Chat, and News Digest are built shows you the practical trade-offs: privacy, cost, speed, and capability.

### The trust question

You will face a real question: *am I comfortable putting my actual portfolio into a system that sometimes sends data to a cloud API?* The app is designed to make this trade-off explicit rather than hiding it. Working through that question is itself a valuable exercise in responsible AI use.

---

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

Copy `.env.example` to `.env` and fill in your values.

| Variable | Required | Description |
|---|---|---|
| `ENCRYPTION_KEY` | Yes | Fernet key — generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `ANTHROPIC_API_KEY` | See below | Direct Anthropic API key (for Research Chat) |
| `ANTHROPIC_BASE_URL` | See below | LLM proxy URL — use instead of `ANTHROPIC_API_KEY` |
| `OLLAMA_HOST` | Optional | Default: `http://localhost:11434` |
| `OLLAMA_MODEL` | Optional | Default: `llama3.2` |
| `LANGFUSE_SECRET_KEY` | Optional | Langfuse monitoring (omit to disable) |
| `LANGFUSE_PUBLIC_KEY` | Optional | Langfuse monitoring (omit to disable) |
| `DEMO_MODE` | Optional | Set to `true` to use the demo database |
| `DB_PATH` | Optional | Default: `data/portfolio.db` |
| `MARKET_DATA_FETCH_HOUR` | Optional | Hour (0–23) for automatic price refresh, default `18` |

At least one of `ANTHROPIC_API_KEY` or `ANTHROPIC_BASE_URL` is required to use Research Chat.

### LLM Proxy (corporate environments)

If your organisation routes LLM traffic through a proxy instead of issuing direct API keys,
set `ANTHROPIC_BASE_URL` to your proxy endpoint and leave `ANTHROPIC_API_KEY` unset:

```env
ANTHROPIC_BASE_URL=https://your-llm-proxy.example.com
```

The proxy must expose an Anthropic-compatible API.

### Multi-Environment Setup

Use environment profiles to maintain separate configs for different machines
(e.g. home vs. work) without duplicating your base `.env`:

1. Keep shared defaults in `.env`
2. Create a profile file with only the overrides: `.env.work`
3. Set `ENV_PROFILE=work` when starting the app — it loads `.env.work` on top of `.env`

```bash
# .env.work — only the values that differ from .env
ANTHROPIC_BASE_URL=https://your-corp-proxy.example.com
OLLAMA_HOST=http://work-server:11434
DB_PATH=data/work.db
```

```bash
ENV_PROFILE=work streamlit run app.py
```

### Demo Data on a New Machine

To recreate the demo database on any machine:

```bash
python scripts/seed_demo.py        # creates data/demo.db
DEMO_MODE=true streamlit run app.py
```

## Disclaimer

This app is for informational purposes only. AI-generated content does not constitute financial or investment advice. The authors accept no liability for financial losses based on information provided by this app. This software is provided as-is with no warranties of any kind.

## Privacy

See [PRIVACY.md](PRIVACY.md) for the full privacy notice.

## License

[Business Source License 1.1](LICENSE) — commercial use prohibited.
