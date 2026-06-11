# Architecture Overview

## Software Architecture

```mermaid
graph TD
    subgraph UI["Streamlit UI (30 Pages)"]
        PG1["Dashboard / Positionen / Marktdaten"]
        PG2["Portfolio Chat / Portfolio Checker / Position Dashboard"]
        PG3["Storychecker / Watchlist Checker / Watchlist-Analyse"]
        PG4["Consensus Gap / Fundamental Analyzer / Capital Allocator"]
        PG5["Research Chat / News / Search / Sector Rotation"]
        PG6["Research Inbox / Research Answers / Research anfordern"]
        PG7["Dividenden / Tax Loss Harvesting / Analyse"]
        PG8["System: Statistics / Skills / Scheduler / Settings"]
    end

    state["state.py — DI Factory<br/>@st.cache_resource Singletons"]

    subgraph Local["Local Agents (Ollama 🔒)"]
        PA["PortfolioAgent"]
        PSA["PortfolioStoryAgentV2"]
        WCA["WatchlistCheckerAgent"]
        MDA["MarketDataAgent"]
        PRA["PortfolioRobustnessAgent"]
        TLH["TaxLossHarvestingAgent"]
        DCA["DividendCalendarAgent"]
    end

    subgraph Cloud["Cloud Agents (Claude API ☁️)"]
        RA["ResearchAgent"]
        NA["NewsAgent"]
        SA["SearchAgent"]
        SCA["StorycheckerAgent"]
        CGA["ConsensusGapAgent"]
        STA["StructuralChangeAgent"]
        FAA["FundamentalAnalyzerAgent"]
        CAA["CapitalAllocatorAgent"]
        DAA["DevilsAdvocateAgent"]
        SRA["SectorRotationAgent"]
        WSA["WealthSnapshotAgent"]
    end

    subgraph Core["core/ — Platform Layer"]
        LLM["llm/<br/>OllamaProvider<br/>ClaudeProvider<br/>OpenAICompatibleProvider"]
        STOR["storage/<br/>28 Repositories"]
        UTIL["i18n / currency<br/>scheduler / background_jobs<br/>attribution / digests"]
    end

    DB[("SQLite + Fernet<br/>wealth.db<br/>(encrypted)")]

    UI --> state
    state --> Local
    state --> Cloud
    Local --> Core
    Cloud --> Core
    Core --> DB
```

## Runtime Architecture

```mermaid
sequenceDiagram
    participant B as Browser
    participant A as app.py
    participant S as state.py
    participant Ag as Agent
    participant LLM as LLM Provider
    participant DB as SQLite

    B->>A: Page request
    A->>A: validate config, login gate
    A->>S: get_portfolio_agent() ← EAGER
    A->>S: get_market_agent() ← EAGER + APScheduler
    A->>S: get_agent_scheduler() ← EAGER + BackgroundThread
    A->>B: render navigation

    B->>A: navigate to analysis page
    A->>S: get_*_agent() ← lazy + @st.cache_resource
    S-->>A: Agent singleton
    A->>Ag: analyze() / chat() / start_session()
    Ag->>LLM: OllamaProvider (local) or ClaudeProvider (cloud)
    LLM-->>Ag: response ± tool_calls
    Ag->>DB: save via Repository
    Ag-->>A: result
    A->>A: render results
    A->>B: return page
```

---

## Agent Overview (18 Agents)

| Agent | Provider | Model¹ | Session Type | Primary Method | Scope |
|-------|----------|-------|--------------|--------|-------|
| **PortfolioAgent** | Ollama | Local | Stateless | `chat()` + tools | Portfolio CRUD |
| **PortfolioStoryAgentV2** | Ollama | Local | Stateless | `analyze()` / `analyze_stability()` / `analyze_story_and_performance()` | Modular portfolio checks (FEAT-18) |
| **WatchlistCheckerAgent** | Ollama | Local | Stateless | `check_watchlist()` | Watchlist fit into portfolio |
| **PortfolioRobustnessAgent** | Ollama | Local | Stateless | `analyze()` | Portfolio-level stress assessment (FEAT-48) |
| **TaxLossHarvestingAgent** | Ollama | Local | Stateless | `analyze()` | Loss positions + tax impact + replacements (FEAT-44) |
| **DividendCalendarAgent** | Ollama | Local | Stateless | `analyze()` | Dividend cashflow commentary (FEAT-45) |
| **MarketDataAgent** | — | — | Stateless | APScheduler | Price fetch + history |
| **ResearchAgent** | Claude | Haiku | DB-persisted | `start_session()` + `chat()` | Research per position |
| **NewsAgent** | Claude | Haiku | Stateless | `analyze_portfolio()` | News digest |
| **SearchAgent** | Claude | Sonnet | DB-persisted | `start_session()` + `chat()` | Watchlist screening |
| **StorycheckerAgent** | Claude | Haiku | DB-persisted | `start_session()` + `chat()` + `batch_check_all()` | Thesis validation |
| **ConsensusGapAgent** | Claude | Sonnet | DB-persisted | `analyze_portfolio()` | Market vs. thesis gap |
| **StructuralChangeAgent** | Claude | Sonnet | DB-persisted | `scan()` | Structural shifts |
| **FundamentalAnalyzerAgent** | Claude | Sonnet | DB-persisted | `start_session()` + `chat()` + `analyze_portfolio()` | Deep valuation analysis |
| **CapitalAllocatorAgent** | Claude | Sonnet | DB-persisted | `analyze_portfolio()` | Management capital allocation quality — Watchlist only (FEAT-31) |
| **DevilsAdvocateAgent** | Claude | Sonnet | DB-persisted | `analyze_portfolio()` | Bear case per watchlist position (FEAT-47) |
| **SectorRotationAgent** | Claude | Sonnet | Run-persisted | `scan()` | Sector inflow/outflow vs. portfolio exposure (FEAT-46) |
| **WealthSnapshotAgent** | — | — | Stateless | `take_snapshot()` | Portfolio history |

¹ Compile-time defaults — every agent's model is overridable per agent in Settings (DB) and via `LLM_DEFAULT_MODEL`.

---

## Storage Layer (28 Repositories)

| Repository | Purpose | Tables |
|---|---|---|
| **PositionsRepository** | Portfolio + watchlist positions | `positions` |
| **MarketDataRepository** | Current prices + history | `market_data`, `price_history` |
| **SkillsRepository** | Skill templates per agent area | `skills` |
| **AppConfigRepository** | User settings (models, alerts) | `app_config` |
| **ResearchRepository** | Research chat sessions | `research_sessions`, `research_messages` |
| **SearchRepository** | Investment search sessions | `search_sessions`, `search_messages` |
| **StorycheckerRepository** | Story validation sessions | `storychecker_sessions`, `storychecker_messages` |
| **FundamentalAnalyzerRepository** | Valuation analysis sessions | `fundamental_analyzer_sessions`, `fundamental_analyzer_messages` |
| **ConsensusGapRepository** | Consensus gap sessions | `consensus_gap_sessions`, `consensus_gap_messages` |
| **CapitalAllocatorRepository** | Capital allocator quality sessions | `capital_allocator_sessions`, `capital_allocator_messages` |
| **PositionAnalysesRepository** | Verdicts for all checker agents | `position_analyses` |
| **StructuralScansRepository** | Structural change scan runs | `structural_scan_runs`, `structural_scan_messages` |
| **WealthSnapshotRepository** | Historical portfolio snapshots | `wealth_snapshots` |
| **ScheduledJobsRepository** | Periodic agent runs + run history | `scheduled_jobs`, `scheduled_job_runs` |
| **NewsRepository** | News digest runs + messages | `news_runs`, `news_messages` |
| **UsageRepository** | Token counts + costs per call | `llm_usage`, `usage_resets` |
| **ResearchQueueRepository** | MCP back channel: requests + answers (FEAT-50/52) | `research_requests`, `research_answers` |
| **BatchQueueRepository** | Pending Anthropic Batch API jobs | `pending_batches` |
| **AgentRunsRepository** | Agent run telemetry | `agent_runs` |
| **CoworkRepository** | Research Inbox entries + suggestions | `cowork_research_entries`, `cowork_watchlist_suggestions` |
| **DevilsAdvocateRepository** | Bear case sessions (FEAT-47) | `devils_advocate_sessions`, `devils_advocate_messages` |
| **SectorRotationRepository** | Sector scan runs + verdicts (FEAT-46) | `sector_rotation_runs`, `sector_rotation_messages`, `sector_verdicts` |
| **PortfolioRobustnessRepository** | Portfolio stress analyses (FEAT-48) | `portfolio_robustness_analyses` |
| **PortfolioStoryRepository** | Portfolio story analyses + position fits | `portfolio_story_analyses_new`, `portfolio_story_position_fits` |
| **WatchlistCheckerRepository** | Watchlist checker analyses | `watchlist_checker_analyses` |
| **DividendSnapshotsRepository** | Dividend data + snapshots (FEAT-45) | `dividend_data`, `dividend_snapshots` |
| **MonthlyDigestRepository** | Monthly portfolio digests (FEAT-36) | `monthly_digests` |
| **YearlyDigestRepository** | Yearly portfolio digests (FEAT-37) | `yearly_digests` |

---

## Key Architectural Patterns

### 1. Session-Based Chat
Used by: ResearchAgent, SearchAgent, StorycheckerAgent, StructuralChangeAgent, FundamentalAnalyzerAgent

```python
# Initialize session and persist to repo
session_id = agent.start_session(context=..., skill=...)
# returns int (DB row) or str (UUID)

# Multi-turn conversation
response = agent.chat(session_id, user_message)
# appends to messages table, returns assistant response
```

### 2. Batch Processing (Background Thread)
Used by: ConsensusGapAgent, StorycheckerAgent (batch_check_all), FundamentalAgent

```python
# Track job in session_state
_job = {"running": False, "done": False, "count": 0, "error": None}

# Background thread with asyncio loop
def _run_background(agent, positions, analyses_repo, job):
    loop = asyncio.new_event_loop()
    results = loop.run_until_complete(agent.analyze_portfolio(...))
    job.update({"done": True, "count": len(results)})
    loop.close()

# Polling UI with st.rerun()
if _job["running"]:
    time.sleep(5)
    st.rerun()
```

### 3. Verdict Storage & Retrieval
All verdict agents (Storychecker, ConsensusGap, FundamentalAnalyzer) write to `PositionAnalysesRepository`:

```python
# Store verdict
repo.add(PositionAnalysis(
    position_id=pos.id,
    agent="storychecker",  # or "consensus_gap", "fundamental_analyzer"
    verdict="gemischt",
    summary="...",
    created_at=datetime.now()
))

# Retrieve latest for portfolio
verdicts = repo.get_latest_bulk(position_ids=[...], agent="storychecker")
# returns Dict[position_id, PositionAnalysis]
```

### 4. Session Persistence Pattern (Architektur-Guard)

**Rule**: If an agent supports multi-turn chat (chat history + follow-up messages):
→ Sessions **MUST** be persisted to DB, not stored in-memory `Dict`

**Implementation**: Follow StorycheckerAgent/FundamentalAnalyzerAgent pattern:
1. Create session repository with tables: `<agent>_sessions` + `<agent>_messages`
2. `start_session()` → `repo.create_session()` + `repo.add_message()`
3. `chat()` → `repo.get_messages()` + LLM call + `repo.add_message()`
4. `list_sessions()` → `repo.list_sessions(limit)`

**Why**: In-memory sessions are lost after Streamlit restart. Users lose their chat history and page-load becomes slow with dangling UUIDs. DB persistence solves both.

**Anti-pattern** (don't do this):
```python
# ❌ WRONG: in-memory Dict
class MyAgent:
    def __init__(self):
        self._sessions: Dict[str, MySession] = {}
    
    def start_session(self):
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = MySession(...)  # ← lost after restart
        return session_id
```

---

## Dependency Injection (state.py)

All agents are **lazy-loaded via `@st.cache_resource` factory functions**. Three agents are **eager-initialized** in `app.py`:

- `get_portfolio_agent()` — Portfolio Chat critical path
- `get_market_agent()` — APScheduler (daily price fetch)
- `get_agent_scheduler()` — Background thread (scheduled cloud jobs)

All others are loaded on first page visit and cached for the session.

Model selection chain:
```
AppConfigRepo.get("model_<provider>_<agent>")  # per-agent override
  OR AppConfigRepo.get("model_<provider>")     # provider-wide override
  OR CLAUDE_HAIKU / CLAUDE_SONNET (constants)  # compile-time default
```

---

## LLM Provider Interface

Both `OllamaProvider` and `ClaudeProvider` extend `LLMProvider` (ABC):

```python
async def chat(messages, max_tokens, temperature) -> str
async def chat_with_tools(messages, tools, ...) -> ProviderResponse

# Shared attributes (set post-construction)
.model: str
.on_usage: Callable  # token callback to UsageRepository
.skill_context: str
.position_count: int
```

**Key Differences:**
- **ClaudeProvider**: Anthropic SDK, system prompt as separate kwarg, rate-limit retry (3x)
- **OllamaProvider**: HTTP client, system prompt inline in messages, single attempt

---

## UI Patterns

### Agent Analysis Pages (Unified Design — FEAT-19)

**Storychecker, Consensus Gap, Fundamental Analyzer** follow a consistent pattern:

```
┌─ Help Expander ("Was ist X?")
├─ Batch Section
│  ├─ Only-Pending Checkbox (filter to positions without verdict)
│  ├─ Total/Pending Count (N positions, M pending)
│  ├─ Skill Selector (Consensus Gap, Fundamental)
│  └─ Run All Button (starts background thread)
├─ Divider
└─ 2-Column Layout
   ├─ Left (0.8): Current Results
   │  └─ Card per position (icon, name, verdict, date, summary)
   └─ Right (2.2): Older Tests or Chat
      ├─ Older Tests: Expander per position (limit=5)
      └─ (Chat only in Storychecker/Fundamental)
```

**Batch Processing (Background Thread Pattern):**
- Session state tracks: `running`, `done`, `count`, `errors`, `error`, `last_error`
- Thread calls `agent.analyze_portfolio(positions, skill_name, skill_prompt, language)`
- UI polls every 5s with `st.rerun()` while running
- On done: reload verdicts, show success/error summary, refresh page

**Error Handling:**
- Detailed errors logged to Python logger (level=ERROR)
- User sees safe summary: "❌ Der Batch-Lauf ist fehlgeschlagen. Bitte versuchen Sie es später erneut."
- Last error persisted in session state for debugging

**Verdict Display (with verdict_icon):**
- All agent pages use shared `verdict_icon(verdict, VERDICT_CONFIG)` from `core.ui.verdicts`
- Colors + icons defined per agent in VERDICT_CONFIGS dict
- Older tests shown collapsible per position

### Position-Analysis Agents Pattern (FEAT-22)

**Scope**: Agents that analyze individual portfolio positions and store verdicts: StorycheckerAgent, ConsensusGapAgent, FundamentalAnalyzerAgent.

**Unified Data Model:**
```
position_analyses table:
├─ position_id: which position was analyzed
├─ agent: "storychecker" | "consensus_gap" | "fundamental_analyzer"
├─ verdict: agent-specific enum (e.g., "intact" / "wächst" / "unterbewertet")
├─ summary: 1-sentence summary of verdict
├─ skill_name: which skill was used (optional, for filtering/history)
├─ session_id: reference to agent-specific session table (optional; for multi-turn chat or full-text retrieval)
├─ analysis_text: full analysis details (optional; for agents without sessions, e.g., consensus_gap)
└─ created_at: when analysis was created
```

**Unified UI Pattern** (right-side results panel per position):
```
{verdict_icon} **Position Name**
`Ticker` · Datum · Skill Name

Summary (1 Satz)

▼ Vollständige Analyse [expandable, default open]
  {Retrieved via: session_id → agent_messages table, OR analysis_text field}

▼ Ältere Analysen (N) [expandable, default collapsed]
  {verdict_icon} **Datum** · Skill Name
  Summary
```

**Implementation Checklist for New Position-Analysis Agent:**

1. **Agent Class** (`agents/<name>_agent.py`):
   - `analyze_portfolio(positions, skill_name, skill_prompt, language)` → async batch method
   - Call `analyses_repo.save(position_id, agent=<name>, verdict, summary, [session_id], [analysis_text])`
   - If multi-turn chat needed: create session table + StorycheckerAgent-style repository

2. **Data Storage** (`position_analyses` table):
   - verdict: enum or string; use fixed codes (not localized) for consistency
   - summary: 1 sentence; can be extracted from LLM output or computed
   - session_id (optional): if agent has multi-turn chat, store session reference
   - analysis_text (optional): full response text (if no session table)

3. **Page** (`pages/<name>.py`):
   - Batch section: "Only Pending" checkbox, Skill selector, "Run All" button (background thread)
   - Current Results (right panel):
     ```python
     _verdicts = analyses_repo.get_latest_bulk(position_ids, agent="<name>")
     for _pos, _a in _verdicts.items():
         st.markdown(f"{verdict_icon(_a.verdict)} **{_pos.name}**")
         st.caption(_a.summary)
         # Full-text expander
         if _a.session_id:
             messages = agent.get_messages(_a.session_id)
             with st.expander("▼ Vollständige Analyse", expanded=True):
                 st.markdown(messages[0].content)
         elif _a.analysis_text:
             with st.expander("▼ Vollständige Analyse", expanded=True):
                 st.markdown(_a.analysis_text)
     ```
   - History (inline expander): `analyses_repo.get_for_position(pos_id, limit=20)`
   - **No left-side session navigation** (pages are cleaner when all history is on the right)

4. **Verdict Config** (`core/ui/verdicts.py`):
   - Add `VERDICT_CONFIGS["<agent_name>"]` dict with verdict → (icon, color) mapping

5. **Tests** (`tests/`):
   - Integration test: agent stores verdict + summary correctly
   - Smoke test: page loads without exceptions (`pytest tests/integration/test_db_schema_migration.py`)

---

## Configuration Files

### `config/default_skills.yaml`
Skill templates per agent area. Seeded on startup via `SkillsRepository.seed_if_empty()`.

User-editable at runtime. System skills (Josef's Regel) injected directly by agents.

### `config/asset_classes.yaml`
12 asset classes with metadata:
- `name` (Aktie, Aktienfonds, Festgeld, etc.)
- `investment_type` (Wertpapiere, Renten, Geld, etc.)
- `auto_fetch` (enable yfinance)
- `watchlist_eligible` (allow in watchlist)
- `manual_valuation` (show "Schätzwert" button)

---

## Architectural Decisions

### Story-Primacy Model
For existing positions, **Portfolio Story alignment is PRIMARY**. Fundamental/Consensus verdicts are **confirmatory only**.

Rationale: A volatile tech stock is not a "weakness" if the story prioritizes growth — it's exactly what's needed.

### Role-Based Position Fit
Each position has ONE ROLE describing its contribution:
- 🔵 **Wachstumsmotor** — capital growth (ok if volatile)
- 🟡 **Stabilitätsanker** — volatility hedge (bonds, real estate)
- 🟢 **Einkommensquelle** — income generation (dividends)
- 🟣 **Diversifikationselement** — low correlation (gold, commodities)
- 🔴 **Fehlplatzierung** — doesn't fit story

---

## Currency System

**Display-only approach**: `BASE_CURRENCY` env var configurable (EUR/CHF/GBP/USD/JPY). All DB fields remain in EUR.

Pages use `core.currency.symbol()` and `core.currency.fmt()` for display.

---

## Encryption & Storage

- **Prod**: Full encryption via Cryptography/Fernet on: position names, stories, notes, extra_data (JSON)
- **Demo**: Plaintext (PassthroughEncryptionService)
- **Migrations**: Auto-run on startup via `migrate_db()` — idempotent, no data loss

---

## Testing Strategy

- **Unit tests**: Agent logic, repository CRUD, parsing; smoke tests for all 30 pages (AppTest)
- **Integration tests**: Full workflows with real SQLite (`:memory:`)
- **No mocking of repositories**: Always use real storage for higher fidelity
- **Test-first on bugs**: write the failing test before the fix (see CLAUDE.md Test-Disziplin)
- **Volume**: 996 tests, ~38s wall time, coverage 71% (target: 50%+)

```bash
pytest tests/                 # All
pytest tests/unit/            # Unit only
pytest tests/integration/     # Integration only
pytest -k consensus_gap       # Specific agent
```

---

## Known Technical Debt

See **BACKLOG.md § Technical Debt** for full inventory.

**DEBT Stack Completed (2026-04-16):** ✅
- ✅ [DEBT-9] asyncio.get_event_loop() → asyncio.run() (Python 3.12+ safe)
- ✅ [DEBT-7] state.py decomposed (437 → 60 lines + 5 modules, zero page disruption)
- ✅ [DEBT-4] Service Layer + Agent Encapsulation (AnalysisService, PortfolioService; agents own persistence)

---

## Multi-Language Support (i18n)

**UI Language Selection**: Settings page allows German ↔ English switching via `core.i18n` module.

**Agent Response Language** (2026-04-17):
- Agents accept `language: str = "de"` parameter on execution methods
- System prompts dynamically inject language instruction via `agents/agent_language.py` helpers
- Pages capture `current_language()` in main thread before background thread spawn (session_state safety)

**Verdict Code Preservation**:
- Internal verdict labels (`unterbewertet`, `wächst`, `intact`, etc.) remain German
- These are database identifiers, not user-visible text
- Agents with schema-locked enums use `response_language_with_fixed_codes()` helper
- Explicitly instructs LLM: "Write text in {language}, use EXACTLY these codes as-is"

**Scope**:
- ✅ All analysis agents accept `language` (StorycheckerAgent, ConsensusGapAgent, FundamentalAnalyzerAgent, ResearchAgent, DevilsAdvocateAgent, …)
- ✅ Page UI via `translations/de.yaml` + `en.yaml` (`core.i18n.t()`) — most pages fully covered
- ⚠️ **Known debt**: portfolio_story.py and positionen.py partially hardcoded German; cowork_setup.py intentionally German-only until FEAT-56

---

## Recent Changes (May–June 2026)

✅ **MCP Research Loop complete** (FEAT-49–55, 2026-06-09 through 2026-06-11)
   - MCP server (stdio + optional HTTP), research queue, UserPromptSubmit hook
   - Research Answers UI, global request form, Position Dashboard integration

✅ **Security: SEC-4 + SEC-5** (2026-06-09 / 2026-06-11)
   - Path traversal, prompt-injection framing, length limits, constant-time bearer
     comparison, XML escaping in the hook, limit sync across both write paths

✅ **New agents** (May–June 2026)
   - DevilsAdvocateAgent + PortfolioRobustnessAgent (FEAT-47/48)
   - SectorRotationAgent (FEAT-46), TaxLossHarvestingAgent (FEAT-44), DividendCalendarAgent (FEAT-45)

✅ **Batch API** (2026-06-07/08) — 50% cheaper scheduled jobs via `pending_batches` + scheduler polling

✅ **Attribution & digests** (FEAT-34–39, May 2026) — monthly/yearly attribution incl. dividends, digest reports, macro chips

✅ **Status matrix & background jobs** (FEAT-40/41) — `core/background_jobs.py` shared across SC/CG/FA/CA, watchlist cockpit

✅ **Provider flexibility** (May 2026) — OpenRouter/DeepSeek migration, Tavily search, `OpenAICompatibleProvider`

For older changes see CHANGELOG.md.

---

## Service Layer (Post-DEBT-4)

### Core Services

**AnalysisService** (`core/services/analysis_service.py`)
- `get_verdicts(position_ids, agent)` — Fetch verdicts for a list of positions from a specific agent
- `get_all_verdicts(position_ids)` — Fetch all agent verdicts in one call (storychecker, consensus_gap, fundamental_analyzer)
- `get_coverage(positions, agents)` — Count positions missing analysis per agent
- `has_verdict(position_id, agent)` — Check if position has a verdict
- `get_verdict(position_id, agent)` — Get single verdict

**PortfolioService** (`core/services/portfolio_service.py`)
- `get_all_positions(include_portfolio, include_watchlist, require_story, require_ticker)` — Centralized position aggregation
- `get_portfolio_positions()` — Convenience method for portfolio only
- `get_watchlist_positions()` — Convenience method for watchlist only

### Usage Pattern
Pages no longer call `analyses_repo.get_latest_bulk()` or `positions_repo.get_*()` directly:
```python
# Before DEBT-4:
verdicts = analyses_repo.get_latest_bulk(ids, "storychecker")

# After DEBT-4:
verdicts = analysis_service.get_verdicts(ids, "storychecker")
```

### Pages Using Services
- `pages/structural_scan.py` — AnalysisService, PortfolioService
- `pages/positionen.py` — AnalysisService
- `pages/watchlist_checker.py` — AnalysisService, PortfolioService
- `pages/portfolio_story.py` — AnalysisService, PortfolioService
- `pages/consensus_gap.py` — AnalysisService, PortfolioService
- `pages/fundamental_analyzer.py` — PortfolioService  
✅ Portfolio Story subsystem (role-based fit)  
✅ 550 tests passing, 76% coverage  

---

## LLM Provider Configuration

The public LLM layer is provider-agnostic and configured via environment variables.

### Configuration Variables

| Variable | Purpose | Default |
|---|---|---|
| `LLM_API_KEY` | Provider API key | — (required) |
| `LLM_BASE_URL` | Endpoint URL | empty = Anthropic direct |
| `LLM_DEFAULT_MODEL` | Fallback model when no DB override exists | empty = `claude-haiku-4-5-20251001` |
| `CLAUDE_MODELS` | Comma-separated list for the Settings dropdown | `claude-haiku-4-5-20251001,claude-sonnet-4-6,claude-opus-4-6` |

### Model Resolution Chain

```
DB (agent-specific)
  → DB (global)
  → LLM_DEFAULT_MODEL (if set)
  → hardcoded constant (CLAUDE_HAIKU/CLAUDE_SONNET)
```

DB entries are written via the Settings UI. `LLM_DEFAULT_MODEL` serves as a fallback for infrastructure changes (provider switch without reconfiguring Settings).

### Web Search

| Mode | Condition | Portability |
|---|---|---|
| Anthropic built-in (`web_search_20250305`) | no `TAVILY_API_KEY` | Anthropic / OpenRouter only |
| Tavily (client-side) | `TAVILY_API_KEY` set | any provider with tool use |

Agents with web search (SearchAgent, StructuralChangeAgent, NewsAgent): on OpenRouter or other providers, enable via Tavily — or pick models with built-in search (Perplexity Sonar).

### Known Provider Configurations

#### Anthropic direct (default)
```env
LLM_API_KEY=sk-ant-...
# LLM_BASE_URL, LLM_DEFAULT_MODEL = empty
```

#### OpenRouter  
*Anthropic-SDK-compatible, 100+ models (Claude, GPT-4o, Perplexity Sonar, etc.)*

```env
LLM_API_KEY=sk-or-...
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_DEFAULT_MODEL=anthropic/claude-sonnet-4-6
CLAUDE_MODELS=anthropic/claude-haiku-4-5-20251001,anthropic/claude-sonnet-4-6,perplexity/sonar,openai/gpt-4o
TAVILY_API_KEY=tvly-...  # optional: web search for GPT-4o, etc.
```

**Perplexity Sonar via OpenRouter:** Sonar has built-in web search — no separate web-search tool calls needed. Select Sonar in Settings → no Tavily required.

#### Perplexity Sonar direct  
*OpenAI API format, built-in web search, no tools needed*

```env
OPENAI_API_KEY=pplx-...
OPENAI_BASE_URL=https://api.perplexity.ai
OPENAI_MODELS=sonar,sonar-pro,sonar-reasoning
```

**Note:** With Sonar the `OpenAICompatibleProvider` is used (not ClaudeProvider). Sonar has internal web search → agents work without Tavily/tool-use loop. Ideal for "out of Anthropic tokens" scenarios.

#### Other compatible endpoints (OpenAI format)
Any endpoint supporting the OpenAI API format uses `OpenAICompatibleProvider`:
- **Groq**: `OPENAI_BASE_URL=https://api.groq.com/openai/v1`
- **Together AI**: `OPENAI_BASE_URL=https://api.together.xyz/v1`
- any OpenAI-compatible proxy

**Important after a provider switch:**  
1. Set `OPENAI_MODELS` (or `CLAUDE_MODELS` for Anthropic-compatible providers) to the new model IDs
2. Open the Settings page → re-select models for each agent (writes to DB)
3. DB entries then override all fallbacks

### Provider Switch Workflow (example: Anthropic → Sonar)

```bash
# 1. Adjust .env (no need to change LLM_API_KEY — keep it for the OpenRouter scenario)
OPENAI_API_KEY=pplx-...
OPENAI_BASE_URL=https://api.perplexity.ai
OPENAI_MODELS=sonar,sonar-pro

# 2. Start the app
streamlit run app.py

# 3. Settings → Cloud Agents (now shows "OpenAI-compatible 🌐" instead of "Claude ☁️")
# → set models for News, Search, etc. to "sonar" → Save

# 4. Run an agent → automatically uses Sonar with built-in web search
```

---

---

## MCP Server Architecture (FEAT-49/50/51/52)

### What is MCP?

The **Model Context Protocol** (MCP) is an open protocol by Anthropic that connects LLM hosts (e.g. Claude Code, Claude Desktop) to external tool servers. The transport is JSON-RPC 2.0 over stdio — no HTTP server, no port, no auth setup.

```
Claude Code  ──stdio──►  MCP Server (wealth_mcp.py)
             ◄──stdio──   FastMCP SDK → tool functions (Python)
```

The server declares tools as plain Python functions with `@mcp.tool()`. Claude Code discovers them at startup, lists them as available tools, and calls them like any other tool call.

### Dual-Venv Architecture

The MCP SDK requires Python ≥ 3.10, the main app runs on Python 3.9.6. Solution: two separate virtual environments.

```
.venv/        (Python 3.9.6)  — main app, all tests, all imports
mcp_venv/     (Python 3.11.15) — only mcp_server/wealth_mcp.py
```

The separation is clean: `mcp_server/_helpers.py` contains the testable logic (no MCP import) — YAML building, atomic file writes, input validation (`validate_answer_input`), and the `BearerTokenMiddleware` — importable from `.venv`. `wealth_mcp.py` imports `_helpers` + FastMCP and runs only in `mcp_venv`.

```
mcp_server/
├── _helpers.py       # pure Python 3.9 — testable from .venv (incl. auth middleware + validation)
├── wealth_mcp.py     # FastMCP server — runs in mcp_venv
├── check_queue.py    # hook script — /usr/bin/python3
├── requirements.txt  # mcp[cli]>=1.0.0, pyyaml>=6.0, uvicorn
└── __init__.py
```

### Registration and Auto-Approval

```json
// .mcp.json (project root — loaded at Claude Code startup)
{
  "mcpServers": {
    "wealth-research": {
      "command": "/Users/erik/Projects/wealth_management/mcp_venv/bin/python",
      "args": ["-m", "mcp_server.wealth_mcp"],
      "cwd": "/Users/erik/Projects/wealth_management"
    }
  }
}
```

```json
// .claude/settings.json
{
  "enabledMcpjsonServers": ["wealth-research"]
}
```

`enabledMcpjsonServers` suppresses the manual approval prompt on every session start.

### Tool Overview

| Tool | Direction | What it does |
|---|---|---|
| `propose_position()` | Claude → App | Writes `.md` to the Cowork outbox, file watcher imports it |
| `propose_multiple()` | Claude → App | Batch version, several candidates in one file |
| `get_research_queue()` | Claude ← App | Reads open research requests from `research_requests` |
| `complete_research_request(id)` | Claude → App | Marks a request as done |
| `submit_research_answer(md, ...)` | Claude → App | Writes an answer to `research_answers`, marks the request done |

### Bidirectional Communication (FEAT-50/51)

The research queue implements two complementary channels:

```
App → Claude:  research_requests table  +  UserPromptSubmit hook
Claude → App:  research_answers table   +  submit_research_answer() tool
```

**App → Claude (posting requests):**
1. User fills in the form on the Position Dashboard page (or the global Research Request page)
2. `ResearchQueueRepository.create_request()` writes a row to the DB
3. `mcp_server/check_queue.py` runs before every Claude Code message (hook)
4. The hook reads open requests and injects them as `additionalContext`
5. Claude sees the requests at the start of every session/message

**Claude → App (answering requests):**
1. Claude calls `get_research_queue()` for details
2. Answers via `submit_research_answer(markdown, request_id)` 
3. The answer appears in `pages/research_answers.py` under "Answers"
4. The request is automatically marked `done`

```mermaid
sequenceDiagram
    participant U as User (App)
    participant DB as SQLite
    participant H as check_queue.py (Hook)
    participant CC as Claude Code
    participant T as wealth_mcp.py (MCP Tools)

    U->>DB: create_request("Analyze AAPL Q3 numbers")
    Note over H: On next CC message
    CC->>H: UserPromptSubmit fired
    H->>DB: SELECT * FROM research_requests WHERE status='open'
    H-->>CC: additionalContext with open requests
    CC->>T: get_research_queue() [optional — for details]
    T->>DB: SELECT ...
    T-->>CC: list with details
    CC->>T: submit_research_answer("## AAPL Q3...", request_id=1)
    T->>DB: INSERT research_answers + UPDATE status='done'
    U->>DB: list_answers(ticker="AAPL")
    DB-->>U: answer appears on the Research Answers page
```

### UserPromptSubmit Hook

```python
# mcp_server/check_queue.py — output format
output = {
    "hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": "📋 2 open requests...",
    }
}
print(json.dumps(output))
```

`additionalContext` is injected into the context before the user message — Claude sees the requests automatically, without the user doing anything.

### Cowork Outbox Pattern (FEAT-49)

`propose_position()` writes `.md` files atomically into the outbox directory:

```python
# Atomic write: tmp/ → rename (prevents partial file reads by the watcher)
tmp_path.write_text(content, encoding="utf-8")
tmp_path.rename(final_path)  # atomic on same filesystem
```

The app's existing watchdog file watcher detects new files and imports them as watchlist candidates for human review — with zero code changes to the app.

### Security Hardening (SEC-4 + SEC-5)

The MCP server is the first external write path that does not go through the Streamlit UI. Mitigations:

| Vector | Mitigation |
|---|---|
| Path traversal in outbox filename | Slug sanitization (`[^A-Za-z0-9._-]` → `_`) + date prefix |
| Prompt injection via hook context | XML framing **and** escaping (`xml.sax.saxutils`) — tag breakout from `focus`/`ticker` impossible, output is parseable XML |
| Oversize inputs | `focus` ≤ 500, `context` ≤ 2000, `ticker` ≤ 20 chars, `answer_md` ≤ 100 KB |
| Duplicate write paths (repo vs. raw SQL) | Limits defined in `core/storage/research_queue.py` **and** `mcp_server/_helpers.py`; a test enforces they stay in sync |
| HTTP transport auth | Bearer token required, `hmac.compare_digest` (constant-time), websocket scope rejected, bound to `127.0.0.1` |
| DB access | Convention + checklist (CLAUDE.md): tools touch only `research_requests`/`research_answers` |

### New Storage Tables

```sql
CREATE TABLE research_requests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    request_type TEXT NOT NULL DEFAULT 'research_question',  -- watchlist_candidate | research_question | analysis_deepdive | general
    ticker       TEXT,
    focus        TEXT NOT NULL,   -- the actual question/request
    context      TEXT,            -- additional context (optional)
    source       TEXT NOT NULL DEFAULT 'manual',  -- manual | agent | batch
    status       TEXT NOT NULL DEFAULT 'open',    -- open | in_progress | done
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE research_answers (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER REFERENCES research_requests(id),
    ticker     TEXT,
    answer_md  TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

---

*Last updated: 2026-06-11*
