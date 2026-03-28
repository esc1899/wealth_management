# Architecture

## System Overview

```
┌──────────────────────────────────────────────────────────────┐
│  Streamlit UI  (localhost:8501)                              │
│                                                              │
│  app.py ─── pages/1_Dashboard.py                            │
│         ├── pages/2_Portfolio_Chat.py                       │
│         ├── pages/3_Marktdaten.py                           │
│         └── pages/4_Analyse.py                              │
└────────────────────┬─────────────────────────────────────────┘
                     │ state.py  (@st.cache_resource singletons)
          ┌──────────┴──────────────┐
          │                         │
          ▼                         ▼
  PortfolioAgent            MarketDataAgent
  (Ollama / qwen3:8b)       (APScheduler + yfinance)
          │                         │
          ▼                         ▼
  PortfolioRepository       MarketDataRepository
  WatchlistRepository       (MarketDataFetcher)
          │                         │
          └──────────┬──────────────┘
                     ▼
              SQLite  data/portfolio.db
              (encrypted: portfolio, watchlist)
              (plain:     current_prices, historical_prices)
```

## Runtime Architecture

### Process Model

A single Python process runs both the Streamlit server and the APScheduler background thread:

```
Main Thread (Streamlit):
  - Serves HTTP requests
  - Renders pages on each user interaction
  - Reads from SQLite (via shared connection)

Background Thread (APScheduler):
  - Wakes up daily at 18:00 Europe/Berlin
  - Creates its OWN SQLite connection (thread safety)
  - Calls MarketDataFetcher → yfinance → stores results
  - Thread exits, scheduler sleeps until next trigger
```

### Streamlit Lifecycle

Streamlit re-executes the page script on every user interaction (button click, input, etc.). Shared state is managed via:

- `@st.cache_resource` in `state.py` — creates agents/repos **once** per server process
- `st.session_state` — per-user session state (chat history)

The APScheduler is started inside `get_market_agent()` which is `@st.cache_resource` — guaranteeing it starts exactly once regardless of how many times the page rerenders.

## Agent Architecture

### PortfolioAgent

Handles all portfolio and watchlist CRUD via natural language.

```
User message
    │
    ▼
OllamaProvider.chat_with_tools()  ←── TOOLS list (6 tools)
    │
    ├── tool_calls?
    │     YES → _execute_tool() → Repository
    │              └── summarise result (second LLM call)
    └── NO → return text response
```

**Public API for other agents:**
```python
agent.add_to_watchlist(symbol, name, asset_type, target_price, notes)
# source is automatically set to WatchlistSource.AGENT
```

### MarketDataAgent

Orchestrates price fetching, storage, and scheduling.

```
fetch_all_now()
    │
    ├── _collect_symbols()  ← portfolio entries (deduplicated)
    ├── MarketDataFetcher.fetch_current_prices()
    │       └── validate_symbol() → yf.Ticker.fast_info → EUR conversion
    ├── MarketDataRepository.upsert_price()
    └── (optionally) fetch_historical() → upsert_historical()

get_portfolio_valuation()
    ├── PortfolioRepository.get_all()
    └── MarketDataRepository.get_price(symbol)
            └── PortfolioValuation(pnl_eur, pnl_pct, ...)
```

## Data Model

### Encrypted Tables (portfolio data)

| Table       | Encrypted Fields                    | Reason                          |
|-------------|-------------------------------------|---------------------------------|
| `portfolio` | quantity, purchase_price, notes     | Position size reveals wealth    |
| `watchlist` | notes, target_price                 | Target prices reveal strategy   |

Encryption: Fernet (AES-128-CBC + HMAC-SHA256) via `cryptography` library.
Key derivation: PBKDF2-HMAC-SHA256 with stored salt (`data/salt.bin`).

### Plain Tables (market data)

| Table               | Why unencrypted                               |
|---------------------|-----------------------------------------------|
| `current_prices`    | Public data — encrypting adds no privacy      |
| `historical_prices` | Public data — large volume, no privacy benefit|

### Schema

```sql
-- Encrypted
portfolio (id, symbol, name, quantity*, purchase_price*, purchase_date, asset_type, notes*)
watchlist (id, symbol, name, notes*, target_price*, added_date, source, asset_type)

-- Plain
current_prices (id, symbol UNIQUE, price_eur, currency_original,
                price_original, exchange_rate, fetched_at)
historical_prices (id, symbol, date, close_eur, volume,
                   UNIQUE(symbol, date))
```

## Market Data Fetching

### EUR Conversion

All prices are stored and displayed in EUR. Conversion happens at fetch time:

```
price_eur = price_original × exchange_rate

exchange_rate = EUR per 1 unit of original currency
             = yfinance("{CURRENCY}EUR=X").fast_info.last_price

EUR assets: exchange_rate = 1.0 (no network call)
```

Exchange rates are cached per `MarketDataFetcher` instance (one fetch session = one cache).

### Symbol Validation

Two-layer validation prevents injection and invalid API calls:

1. **Format**: `^[A-Z0-9\-\.\^=]{1,20}$` — blocks shell chars, SQL chars, path traversal
2. **Existence**: If yfinance returns no price or raises → symbol added to `failed` list

Symbols rejected at format validation never reach the network.

### Asset Type Coverage

| Asset Type  | Example Symbols       | Data Source     |
|-------------|----------------------|-----------------|
| Stocks      | AAPL, MSFT, SAP.DE   | yfinance        |
| ETFs        | VWCE.DE, SPY, QQQ    | yfinance        |
| Crypto      | BTC-USD, ETH-EUR     | yfinance        |
| Gold        | GC=F, GLD            | yfinance        |
| Bonds (ETF) | TLT, AGG             | yfinance        |

### Rate Limiting

`RateLimiter` implements a token bucket with a configurable rate (default: 2 req/s).
Set via `.env`: `RATE_LIMIT_RPS=2.0`

## Scheduling

APScheduler `BackgroundScheduler` with `CronTrigger`:

```
Daily at MARKET_DATA_FETCH_HOUR (default: 18:00, Europe/Berlin)
    → MarketDataAgent._scheduled_fetch()
        → creates fresh SQLite connection (thread safety)
        → fetch_all_now(fetch_history=True)
        → closes connection
```

Configure fetch time via `.env`: `MARKET_DATA_FETCH_HOUR=18`

## Security Model

| Concern              | Mitigation                                              |
|----------------------|---------------------------------------------------------|
| Portfolio data at rest | Fernet encryption (AES-128-CBC + HMAC)               |
| Symbol injection      | Regex validation before any yfinance/network call      |
| yfinance rate limits  | Token bucket rate limiter (2 req/s default)            |
| Thread safety (SQLite)| Scheduler creates own connection; no shared write conn |
| Sensitive data in logs| Portfolio values never logged                          |
| External API surface  | yfinance only; no API keys stored                      |
| LLM prompt injection  | Symbols from LLM pass through validate_symbol()        |

## Adding a New Asset Type

1. Add value to `AssetType` enum in `core/storage/models.py`
2. Add to `TOOLS` schema in `agents/portfolio_agent.py`
3. If the asset uses a non-standard yfinance symbol format:
   - Update `SYMBOL_PATTERN` in `agents/market_data_fetcher.py` if needed
   - Add currency handling in `_detect_currency()` if needed
4. Add test cases to `tests/unit/test_market_data_fetcher.py`

## Technology Stack

| Component     | Library/Tool          | Version  |
|---------------|-----------------------|----------|
| UI            | Streamlit             | ≥1.50    |
| Charts        | Plotly                | ≥5.0     |
| LLM (local)   | Ollama + qwen3:8b     | —        |
| LLM (cloud)   | Anthropic Claude      | ≥0.40    |
| Market data   | yfinance              | ≥0.2     |
| Scheduling    | APScheduler           | ≥3.10    |
| Storage       | SQLite (built-in)     | —        |
| Encryption    | cryptography (Fernet) | ≥42.0    |
| Monitoring    | Langfuse              | ≥3.0     |
| Monitoring DB | ClickHouse + Postgres | —        |
| Models        | Pydantic v2           | ≥2.0     |
| Tests         | pytest + pytest-asyncio| ≥8.0    |

## Infrastructure (Docker)

Langfuse v3 erfordert mehrere Services — alle lokal via `docker-compose.yml`:

```
docker compose up -d

Services:
  langfuse    :3000   — Web UI + API
  postgres    :5432   — Langfuse Metadaten
  clickhouse  :8123   — Traces + Generations (Langfuse v3 Pflicht)
  redis       :6379   — Queue / Cache
  minio       :9001   — S3-kompatibler Event Storage (Langfuse v3 Pflicht)
  minio-init          — Erstellt den langfuse-Bucket beim ersten Start
```

**Hinweis:** Langfuse v2 benötigt nur Postgres. v3 erfordert zusätzlich ClickHouse, Redis und MinIO.

## Known Issues & Fixes

| Problem | Fix |
|---------|-----|
| `SQLite objects created in a thread can only be used in that same thread` | `check_same_thread=False` in `get_connection()` |
| ClickHouse Healthcheck schlägt fehl | `clickhouse-client` statt `wget`/`curl` (nicht im Image vorhanden) |
| Python 3.9: `match/case` nicht verfügbar | `if/elif` statt `match` in allen Agents |
| Langfuse v3: `CLICKHOUSE_URL is not configured` | docker-compose.yml um ClickHouse + Redis + MinIO erweitern |

## Hardware

Entwicklung und Betrieb auf **Mac Mini M4, 16 GB Unified Memory, arm64**.
Ollama nutzt die Neural Engine des M4 — alle Inferenzen bleiben lokal.
