# Architecture

Stand: 2026-04-02

## System Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Streamlit UI  (localhost:8501)                                           │
│                                                                           │
│  app.py ─── pages/dashboard.py         (Portfolio overview)              │
│         ├── pages/positionen.py        (CRUD, detail dialog, no LLM)    │
│         ├── pages/marktdaten.py        (MarketDataAgent — yfinance)      │
│         ├── pages/analyse.py           (P&L, day chart, allocation)      │
│         ├── pages/portfolio_chat.py    (PortfolioAgent — Ollama 🔒)      │
│         ├── pages/rebalance_chat.py    (RebalanceAgent — Ollama 🔒)      │
│         ├── pages/research_chat.py     (ResearchAgent — Claude ☁️)       │
│         ├── pages/news_chat.py         (NewsAgent — Claude ☁️)           │
│         ├── pages/search_chat.py       (SearchAgent — Claude ☁️)         │
│         ├── pages/storychecker.py      (StorycheckerAgent — Claude ☁️)   │
│         ├── pages/fundamental.py       (FundamentalAgent — Claude ☁️)    │
│         ├── pages/structural_scan.py   (StructuralChangeAgent — Claude ☁️)│
│         ├── pages/consensus_gap.py     (ConsensusGapAgent — Claude ☁️)   │
│         ├── pages/settings.py          (Skills, models, scheduling)      │
│         └── pages/statistics.py        (Token usage per agent)           │
└──────────────────────┬───────────────────────────────────────────────────┘
                       │ state.py  (@st.cache_resource singletons)
          ┌────────────┴──────────────────────────────┐
          │                                             │
          ▼                                             ▼
  Local Agents (Ollama 🔒)               Cloud Agents (Claude ☁️)
  PortfolioAgent                          ResearchAgent       (Haiku)
  RebalanceAgent                          NewsAgent           (Haiku)
          │                               StorycheckerAgent   (Haiku)
          ▼                               SearchAgent         (Sonnet)
  OllamaProvider                          ConsensusGapAgent   (Sonnet)
          │                               FundamentalAgent    (Sonnet)
          │                               StructuralChangeAgent (Sonnet)
          │                                             │
          └──────────────────────────────┐              │
                                         ▼              ▼
                                  PositionsRepository
                                  MarketDataRepository
                                  SkillsRepository
                                  AppConfigRepository
                                  UsageRepository
                                  PositionAnalysesRepository
                                  StorycheckerRepository
                                  StructuralScansRepository
                                  ScheduledJobsRepository
                                         │
                                         ▼
                                  SQLite  data/portfolio.db
                                  (encrypted: positions.quantity, purchase_price,
                                              notes, extra_data, story)
                                  (plain: current_prices, historical_prices,
                                          skills, app_config, llm_usage,
                                          position_analyses, structural_scan_runs,
                                          scheduled_jobs, ...)
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

### StorycheckerAgent

Validates investment theses ("Stories") against current facts. Stateful — persists conversation sessions and the final verdict in `position_analyses` (agent=`storychecker`). Verdict values: `intact` / `gemischt` / `gefaehrdet`. Verdicts appear as badges in the positions list and feed into the Rebalance context.

### StructuralChangeAgent

Agentic loop — Claude decides autonomously when to search and when to add candidates:

```
start_scan()
    │
    ▼
_run_agentic_loop()  (max 20 iterations)
    │
    ├── chat_with_tools([web_search, add_structural_candidate])
    │
    ├── web_search results? → Anthropic handles server-side, response continues
    │
    └── add_structural_candidate? → _tool_add_candidate()
              └── PositionsRepository.add() → Position in watchlist
                  with story = "[Struktureller Wandel] {theme}\n\n{thesis}"

    loop ends when stop_reason == "end_turn" or no tool calls
    └── save_run() + add_message() → StructuralScansRepository
```

**Important:** Requires Claude Sonnet+. Claude Haiku does not execute `web_search_20250305` server-side — the tool call appears as a client-side call, breaking the loop silently.

### ConsensusGapAgent / FundamentalAgent

Single-call agents (not agentic loop). Claude uses `web_search` server-side to research each position, then outputs a structured block per position.

```
analyze_portfolio(positions, skill_name, skill_prompt, analyses_repo)
    │
    ├── filter eligible (consensus_gap: has story; fundamental: has ticker)
    ├── batch positions (2 or 1 per call)
    ├── chat_with_tools([web_search]) → structured verdict blocks
    ├── _parse_verdicts() → regex parse POSITION/VERDICT/SUMMARY/ANALYSIS
    └── analyses_repo.save(position_id, agent, verdict, summary)
```

Verdict values:
- ConsensusGap: `wächst` / `stabil` / `schließt` / `eingeholt`
- Fundamental: `unterbewertet` / `fair` / `überbewertet` / `unbekannt`

### Cloud Agents (ResearchAgent, NewsAgent, SearchAgent, StorycheckerAgent)

All use `ClaudeProvider` with `on_usage` callback → `UsageRepository`.
Token usage is tracked per agent and displayed on the Statistics page (total, daily trend, avg per call).

### AgentSchedulerService

APScheduler `BackgroundScheduler` in a daemon thread. Each job execution:
1. Creates its own SQLite connection (thread safety — no shared write connection)
2. Calls the appropriate agent's `analyze_portfolio()` or `run()` method
3. Updates `scheduled_jobs.last_run`

Configurable via Settings: agent, skill, frequency (daily/weekly/monthly), time, model override.

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

Used for: `model_ollama`, `model_claude`, `model_claude_{agent_key}` (per-agent override), `empfehlung_labels`.

### `position_analyses` Table

Agent-agnostic verdict store — reused by Storychecker, ConsensusGap, and Fundamental:

```sql
CREATE TABLE position_analyses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id INTEGER NOT NULL,
    agent       TEXT NOT NULL,      -- 'storychecker' | 'consensus_gap' | 'fundamental'
    skill_name  TEXT NOT NULL,
    verdict     TEXT,               -- agent-specific value
    summary     TEXT,               -- one-sentence summary (shown in UI)
    created_at  TEXT NOT NULL
);
```

`get_latest_bulk(ids, agent)` always returns the newest entry per position — older runs accumulate but never overwrite.

### Other Tables (plaintext)

| Table | Purpose |
|---|---|
| `current_prices` | Latest price per ticker symbol |
| `historical_prices` | Daily closing prices (1y history) |
| `research_sessions` / `research_messages` | Research Chat sessions |
| `rebalance_sessions` / `rebalance_messages` | Rebalance sessions |
| `news_runs` / `news_messages` | News Digest runs |
| `search_sessions` / `search_messages` | Investment Search sessions |
| `storychecker_sessions` / `storychecker_messages` | Story Checker sessions |
| `structural_scan_runs` / `structural_scan_messages` | Structural Change scan history |
| `position_analyses` | Agent verdicts (storychecker, consensus_gap, fundamental) |
| `scheduled_jobs` | APScheduler job definitions |
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

Ollama and Claude models are selectable per agent at runtime in Settings → Model Selection.

- Available Ollama models are fetched live from `/api/tags`
- Claude models come from the `CLAUDE_MODELS` env var (comma-separated, default: all three)
- Global fallback chain: `model_{type}_{agent_key}` → `model_{type}` → hardcoded default
- Selections are persisted in `app_config`
- `st.cache_resource.clear()` is called on save to force agent recreation with new model

**Model requirements:**
| Agent | Minimum | Reason |
|---|---|---|
| Portfolio Chat, Rebalance | any Ollama | Local only |
| Research, News, Storychecker | Haiku+ | No web search needed |
| Search, Structural, ConsensusGap, Fundamental | **Sonnet+** | Requires server-side `web_search_20250305` |

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
