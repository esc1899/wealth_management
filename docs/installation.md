# Installation Guide

## Requirements

- Python 3.9 or higher
- [Ollama](https://ollama.com) installed and running locally
- An [Anthropic API key](https://console.anthropic.com) — required for Research Chat, News Digest, and Investment Search

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
ollama pull qwen3:8b

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

### Claude API

```env
ANTHROPIC_API_KEY=sk-ant-...
```

### Ollama

```env
OLLAMA_HOST=http://localhost:11434   # default — change if Ollama runs elsewhere
OLLAMA_MODEL=qwen3:8b               # default model for Portfolio Chat and Rebalance
                                    # (can be changed at runtime in Settings)
```

### Optional

```env
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
2. Create `.env.work` with only the values that differ:

```env
# .env.work
OLLAMA_HOST=http://workstation.local:11434
DB_PATH=data/work.db
```

3. Start the app with `ENV_PROFILE=work`:

```bash
ENV_PROFILE=work streamlit run app.py
```

---

## Demo Mode

Demo mode loads a pre-seeded portfolio database with 20 realistic positions
(stocks, ETFs, precious metals, crypto, a fixed deposit, and a property).
No `ENCRYPTION_KEY` is required in demo mode.

```bash
# Seed the demo database (fetches real historical prices via yfinance)
python scripts/seed_demo.py

# Start in demo mode
DEMO_MODE=true streamlit run app.py
```

To recreate the demo database on a different machine:
```bash
DEMO_DB_PATH=data/demo.db python scripts/seed_demo.py
```

---

## Model Selection at Runtime

After starting the app, go to **Settings → Model Selection** to choose:

- **Ollama model** — list populated live from your local Ollama instance
- **Claude model** — select from Haiku / Sonnet / Opus

Settings are persisted in the database and survive restarts.
The `OLLAMA_MODEL` env var sets the startup default; the Settings UI overrides it.

---

## Ollama Model Recommendations

| Model | Size | Notes |
|---|---|---|
| `qwen3:8b` | 8B | Recommended — good tool use, strong instruction following |
| `llama3.1:8b` | 8B | Good general-purpose alternative |
| `llama3.2` | 2B | Fast, lower quality — for resource-constrained setups |

```bash
ollama pull qwen3:8b
```

---

## Schema Migrations

The database schema is updated automatically on startup. No manual migration steps are needed.
New columns (`empfehlung`, `story`, `skills.hidden`) are added via `migrate_db()` on first run
against an existing database.

---

## Updating

```bash
git pull
pip install -r requirements.txt   # update dependencies if needed
streamlit run app.py              # migration runs automatically on startup
```

---

## Troubleshooting

**App shows "Configuration error: ENCRYPTION_KEY is not set"**
→ Run the generate command shown in the error message and add the key to `.env`.

**Portfolio Chat / Rebalance fails with connection error**
→ Make sure Ollama is running: `ollama serve`
→ Check Settings → System Status for a connectivity check.

**Research / News / Search Chat fails with API error**
→ Check that `ANTHROPIC_API_KEY` is set in `.env`.

**Prices not updating**
→ Click **Refresh Now** on the Market Data page. Check that tickers are valid yfinance symbols.
→ Positions without a ticker (Festgeld, Immobilie, etc.) cannot be auto-priced — this is expected.

**Demo mode not working**
→ Run `python scripts/seed_demo.py` first to create the demo database.

**Watchlist button unavailable for a position type**
→ Asset types without auto-fetch (Festgeld, Anleihe, Immobilie, etc.) are portfolio-only
  and cannot be added to the watchlist — this is by design.
