# Architecture Overview

## High Level

```
Streamlit UI (Multi-page)
  ↓
Pages (14)
  ├─ Dashboard, Positionen, Marktdaten, Analyse (Portfolio management)
  ├─ Portfolio Chat, Rebalance Chat (Local Ollama 🔒)
  ├─ Research Chat, News, Search, Story Checker (Cloud Claude ☁️)
  └─ Structural Scan, Consensus Gap, Fundamental Value (Claude Strategy)
  ↓
Agents (10)
  ├─ Local (Ollama): PortfolioAgent, RebalanceAgent, MarketDataAgent
  └─ Cloud (Claude): ResearchAgent, NewsAgent, SearchAgent, StorycheckerAgent,
                     StructuralChangeAgent, ConsensusGapAgent, FundamentalAgent
  ↓
Storage (SQLite, encrypted)
  └─ Repositories: Positions, MarketData, Research, News, Search, Skills,
                   Rebalance, Analyses, StructuralScans, WealthSnapshots, etc.
```

---

## Core Modules

### `config.py`
- Environment variable loading (.env, profile overrides)
- Settings: ENCRYPTION_KEY, ANTHROPIC_API_KEY, OLLAMA_HOST, OLLAMA_MODEL, LOG_LEVEL, BASE_CURRENCY, DEMO_MODE, etc.

### `core/currency.py` (NEW)
- Display-only currency flexibility
- Functions: `symbol()`, `fmt(value, decimals)`, `is_cash_unit(unit)`
- Supports: EUR, CHF, GBP, USD, JPY
- Internal DB remains EUR; display configurable

### `core/i18n.py`
- Translation via `t(key)` function
- YAML-based (translations/de.yaml, en.yaml)
- Per-session language switching

### `core/llm/`
- **OllamaProvider**: Ollama HTTP client (local, private 🔒)
- **ClaudeProvider**: Anthropic API client (cloud, cost-tracked ☁️)
- Tracking: `on_usage` callback → token counts to UsageRepository

### `core/storage/`
High-level: One repository per entity. Each wraps SQLite + encryption.

| Repo | Purpose | Persistence |
|---|---|---|
| **PositionsRepository** | CRUD for portfolio + watchlist | positions table |
| **MarketDataRepository** | Current prices + history | market_data, price_history |
| **SkillsRepository** | Prompt templates per agent area | skills, INSERT OR IGNORE on seed |
| **AppConfigRepository** | User settings (models, cost alerts) | app_config |
| **RebalanceRepository** | Session chat history | rebalance_sessions, rebalance_messages |
| **ResearchRepository** | Research chat sessions | research_sessions, research_messages |
| **SearchRepository** | Investment search sessions | search_sessions, search_messages |
| **StorycheckerRepository** | Story validation sessions | storychecker_sessions, storychecker_messages |
| **PositionAnalysesRepository** | Verdicts from 3 agents (storychecker/consensus_gap/fundamental) | position_analyses (agent field) |
| **StructuralScansRepository** | Structural change scan runs | structural_scan_runs, structural_scan_messages |
| **WealthSnapshotRepository** | Historical portfolio snapshots | wealth_snapshots |
| **ScheduledJobsRepository** | Periodic agent runs | scheduled_jobs |
| **NewsRepository** | News digest caching | news_digests |
| **UsageRepository** | Token counts + costs per call | usage_log |

### `core/scheduler.py`
- **AgentSchedulerService**: Background scheduler for periodic cloud agent runs
- Thread-safe: separate DB connection per job
- Configurable: daily/weekly/monthly with cron syntax
- Supported agents: news, structural_scan, consensus_gap

---

## Agents (10 total)

### Local (Private 🔒, Ollama)

#### PortfolioAgent
- **Purpose**: Natural language portfolio CRUD
- **Input**: User text ("Add 10 Apple at €150")
- **Tools**: `add_portfolio`, `get_positions`, `update_position`, `delete_position`
- **Storage**: None (stateless, tools hit repos directly)

#### RebalanceAgent
- **Purpose**: Portfolio rebalancing analysis using Josef's Rule (1/3 Aktien / 1/3 Renten+Geld / 1/3 Rohstoffe)
- **Input**: Selected skill + optional user context
- **Session**: rebalance_sessions (portfolio snapshot + skill stored)
- **Context**: Handelbares + Nicht-handelbares Vermögen, Cloud verdicts (fundamental/consensus_gap), Kaufkandidaten (Watchlist)
- **Output**: Rebalancing recommendations + chat history
- **Storage**: RebalanceRepository (sessions + messages)

#### MarketDataAgent
- **Purpose**: Fetch and store current prices + historical data
- **Data Source**: yfinance (auto-converted to EUR)
- **Scheduler**: APScheduler (daily at configured hour)
- **Special**: Handles dividends (fetched or estimated for Festgeld/Anleihen)
- **Storage**: MarketDataRepository (prices + history)

---

### Cloud (Intelligent, Claude API ☁️)

#### ResearchAgent
- **Purpose**: Deep research per position
- **Model**: Claude Haiku (cheaper, sufficient for no-search research)
- **Session**: research_sessions
- **Storage**: ResearchRepository

#### NewsAgent
- **Purpose**: News digest for portfolio positions
- **Model**: Claude Haiku
- **Stateless**: No session, one-shot digest
- **Storage**: None (or optional cache in NewsRepository)

#### SearchAgent
- **Purpose**: Investment opportunity screening
- **Model**: Claude Sonnet (requires web_search)
- **Tools**: `add_to_watchlist`
- **Session**: search_sessions
- **Storage**: SearchRepository

#### StorycheckerAgent
- **Purpose**: Validate investment theses against news
- **Model**: Claude Haiku
- **Method**: Regex parsing of verdicts from response
- **Verdicts**: `intact` (✅), `gemischt` (⚠️), `gefaehrdet` (🔴)
- **Batch Mode**: `batch_check_all()` checks all positions with stories
- **Storage**: PositionAnalysesRepository (agent='storychecker')

#### StructuralChangeAgent
- **Purpose**: Identify irreversible market shifts
- **Model**: Claude Sonnet (requires web_search)
- **Tools**: `add_structural_candidate` (direct watchlist write)
- **Agentic Loop**: Claude decides when to search + call tool
- **Session**: StructuralScansRepository (messages stored)
- **Storage**: StructuralScansRepository

#### ConsensusGapAgent
- **Purpose**: Measure gap between personal thesis and market consensus
- **Model**: Claude Sonnet (requires web_search)
- **Method**: Tool-use calling `submit_verdict(position_id, verdict, summary, analysis)`
- **Verdicts**: `wächst` 🟢 (gap widening), `stabil` 🟡, `schließt` 🔴, `eingeholt` ⚫
- **Batch Mode**: `analyze_portfolio()` checks all positions
- **Storage**: PositionAnalysesRepository (agent='consensus_gap')

#### FundamentalAgent
- **Purpose**: Fair value estimation (P/E, P/B, EV/EBITDA, DCF, PEG)
- **Model**: Claude Sonnet (requires web_search)
- **Method**: Regex parsing of verdicts (Fair Value: X €, Verdict: unterbewertet/fair/überbewertet/unbekannt)
- **Batch Mode**: `analyze_portfolio()` checks all positions
- **Storage**: PositionAnalysesRepository (agent='fundamental')

---

## Data Model Highlights

### Position
- `id, ticker, name, asset_class, investment_type, quantity, unit, purchase_price, purchase_date`
- `in_portfolio, in_watchlist, rebalance_excluded`
- `story` (investment thesis), `recommendation_source`, `anlageart` (sub-type)
- `extra_data` (JSON, encrypted): `estimated_value, valuation_date` (for manual valuations), `interest_rate` (for bonds/fixed deposits), `dividend_yield_override`, etc.

### Asset Class (from config/asset_classes.yaml)
- `name` (Aktie, Aktienfonds, Rentenfonds, Immobilie, Festgeld, Bargeld, etc.)
- `investment_type` (Wertpapiere, Renten, Immobilien, Geld, Edelmetalle, Krypto)
- `auto_fetch` (fetch via yfinance)
- `watchlist_eligible` (can be in watchlist)
- `manual_valuation` (show "Schätzwert aktualisieren" button)
- `anlagearten` (sub-types, e.g., "ETF", "Einzelaktie")

### Josef's Rule
**Target**: 1/3 each
- **Aktien**: investment_type=Wertpapiere
- **Renten/Geld**: investment_type ∈ {Renten, Geld}
- **Rohstoffe+Immobilien**: investment_type ∈ {Edelmetalle, Krypto, Immobilien}

Mapping in `agents/rebalance_agent.py`:
```python
_JOSEF_CATEGORY = {
    "Wertpapiere": "Aktien",
    "Renten": "Renten/Geld",
    "Geld": "Renten/Geld",
    "Edelmetalle": "Rohstoffe",
    "Krypto": "Rohstoffe",
    "Immobilien": "Rohstoffe",  # ← Fixed in Commit 19abc12
}
```

### position_analyses (agent-agnostisch)
Shared table for 3 agents; `agent` field distinguishes:
- `storychecker`: verdict ∈ {intact, gemischt, gefaehrdet}
- `consensus_gap`: verdict ∈ {wächst, stabil, schließt, eingeholt}
- `fundamental`: verdict ∈ {unterbewertet, fair, überbewertet, unbekannt}

`get_latest_bulk(position_ids, agent)` → always returns newest analysis per position.

---

## Key Patterns

### Session-Based Chat
Used by: RebalanceAgent, ResearchAgent, SearchAgent, StorycheckerAgent, StructuralChangeAgent

```python
# Start
session = agent.start_session(skill_key, optional_context)
# Persist to repo, return session ID

# Chat
response = agent.chat(session_id, user_message)
# Append to messages table, return assistant response
```

### Batch Processing (Background Thread)
Used by: ConsensusGapAgent, FundamentalAgent, StorycheckerAgent

```python
# Session-State Bridge
job = BatchJob(...)
st.session_state["_analysis_job"] = job

# Background Thread
def run():
    agent.analyze_portfolio(...)
    job.mark_done()

threading.Thread(daemon=True, target=run).start()

# Polling
while job.is_running():
    time.sleep(5)
    st.rerun()
```

### Tool-Use (Deterministic Parsing)
Only **ConsensusGapAgent** currently uses tool-use:
```python
# Claude calls: submit_verdict(position_id, verdict, summary, analysis)
# vs. regex parsing: "POSITION: 3\nVERDICT: [wächst]\n..."
```

**Candidates for Tool-Use migration**: StorycheckerAgent, FundamentalAgent (stable with regex, not urgent).

### Lazy Agent Initialization
Startup loads only:
- `get_portfolio_agent()` (portfolio chat)
- `get_market_agent()` (price fetching)
- `get_agent_scheduler()` (background jobs)

All other agents are lazy-loaded via `@st.cache_resource` when pages access them.

---

## Configuration Files

### `config/default_skills.yaml`
Skill templates for all agent areas. Seeded on startup via `SkillsRepository.seed_if_empty()`.

Format per area:
```yaml
skills:
  portfolio:
    - name: "Precision"
      description: "..."
      system_prompt: "..."
    - name: "Explanatory"
      ...
```

**System Skills** (hidden from UI, never user-editable):
- `rebalance.josef_rule` — 1/3 allocation hint
- `rebalance.cash_split` — handelbares vs. nicht-handelbares distinction

### `config/asset_classes.yaml`
12 asset classes with metadata. No DB migration needed; read on startup.

---

## Storage & Encryption

### SQLite + Cryptography/Fernet
- **Prod**: Full encryption (EncryptionService)
- **Demo**: Plaintext (PassthroughEncryptionService) for ease of inspection

Encrypted fields: position `name`, `notes`, `story`, `recommendation_source`, `extra_data` (JSON).

### Migrations
Auto-run on startup via `migrate_db(conn)` → adds new columns, indices, etc. without data loss.

---

## Currency System (April 2026)

### Display-Only Approach
- **Config**: `BASE_CURRENCY` env var (default: EUR)
- **Supported**: EUR, CHF, GBP, USD, JPY
- **Internal**: All DB fields `_eur` remain in EUR; no schema change
- **Display**: Pages use `core.currency.symbol()` and `core.currency.fmt()`
- **Agents**: LLM output includes currency symbol from `symbol()` function

### Usage
```bash
BASE_CURRENCY=EUR streamlit run app.py  # € 1.234,56
BASE_CURRENCY=CHF streamlit run app.py  # Fr. 1.234,56
BASE_CURRENCY=GBP streamlit run app.py  # £ 1.234,56
```

---

## Testing

### Test Strategy
- **Unit tests**: Agent logic, repository CRUD, parsing (526 tests total)
- **Integration tests**: Full workflows with real SQLite (`:memory:`)
- **No mocking of repositories**: Always use real storage (more representative)

### Running Tests
```bash
pytest tests/                 # All
pytest tests/unit/            # Unit only
pytest tests/integration/     # Integration only
pytest -k consensus_gap       # Specific agent
```

---

## Logging

### Setup (April 2026)
- Root logger configured in `app.py` on startup
- All agents + core modules import `logging.getLogger(__name__)`
- **Log Level**: `LOG_LEVEL` env var (default: INFO)

```bash
LOG_LEVEL=DEBUG streamlit run app.py  # Verbose
LOG_LEVEL=ERROR streamlit run app.py  # Errors only
```

---

## Known Limitations & Workarounds

### web_search_20250305 (Tool)
- **Only Sonnet+**: Haiku treats it as client-side tool → agentic loop would fail
- **Workaround**: Use Claude Sonnet (or better) for Structural Change, Consensus Gap, Fundamental agents
- **Cost**: ~2-3x higher than Haiku for web-search agents

### Streamlit @st.cache_resource
- **Caching Issue**: After code changes, full restart required (`Ctrl+C`, rerun `streamlit run app.py`)
- **Why**: Cached resources (agents, repos) won't be recreated until cache clears
- **Mitigation**: Documented in system instructions for users

### ClaudeToolCall / ClaudeResponse
- **Attribute names**: `.input` (not `.arguments`), `.raw_blocks` (not `.raw_content`)
- **Context**: SDK difference from older versions

---

## Deployment

### Self-Hosted Only
- No SaaS offering
- Users control encryption keys, API keys, database
- Commercial use requires separate license (see LICENSE, README)

### Recommended Stack
- Python 3.9+
- SQLite (local or on NAS)
- Ollama (local or remote) for portfolio/rebalance
- Anthropic API key for cloud research agents
- Optional: Langfuse for monitoring

---

## Future Improvements (Not Blocking)

- **Tool-Use for StorycheckerAgent / FundamentalAgent**: Currently stable with regex; tool-use would be cleaner (6-8h effort)
- **Multi-Currency Positions**: Allow holding assets in foreign currencies (would require schema changes)
- **Automatic Kursumrechnung**: Auto-convert prices when BASE_CURRENCY ≠ EUR (requires daily exchange rates)
- **Dependency Injection Refactoring**: `@st.cache_resource` works but is Streamlit-specific
- **Lazy Skill Loading**: Seeds all skills on startup; could lazy-load per agent

---

## Architectural Decisions (Portfolio Story Subsystem)

### Story-Primacy for Position Alignment
**Decision**: For existing positions, Portfolio-Story alignment is the PRIMARY evaluation dimension. Fundamental analysis & Consensus-Gap verdicts are SECONDARY ("confirmatory signals only").

**Rationale**: Portfolio Story captures the investor's goals and narrative. A volatile tech stock is not a "weakness" if the story prioritizes growth — it's exactly what's needed.

**Implementation**: 
- `PortfolioStoryPositionFit.fit_role` replaces verdicts (stärkt/schwächt/neutral)
- LLM prompt instruction: "Role basiert auf Story-Logik, nicht absoluter Qualität"
- Fundamental/Consensus only override to "Fehlplatzierung" if explicitly contradicted

### Role-Based Position Model
**Decision**: Each position has ONE ROLE describing its contribution to the portfolio story.

**Roles** (5-taxonomy):
- `Wachstumsmotor` (🔵): Drives capital growth (ok if volatile)
- `Stabilitätsanker` (🟡): Hedges volatility (Anleihen, Immobilien)
- `Einkommensquelle` (🟢): Generates income (Dividenden, Rentals)
- `Diversifikationselement` (🟣): Low correlation to rest (Gold, Rohstoffe)
- `Fehlplatzierung` (🔴): Doesn't fit story logic

**Benefit**: Positions understood by contribution, not as "successes/failures"

### Position-Story Iterative Refinement
**Decision**: After Portfolio Story Check, users can update position-level stories (Position.story field) based on AI-generated suggestions.

**Flow**: Story Check → Identify fit-role → User can request AI-drafted position story → Review & save → Next check uses refined story as input

**Benefit**: Convergence: each iteration refines position descriptions, next analyses are more aligned

---

## Known Technical Debt

A comprehensive technical debt analysis was conducted on **2026-04-12**. See **[BACKLOG.md § Technische Schulden](BACKLOG.md)** for the full inventory (16 items, prioritized P1–P3).

### High-Priority Items (P1)

| Item | Description | Impact | Solution |
|---|---|---|---|
| **[DEBT-1]** | Duplicate DDL in `init_db()`/`migrate_db()` | Schema changes require manual sync at 2 locations | Centralized migration system (Alembic/Flyway) |
| **[DEBT-3]** | Hardcoded model names at 7+ locations | Model updates require changes across codebase | Central `constants.py` with model registry |
| **[DEBT-4]** | No Service Layer — direct Repo access in Pages | Mixed UI/Business Logic; Pages untestable | Introduce Service classes (PortfolioService, etc.) |
| **[DEBT-5]** | LLM instantiated in UI without usage tracking | Bypasses cost/usage monitoring | Move LLM calls to Agents/Services with callbacks |

### Medium-Priority Items (P2)

| Item | Description | Impact | Solution |
|---|---|---|---|
| **[DEBT-6]** | Private attribute access from Pages (`_market`, `_llm`) | Breaks encapsulation; hard to refactor | Expose public properties/methods on Agents |
| **[DEBT-7]** | `state.py` is God Module (imports all Agents/Repos) | Import failures cascade; hard to extend | Lazy-load or module-per-feature structure |
| **[DEBT-8]** | `migrate_db()` called at 3 independent locations | No central migration guard; hard to debug | Single entry-point with idempotent guard |
| **[DEBT-9]** | `asyncio.run()` + `nest_asyncio` anti-pattern | Not production-ready; race conditions possible | Streamlit-native async integration or Task Queue |
| **[DEBT-10]** | Pages completely untested (19 files, 0 tests) | Regressions hard to catch | Extract logic to Services, test separately |
| **[DEBT-12]** | `peewee` installed but not in `requirements.txt` | Fresh installs will fail | Add to `requirements.txt` or remove if unused |

### Low-Priority Items (P3)

See BACKLOG.md for items **[DEBT-2, DEBT-11, DEBT-13, DEBT-14, DEBT-15, DEBT-16]**.

### Architectural Improvements (Future)

**Service Layer Introduction** (blocks: DEBT-4, DEBT-5, DEBT-10)
- Proposed `core/services/` module with business logic facades
- Example: `PortfolioService` encapsulates portfolio queries + calculations
- Benefits: Testable, reusable, decoupled from Streamlit

**Migration System** (blocks: DEBT-1, DEBT-8)
- Replace manual DDL duplication with formal migration tracking
- Each migration numbered (001_create_positions.sql, 002_add_story.sql, etc.)
- `migrate_db()` runs all unexecuted migrations idempotently

**Centralized Constants** (blocks: DEBT-3, dependencies: DEBT-5)
- `core/constants.py` with model registries, feature flags, default values
- Reduces hardcoded strings across codebase

---

## Recent Changes (April 2026)

✅ Removed ANTHROPIC_BASE_URL (corporate proxy, non-commercial license)
✅ Lazy agent initialization (startup faster)
✅ Structured logging (LOG_LEVEL configurable)
✅ Display-only currency flexibility (BASE_CURRENCY configurable)
✅ Infrastrukturfonds asset class added
✅ Fixed Josef's Rule bug (Immobilien mapping)
✅ Role-based Position Fits (stärkt/schwächt/neutral → Rollen-Taxonomie) — 84d27bb
✅ Storychecker Position-Story update button (iterative refinement) — 84d27bb
✅ 527 tests passing

---

*Last updated: 2026-04-11*
