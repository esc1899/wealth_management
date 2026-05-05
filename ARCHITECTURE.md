# Architecture Overview

## Software Architecture

```mermaid
graph TD
    subgraph UI["Streamlit UI (15 Pages)"]
        PG1["Dashboard / Positionen / Marktdaten"]
        PG2["Portfolio Chat / Portfolio Story"]
        PG3["Storychecker / Watchlist Checker"]
        PG4["Consensus Gap / Fundamental Analyzer"]
        PG5["Research Chat / News / Search"]
        PG6["System: Statistics / Skills"]
    end

    state["state.py — DI Factory<br/>@st.cache_resource Singletons"]

    subgraph Local["Local Agents (Ollama 🔒)"]
        PA["PortfolioAgent"]
        PSA["PortfolioStoryAgent"]
        WCA["WatchlistCheckerAgent"]
        MDA["MarketDataAgent"]
    end

    subgraph Cloud["Cloud Agents (Claude API ☁️)"]
        RA["ResearchAgent"]
        NA["NewsAgent"]
        SA["SearchAgent"]
        SCA["StorycheckerAgent"]
        CGA["ConsensusGapAgent"]
        STA["StructuralChangeAgent"]
        FAA["FundamentalAnalyzerAgent"]
        WSA["WealthSnapshotAgent"]
    end

    subgraph Core["core/ — Platform Layer"]
        LLM["llm/<br/>OllamaProvider<br/>ClaudeProvider"]
        STOR["storage/<br/>13 Repositories"]
        UTIL["i18n / currency<br/>scheduler / constants<br/>portfolio_stability"]
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

## Agent Overview (12 Agents)

| Agent | Provider | Model | Session Type | Primary Method | Scope |
|-------|----------|-------|--------------|--------|-------|
| **PortfolioAgent** | Ollama | Local | Stateless | `chat()` + tools | Portfolio CRUD |
| **PortfolioStoryAgent** | Ollama | Local | Stateless | `analyze()` / `analyze_stability()` / `analyze_story_and_performance()` | Modular portfolio checks (FEAT-18) |
| **WatchlistCheckerAgent** | Ollama | Local | Stateless | `check_watchlist()` | Watchlist fit into portfolio |
| **MarketDataAgent** | — | — | Stateless | APScheduler | Price fetch + history |
| **ResearchAgent** | Claude | Haiku | DB-persisted | `start_session()` + `chat()` | Research per position |
| **NewsAgent** | Claude | Haiku | Stateless | `analyze_portfolio()` | News digest |
| **SearchAgent** | Claude | Sonnet | DB-persisted | `start_session()` + `chat()` | Watchlist screening |
| **StorycheckerAgent** | Claude | Haiku | DB-persisted | `start_session()` + `chat()` + `batch_check_all()` | Thesis validation |
| **ConsensusGapAgent** | Claude | Sonnet | Stateless | `analyze_portfolio()` | Market vs. thesis gap |
| **StructuralChangeAgent** | Claude | Sonnet | DB-persisted | `scan()` | Structural shifts |
| **FundamentalAnalyzerAgent** | Claude | Haiku | DB-persisted | `start_session()` + `chat()` + `analyze_portfolio()` | Deep valuation analysis |
| **WealthSnapshotAgent** | — | — | Stateless | `take_snapshot()` | Portfolio history |

---

## Storage Layer (13 Repositories)

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
| **PositionAnalysesRepository** | Verdicts (storychecker/consensus_gap/fundamental) | `position_analyses` |
| **StructuralScansRepository** | Structural change scan runs | `structural_scan_runs`, `structural_scan_messages` |
| **WealthSnapshotRepository** | Historical portfolio snapshots | `wealth_snapshots` |
| **ScheduledJobsRepository** | Periodic agent runs | `scheduled_jobs` |
| **NewsRepository** | News digest caching | `news_digests` |
| **UsageRepository** | Token counts + costs per call | `usage_log` |

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

- **Unit tests**: Agent logic, repository CRUD, parsing (564 total — 14 page smoke tests)
- **Integration tests**: Full workflows with real SQLite (`:memory:`)
- **No mocking of repositories**: Always use real storage for higher fidelity
- **Coverage**: 69% (target: 50%+; page smoke tests reduce metric but add safety)

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
- ✅ 7 agents (StorycheckerAgent, ConsensusGapAgent, FundamentalAgent, ResearchAgent, etc.)
- ✅ 6 pages (consensus_gap, fundamental_analyzer, structural_scan, research_chat, storychecker, watchlist_checker)
- ⚠️ **Out of scope**: Page UI labelsportfolio_story.py, positionen.py partially hardcoded German)

---

## Recent Changes (April 2026)

✅ **DEBT-10: Page Smoke Tests** (2026-04-19)
   - All 19 pages load without exceptions (Streamlit AppTest framework)
   - Safety layer for page refactoring, initialization verification

✅ **Documentation Sync & Debt Inventory** (2026-04-19)
   - ARCHITECTURE, CHANGELOG, MIGRATIONS, BACKLOG updated
   - BACKLOG restored with DEBT-8/10/13 open items
   - Cleanup session (Langfuse/Benchmark/Labels) fully documented

✅ **Agent i18n Support** (2026-04-17)
   - Multi-language responses, verdict codes preserved, thread-safe language passing

✅ **DEBT Stack Complete** (2026-04-16)
   - Async modernization (Python 3.12+), State decomposition, Service layer + Agent encapsulation

✅ Skills Architecture Complete (Phase 5)  
✅ Watchlist Checker + Consensus Gap Analysis Integration  
✅ Fundamental Analyzer (multi-turn session-based)

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

Der Public-LLM-Layer ist provider-agnostisch über Umgebungsvariablen konfigurierbar.

### Konfigurationsvariablen

| Variable | Zweck | Default |
|---|---|---|
| `LLM_API_KEY` | API-Key des Providers | — (Pflicht) |
| `LLM_BASE_URL` | Endpoint-URL | leer = Anthropic direkt |
| `LLM_DEFAULT_MODEL` | Fallback-Modell wenn kein DB-Override | leer = `claude-haiku-4-5-20251001` |
| `CLAUDE_MODELS` | Komma-Liste für Settings-Dropdown | `claude-haiku-4-5-20251001,claude-sonnet-4-6,claude-opus-4-6` |

### Modell-Auflösungskette

```
DB(agent-spezifisch) 
  → DB(global) 
  → LLM_DEFAULT_MODEL (falls gesetzt)
  → Hardcoded Constant (CLAUDE_HAIKU/CLAUDE_SONNET)
```

Die DB-Einträge werden per Settings-UI gespeichert. `LLM_DEFAULT_MODEL` ist als Fallback für Infrastruktur-Wechsel (Provider-Switch ohne Settings-Neuconfig).

### Web Search

| Modus | Bedingung | Portabilität |
|---|---|---|
| Anthropic built-in (`web_search_20250305`) | kein `TAVILY_API_KEY` | Nur Anthropic / OpenRouter |
| Tavily (client-side) | `TAVILY_API_KEY` gesetzt | Alle Provider mit Tool Use |

Agents mit Web Search (SearchAgent, StructuralChangeAgent, NewsAgent): Bei OpenRouter oder anderen Providern mit Tavily aktiviert. Oder Modelle wählen mit integrierter Suche (Perplexity Sonar).

### Bekannte Provider-Konfigurationen

#### Anthropic direkt (Default)
```env
LLM_API_KEY=sk-ant-...
# LLM_BASE_URL, LLM_DEFAULT_MODEL = leer
```

#### OpenRouter  
*Anthropic-SDK-kompatibel, 100+ Modelle (Claude, GPT-4o, Perplexity Sonar, etc.)*

```env
LLM_API_KEY=sk-or-...
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_DEFAULT_MODEL=anthropic/claude-sonnet-4-6
CLAUDE_MODELS=anthropic/claude-haiku-4-5-20251001,anthropic/claude-sonnet-4-6,perplexity/sonar,openai/gpt-4o
TAVILY_API_KEY=tvly-...  # Optional: für Web Search bei GPT-4o, etc.
```

**Perplexity Sonar über OpenRouter:** Sonar hat integrierte Websuche — keine separaten Web-Search-Tool-Calls nötig. Wähle Sonar über Settings → kein Tavily erforderlich.

#### Perplexity Sonar direkt  
*OpenAI-API-Format, gebaut-in web search, keine Tools nötig*

```env
OPENAI_API_KEY=pplx-...
OPENAI_BASE_URL=https://api.perplexity.ai
OPENAI_MODELS=sonar,sonar-pro,sonar-reasoning
```

**Besonderheit:** Mit Sonar wird `OpenAICompatibleProvider` genutzt (nicht ClaudeProvider). Sonar hat interne Web Search → Agents arbeiten ohne Tavily/Tool-Use-Loop. Perfekt für "out of Anthropic tokens"-Szenarien.

#### Weitere kompatible Endpoints (OpenAI-Format)
Jeder Endpunkt der die OpenAI API-Format unterstützt nutzt `OpenAICompatibleProvider`:
- **Groq**: `OPENAI_BASE_URL=https://api.groq.com/openai/v1`
- **Together AI**: `OPENAI_BASE_URL=https://api.together.xyz/v1`
- Beliebige OpenAI-kompatible Proxies

**Wichtig nach Provider-Wechsel:**  
1. `OPENAI_MODELS` (oder `CLAUDE_MODELS` für Anthropic-kompatible) auf neue Modell-IDs setzen
2. Settings-Seite öffnen → Modelle für jeden Agent neu wählen (schreibt in DB)
3. DB-Einträge überschreiben dann alle Fallbacks

### Provider-Wechsel Workflow (Beispiel: Anthropic → Sonar)

```bash
# 1. .env anpassen (kein Ändern von LLM_API_KEY nötig, bleibt für OpenRouter-Scenario)
OPENAI_API_KEY=pplx-...
OPENAI_BASE_URL=https://api.perplexity.ai
OPENAI_MODELS=sonar,sonar-pro

# 2. App starten
streamlit run app.py

# 3. Settings → Cloud Agents (zeigt jetzt "OpenAI-kompatibel 🌐" statt "Claude ☁️")
# → Modelle für News, Search, etc. auf "sonar" setzen → Save

# 4. Agent führen → verwendet automatisch Sonar mit integrierter Web Search
```

---

*Last updated: 2026-04-19*
