# Installation Guide

## Requirements

- Python 3.9 or higher
- [Ollama](https://ollama.com) installed and running locally
- An [Anthropic API key](https://console.anthropic.com) — required for Research Chat, News Digest, and Investment Search
  - Alternatively: a corporate LLM proxy that exposes an Anthropic-compatible API

---

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/esc1899/wealth_management.git
cd wealth_management

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy and fill in the configuration
cp .env.example .env
# edit .env with your values (see Configuration section below)

# 5. Pull an Ollama model (used by Portfolio Chat and Rebalance)
ollama pull llama3.2

# 6. Start the app
streamlit run app.py
```

The app opens at [http://localhost:8501](http://localhost:8501).

---

## Configuration

Edit `.env` with your values. Only `ENCRYPTION_KEY` and one of the Claude API options are
strictly required for full functionality.

### Required

```env
# Generate with:
# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY=your_fernet_key_here
```

### Claude API (choose one)

```env
# Option A: direct Anthropic API key
ANTHROPIC_API_KEY=sk-ant-...

# Option B: corporate LLM proxy (leave ANTHROPIC_API_KEY unset)
ANTHROPIC_BASE_URL=https://your-llm-proxy.example.com
```

### Ollama

```env
OLLAMA_HOST=http://localhost:11434   # default — change if Ollama runs elsewhere
OLLAMA_MODEL=llama3.2               # any model you have pulled
```

### Optional

```env
# Langfuse monitoring (omit both keys to disable)
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_HOST=http://localhost:3000

# Storage
DB_PATH=data/portfolio.db

# Market data
MARKET_DATA_FETCH_HOUR=18   # daily automatic price fetch hour (0–23)
RATE_LIMIT_RPS=2.0          # yfinance requests per second
```

---

## Multi-Environment Setup

If you run the app on multiple machines (e.g. home and work), use environment profiles
to keep machine-specific overrides separate from your shared base config.

**Setup:**

1. Create a base `.env` with shared defaults
2. Create `.env.work` with only the values that differ on the work machine:

```env
# .env.work
ANTHROPIC_BASE_URL=https://corp-proxy.example.com
OLLAMA_HOST=http://workstation.local:11434
DB_PATH=data/work.db
```

3. Start the app with `ENV_PROFILE=work`:

```bash
ENV_PROFILE=work streamlit run app.py
```

`.env.work` values override `.env`. All other values fall back to `.env`.

---

## Demo Mode

Demo mode loads a pre-seeded portfolio database with 17 realistic positions.
Useful for testing or demonstration without entering real data.

```bash
# Seed the demo database (fetches real historical prices)
python scripts/seed_demo.py

# Start in demo mode
DEMO_MODE=true streamlit run app.py
```

To recreate the demo database on a different machine:
```bash
DEMO_DB_PATH=data/demo.db python scripts/seed_demo.py
```

No `ENCRYPTION_KEY` is required in demo mode.

---

## Langfuse Monitoring (Optional)

Langfuse provides LLM call monitoring and tracing. A Docker Compose stack is included.

```bash
# Start Langfuse (PostgreSQL + ClickHouse + Redis + MinIO)
docker compose up -d

# Open the Langfuse UI
open http://localhost:3000
```

Create a project in Langfuse, copy the API keys, and add them to `.env`:

```env
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_HOST=http://localhost:3000
```

Omit both keys to disable monitoring entirely.

---

## Ollama Model Selection

The Portfolio Chat and Rebalance agent use the model configured in `OLLAMA_MODEL`.

Recommended models:

| Model | Size | Notes |
|---|---|---|
| `llama3.2` | 2B | Fast, good for structured tasks |
| `qwen3:8b` | 8B | Better reasoning, higher quality |
| `llama3.1:8b` | 8B | Good general-purpose model |

```bash
ollama pull qwen3:8b
```

Then update `.env`:
```env
OLLAMA_MODEL=qwen3:8b
```

---

## Updating

```bash
git pull
pip install -r requirements.txt   # update dependencies if needed
streamlit run app.py
```

The database schema is updated automatically on startup (`CREATE TABLE IF NOT EXISTS`).
No manual migration steps are needed for new tables.

---

## Troubleshooting

**App shows "Configuration error: ENCRYPTION_KEY is not set"**
→ Run the generate command shown in the error message and add the key to `.env`.

**Portfolio Chat fails with connection error**
→ Make sure Ollama is running: `ollama serve`

**Research / News / Search Chat fails with API error**
→ Check that `ANTHROPIC_API_KEY` or `ANTHROPIC_BASE_URL` is set in `.env`.

**Prices not updating**
→ Click **Refresh Now** on the Market Data page. Check that tickers are valid yfinance symbols.

**Demo mode not working**
→ Run `python scripts/seed_demo.py` first to create the demo database.
