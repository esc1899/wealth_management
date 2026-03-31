# Architecture

Stand: 2026-03-31

## System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│  Streamlit UI  (localhost:8501)                                       │
│                                                                       │
│  app.py ─── pages/dashboard.py        (Portfolio overview, Easter Egg)│
│         ├── pages/positionen.py       (CRUD, detail dialog, no LLM)  │
│         ├── pages/portfolio_chat.py   (PortfolioAgent — Ollama 🔒)   │
│         ├── pages/market_data.py      (MarketDataAgent — yfinance)    │
│         ├── pages/analysis.py         (P&L, allocation charts)       │
│         ├── pages/rebalance_chat.py   (RebalanceAgent — Ollama 🔒)   │
│         ├── pages/research_chat.py    (ResearchAgent — Claude ☁️)    │
│         ├── pages/news_chat.py        (NewsAgent — Claude ☁️)        │
│         ├── pages/search_chat.py      (SearchAgent — Claude ☁️)      │
│         ├── pages/settings.py         (Skills, models, labels)       │
│         └── pages/statistics.py       (Token usage)                  │
└────────────────────┬─────────────────────────────────────────────────┘
                     │ state.py  (@st.cache_resource singletons)
          ┌──────────┴───────────────────────────┐
          │                                       │
          ▼                                       ▼
  Local Agents (Ollama 🔒)             Cloud Agents (Claude ☁️)
  PortfolioAgent                        ResearchAgent
  RebalanceAgent                        NewsAgent
          │                             SearchAgent
          ▼                                       │
  OllamaProvider                        ClaudeProvider
          │                                       │
          └──────────────────────────┐            │
                                     ▼            ▼
                              PositionsRepository
                              MarketDataRepository
                              SkillsRepository
                              AppConfigRepository
                              UsageRepository
                                     │
                                     ▼
                              SQLite  data/portfolio.db
                              (encrypted: positions.quantity, purchase_price,
                                          notes, extra_data, story)
                              (plain: current_prices, historical_prices,
                                       skills, app_config, llm_usage, ...)
```

## Runtime Architecture

### Process Model

A single Python process runs both the Streamlit server and the APScheduler background thread:

```
Main Thread (Streamlit):
  - Serves HTTP requests
  - Renders pages on each user interaction
  - Reads from SQLite (shared connection, check_same_thread=False)

Background Thread (APScheduler):
  - Wakes up daily at MARKET_DATA_FETCH_HOUR (default 18:00 Europe/Berlin)
  - Creates its OWN SQLite connection (thread safety)
  - Calls MarketDataFetcher → yfinance → stores results
  - Thread exits, scheduler sleeps until next trigger
```

### Streamlit Lifecycle

Streamlit re-executes the page script on every user interaction. Shared state is managed via:

- `@st.cache_resource` in `state.py` — creates agents/repos **once** per server process
- `st.session_state` — per-user session state (chat history, form state)
- `@st.dialog` — modal dialogs (detail view, Easter egg) defined at module level

The APScheduler is started inside `get_market_agent()` which is `@st.cache_resource` — guaranteeing it starts exactly once.

## Agent Architecture

### PortfolioAgent

Natural-language CRUD for portfolio and watchlist via local Ollama.

```
User message
    │
    ▼
OllamaProvider.chat_with_tools()  ←── TOOLS (8 tools)
    │                             ←── SYSTEM_PROMPT + hidden system skills
    ├── tool_calls?
    │     YES → _execute_tool() → PositionsRepository
    │              └── summarise result (second LLM call, no tools)
    └── NO → return text response
```

**Tools:** `add_portfolio_entry`, `remove_portfolio_entry`, `list_portfolio`,
`add_to_watchlist`, `remove_from_watchlist`, `list_watchlist`,
`clear_portfolio`, `clear_watchlist`

**Hidden system skills:** Injected silently from `SkillsRepository.get_system_skills()`.
The "Datenpflege-Assistent" skill provides structured rules for all 11 asset types,
ticker lookup logic, and date estimation from historical prices.

### MarketDataAgent

Orchestrates price fetching and portfolio valuation.

```
fetch_all_now()
    │
    ├── filter positions to auto_fetch asset classes only
    ├── MarketDataFetcher.fetch_current_prices()  (rate-limited)
    │       └── yf.Ticker.fast_info → EUR conversion → upsert
    └── (optionally) fetch_historical() → upsert_historical()

get_portfolio_valuation()
    ├── PositionsRepository.get_portfolio()
    ├── for auto_fetch positions → MarketDataRepository.get_price(ticker)
    └── for manual positions (Immobilie, Grundstück, Festgeld, ...)
            → extra_data.estimated_value  OR  purchase_price × quantity
```

### Cloud Agents (ResearchAgent, NewsAgent, SearchAgent)

All use `ClaudeProvider` with `on_usage` callback → `UsageRepository`.
Token usage is tracked and displayed on the Statistics page.

## Data Model

### `positions` Table

```sql
CREATE TABLE positions (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Classification (plaintext)
    asset_class           TEXT NOT NULL,   -- from YAML: "Aktie", "Festgeld", "Immobilie", ...
    investment_type       TEXT NOT NULL,   -- derived: "Wertpapiere", "Geld", "Immobilien", ...
    -- Identifiers (plaintext)
    name                  TEXT NOT NULL,
    isin                  TEXT,
    wkn                   TEXT,
    ticker                TEXT,            -- NULL for manual types (Festgeld, Immobilie, ...)
    -- Financials (ENCRYPTED)
    quantity              TEXT,            -- Fernet; NULL for Grundstück, watchlist entries
    unit                  TEXT NOT NULL,   -- "Stück", "Troy Oz", "g"
    purchase_price        TEXT,            -- Fernet; optional
    purchase_date         TEXT,            -- ISO-8601; optional
    -- Metadata (ENCRYPTED)
    notes                 TEXT,            -- Fernet
    extra_data            TEXT,            -- Fernet over JSON: estimated_value, interest_rate, ...
    story                 TEXT,            -- Fernet; investment thesis
    -- Provenance (plaintext)
    recommendation_source TEXT,
    strategy              TEXT,
    empfehlung            TEXT,            -- recommendation label: "Kaufen", "Halten", ...
    added_date            TEXT NOT NULL,
    -- State (plaintext)
    in_portfolio          INTEGER NOT NULL DEFAULT 0  -- 0=watchlist, 1=portfolio
);
```

**Encrypted fields:** `quantity`, `purchase_price`, `notes`, `extra_data`, `story`

### `skills` Table

```sql
CREATE TABLE skills (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    area        TEXT NOT NULL,
    description TEXT,
    prompt      TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    hidden      INTEGER NOT NULL DEFAULT 0,  -- 1 = system skill, injected silently
    UNIQUE(name, area)
);
```

System skills (`hidden=1`) are seeded at startup from `config/default_skills.yaml` and
injected into the PortfolioAgent system prompt. They are never shown in the Settings UI.

### `app_config` Table

```sql
CREATE TABLE app_config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL  -- plain string or JSON
);
```

Used for: `model_ollama`, `model_claude`, `empfehlung_labels`.

### Other Tables (plaintext)

| Table | Purpose |
|---|---|
| `current_prices` | Latest price per ticker symbol |
| `historical_prices` | Daily closing prices (1y history) |
| `research_sessions` / `research_messages` | Research Chat sessions |
| `rebalance_sessions` / `rebalance_messages` | Rebalance sessions |
| `news_runs` / `news_messages` | News Digest runs |
| `search_sessions` / `search_messages` | Investment Search sessions |
| `llm_usage` | Token usage per agent and model |

## Asset Class Configuration

Defined in `config/asset_classes.yaml`. No code change needed to add a type.

### Flags

| Flag | Purpose |
|---|---|
| `auto_fetch: true` | Price fetched automatically via yfinance (requires ticker) |
| `auto_fetch: false` | No price fetch; value from `extra_data.estimated_value` or `purchase_price` |
| `watchlist_eligible: true` | Position can be added to the watchlist |
| `watchlist_eligible: false` | Portfolio-only (Festgeld, Immobilien, etc.) |
| `manual_valuation: true` | "Update Estimated Value" shown in detail dialog |
| `extra_fields: [...]` | Type-specific fields stored in encrypted `extra_data` JSON |

### Current Asset Classes

| Class | Type | auto_fetch | watchlist | manual_valuation | extra_fields |
|---|---|---|---|---|---|
| Aktie | Wertpapiere | ✓ | ✓ | — | — |
| Aktienfonds | Wertpapiere | ✓ | ✓ | — | — |
| Rentenfonds | Renten | ✓ | ✓ | — | — |
| Immobilienfonds | Immobilien | ✓ | ✓ | — | — |
| Edelmetall | Edelmetalle | ✓ | ✓ | — | — |
| Kryptowährung | Krypto | ✓ | ✓ | — | — |
| Anleihe | Renten | — | — | — | — |
| Festgeld | Geld | — | — | — | interest_rate, maturity_date, bank |
| Bargeld | Geld | — | — | — | — |
| Immobilie | Immobilien | — | — | ✓ | estimated_value, valuation_date |
| Grundstück | Immobilien | — | — | ✓ | estimated_value, valuation_date |

### Adding a New Asset Type

1. Add an entry to `config/asset_classes.yaml`
2. Run `migrate_db()` to add any required columns (handled at startup automatically)
3. No code change required for basic types

## Model Selection

Ollama and Claude models are selectable at runtime in Settings → Model Selection.

- Available Ollama models are fetched live from `/api/tags`
- Claude model is selected from a static list (`haiku-4-5`, `sonnet-4-6`, `opus-4-6`)
- Selections are persisted in `app_config` (`model_ollama`, `model_claude`)
- Agent factories in `state.py` are parameterized with model string as `@st.cache_resource` key

## Schema Migrations

`migrate_db(conn)` in `core/storage/base.py` applies `ALTER TABLE` migrations idempotently using
`PRAGMA table_info` checks. Called at startup from `state.py`. Current migrations:

- `positions.empfehlung TEXT`
- `positions.story TEXT`
- `skills.hidden INTEGER NOT NULL DEFAULT 0`

New installations get these columns directly from `init_db()`. Existing DBs get them via migration.

## Security Model

| Concern | Mitigation |
|---|---|
| Portfolio data at rest | Fernet encryption (AES-128-CBC + HMAC) |
| Investment thesis (story) | Encrypted at rest alongside financials |
| Symbol injection | Regex validation before any yfinance/network call |
| yfinance rate limits | Token bucket rate limiter (2 req/s default) |
| Thread safety (SQLite) | Scheduler creates own connection; no shared write conn |
| External API surface | yfinance only for market data; no API keys |
| LLM prompt injection | Symbols from LLM pass through validate_symbol() |
| Demo mode | PassthroughEncryptionService (identity function) — no key required |

## Market Data — EUR Conversion

```
price_eur = price_original / exchange_rate_EURUSD

EUR assets:  exchange_rate = 1.0  (no network call)
USD assets:  EURUSD=X via yfinance
GBP assets:  GBPUSD=X → USD → EUR
CHF assets:  CHFUSD=X → USD → EUR
```

Precious metals in grams: `price_eur_per_g = price_eur_per_troy_oz / 31.1035`

## Technology Stack

| Component | Library/Tool | Version |
|---|---|---|
| UI | Streamlit | ≥1.50 |
| Charts | Plotly | ≥5.0 |
| LLM (local) | Ollama | any model |
| LLM (cloud) | Anthropic Claude | ≥0.40 |
| Market data | yfinance | ≥0.2 |
| Scheduling | APScheduler | ≥3.10 |
| Storage | SQLite (built-in) | — |
| Encryption | cryptography (Fernet) | ≥42.0 |
| Monitoring | Langfuse | ≥3.0 (optional) |
| Models | Pydantic v2 | ≥2.0 |
| YAML config | PyYAML | — |
| Tests | pytest + pytest-asyncio | ≥8.0 |

## Hardware

Developed and operated on **Mac Mini M4, 16 GB Unified Memory, arm64**.
Ollama uses the M4 Neural Engine — all local inference stays on-device.

## Langfuse Infrastructure (Optional)

Langfuse v3 requires multiple services via `docker-compose.yml`:

```
docker compose up -d

Services:
  langfuse    :3000   — Web UI + API
  postgres    :5432   — Langfuse metadata
  clickhouse  :8123   — Traces and generations (v3 required)
  redis       :6379   — Queue / cache
  minio       :9001   — S3-compatible event storage (v3 required)
  minio-init          — Creates the langfuse bucket on first start
```

Omit all `LANGFUSE_*` env vars to disable monitoring entirely.
