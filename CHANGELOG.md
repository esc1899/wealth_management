# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Bug Fixes + Performance — 2026-05-06

**FA + CG Batch Parallelization**
- `FundamentalAnalyzerAgent.analyze_portfolio()`: sequenzieller for-loop → `asyncio.gather` + `Semaphore(3)`
- Neuer `start_session_async()` + `_run_llm_async()` als sauberer async-Pfad (kein `asyncio.run()` in laufendem Event Loop)
- `ConsensusGapAgent.analyze_portfolio()`: gleiches Muster, `_analyze_position()` extrahiert
- FA `max_tokens` 1500 → 3000; `position.story` aus Initial-Message entfernt (Storychecker-Overlap)

**Web-Search Tracking Fix**
- `core/llm/claude.py`: Anthropic built-in `web_search_20250305` zählte immer 0
- Root cause: Count liegt in `response.usage.server_tool_use.web_search_requests`, nicht in tool_use-Blöcken
- Kosten und Web-Search-Anzahl stimmen jetzt mit Anthropic-Billing überein

**Positionen-Tabelle UI**
- Spalte `"🔬 Analys."` → `"Exkl."`, Row-Icon `"🔬"` → `"✖"`
- `"⚠️ Overr."` → `"Overr."`

**Position Dashboard — Vollständige Analyse Bug Fix**
- SC + FA: `get_messages()[0]` (User-Prompt) → `[-1]` (Assistent-Antwort)
- CG: `analysis_text` (nie befüllt) → `cg_agent.get_messages()[-1].content` via neu importiertem `get_consensus_gap_agent`

---

### FEAT-25: Position Dashboard — Aggregated Position Analysis (2026-05-05)

**Single page + dropdown selector: all analyses for one portfolio position at a glance.**

**Scope & Design**
- New page: `pages/position_dashboard.py` with position dropdown
- Portfolio-positions only (no watchlist)
- Read-only aggregation (no direct analysis triggers)
- Kursverlauf: moved from `analyse.py` (lines 130–148)

**Sections**
1. **Price History**: 1-year chart via MarketAgent (uses selectbox Kursverlauf pattern)
2. **Analyses**: 3 columns (Storychecker | Consensus Gap | Fundamental Analyzer)
   - Verdict badge + summary + created_at date
   - Full-text expandable (via session_id → get_messages() or analysis_text)
   - Placeholder "Noch nicht analysiert" if no verdict
3. **News Digest**: Extract relevant ticker section from latest run
   - No new LLM call (reuses last digest)
   - Pattern: parse `## TICKER —` until next `##` or end
   - Fallback: info if ticker not in last digest

**Reusable Components**
- `_render_checker_card(title, verdict_obj, config, full_text_fn)` — card with badge + summary + expander
- `_extract_ticker_section(digest, ticker)` — markdown section parsing

**Changes**
- New file: `pages/position_dashboard.py` (220 LOC)
- Modified: `pages/analyse.py` (removed Price History section; Zeilen 130–148)
- Modified: `app.py` (navigation: added Position Dashboard after Analyse)
- Tests: Added smoke test in `test_watchlist_checker_ui.py`; 9 unit tests for `_extract_ticker_section`

**Testing**
- 627 tests passing (69.47% coverage)
- Smoke test: page loads without exception ✓
- Unit tests: 9/9 passing (extract_ticker_section logic) ✓
- All other tests: no regression

**Architecture Decision**
- Position analysis data NOT passed to Portfolio Story agent context (local LLM gets confused)
- Data is purely informational on UI layer (may be reconsidered later)

---

### FEAT-23: News Agent UI Refactor — Position-Analysis Pattern (2026-05-05)

**News Agent layout unified with FA/SC/CG pattern. Auto-load of latest run for immediate visibility.**

**Root Cause Analysis + Fix**
- First implementation had News Agent show new layout only after manual click (invisible to users)
- Root causes: (1) run-list kept in left panel (should only be right panel), (2) no auto-load of latest run
- Solution: Removed run-list from left panel, added auto-load of latest run on page init

**Changes**
- **Left Panel**: Now contains form only (Skill selectbox + Focus input + Start button) — no run history list
- **Right Panel**: Auto-loads latest run; displays Digest expander (open) + Older Runs inline-history (closed) + Chat
- **Pattern**: Unified with FA/SC/CG — immediate content visibility, no empty-state left panels
- **Storage**: No DB changes (NewsRun/NewsMessages already correct)

**Testing**
- 617 tests passing (69.67% coverage)
- No regression
- news_chat.py smoke test passes
- Layout immediately visible on page load (auto-load working)

**Commits**
- `e9c9235` feat: FEAT-23 — News Agent UI Refactor (initial version)
- `1b58b01` fix: FEAT-23 — News Agent UI Pattern (root cause fix)

**Architecture Learning**
- Pattern consistency matters: small deviations (keeping left-panel history list) can hide entire features
- Auto-load is invisible but essential: users don't notice it, but notice empty right panels
- Structured exploration (comparing FA/SC/CG) reveals exact problems faster than debug-statements

### FundamentalAnalyzer Refactoring — Lean Prompt + Detailed UI + Retention (2026-05-04)

**Optimized agent prompt + full analysis display for monthly decision-making workflow.**

**Phase 1 — Agent Optimization**
- **System Prompt**: 250 → 50 Tokens (removed prescriptive 5-section structure; skills now define focus)
- **Summary Extraction**: New `**ZUSAMMENFASSUNG:**` marker in prompt (LLM-controlled, replaces heuristic extraction)
- **max_tokens**: 4096 → 1500 (optimize for 500–1000 token output; web_search calls still fit)
- **Web-Search**: max_uses: 3 → 5 (deeper research capability)

**Phase 2 — UI Display Overhaul**
- **"Aktuelle Ergebnisse"**: Now displays Summary (1-line teaser) + Full Analysis (first assistant message, expanded by default) + History
- **No clicks needed**: Full analysis immediately visible for monthly decision-making (not hidden in session history)
- **i18n**: Added keys `fundamental.current_results`, `fundamental.full_analysis` (de + en)

**Phase 3 — Data Retention**
- **cleanup_old_sessions(days=365)**: New method in FundamentalAnalyzerRepository
- **Automatic trigger**: Runs at end of `analyze_portfolio()` batch job (no extra scheduler needed)
- **Impact**: Verdicts persisted in `position_analyses` (history intact); session messages deleted after 12 months

**Testing**
- 587 tests passing (2 more than before, better coverage)
- Imports validated; Streamlit app starts without errors
- Tested: Single position analysis → Summary + Full Analysis both visible ✓

**Known Issues (Backlog)**
- FEAT-20: Scheduler UI lacks Skill field → jobs created with empty skill_name/skill_prompt
- FEAT-21: FundamentalAnalyzer has dual history display (Sessions list + Verdict history); inconsistent with StorycheckER/ConsensusGap

**Commits**
- `c8e02b4` refactor: FundamentalAnalyzer — lean prompt + detailed UI display + retention
- `4d624a9` backlog: FEAT-20 — Scheduler Skill Config bug
- `301b015` backlog: FEAT-21 — Konsistenz Checker-History

### FundamentalAnalyzerAgent DB Persistence & Streamlit Caching Safeguards (DEBT-20, 2026-04-29)

**Complete DB persistence for FundamentalAnalyzerAgent + defensive safeguards against Streamlit @st.cache_resource footguns.**

**FundamentalAnalyzerAgent Persistence**
- Migrated from in-memory `Dict[str, AnalyzerSession]` to repository pattern (mirrors StorycheckerAgent)
- Added `FundamentalAnalyzerRepository` — new storage layer for sessions + messages
- Session IDs: `str` UUID → `int` (SQLite auto-increment)
- New tables: `fundamental_analyzer_sessions`, `fundamental_analyzer_messages`
- Sessions now survive app restarts; users can resume multi-turn chats from "Letzte Analysen"

**Streamlit @st.cache_resource Safeguards (DEBT-20)**
- **Problem identified**: @st.cache_resource caches resources for process lifetime. DB migrations only run once on startup. After code change adding new tables, running process never sees them → "no such table" errors
- **Solution**: Defensive logging in `state_db.py` shows which DB file is loaded and when migrations run
- **Integration test** (`test_db_schema_migration.py`) verifies all critical tables exist after `migrate_db()`
- **Documentation** in CLAUDE.md: Fallstricks + workarounds for Streamlit process caching
- **Deployment note**: After merges adding DB schema or agent signatures, Streamlit must be restarted

**Architecture Guard**
- New rule in ARCHITECTURE.md: Multi-turn chat agents MUST use DB persistence (not in-memory Dict)
- Prevents future agents from repeating in-memory anti-pattern

**Testing**
- 585 → 585 tests passing (3 removed in-memory AnalyzerSession tests, 0 new failures)
- New integration test: `test_db_schema_migration.py` validates 29 critical tables + foreign keys

### Flexible Public LLM Provider — OpenAI-Compatible Switch (2026-04-26)

**Global provider switch for cloud agents: OpenAI-compatible APIs (Perplexity Sonar, Groq, Together, OpenRouter) without code changes.**

- **OpenAICompatibleProvider** — new LLMProvider implementation for OpenAI-format APIs
- **Global switch**: Set `OPENAI_BASE_URL` in `.env` → all cloud agents automatically use OpenAI-compatible provider; Ollama agents unaffected
- **Configuration**: New env vars: `LLM_API_KEY` (replaces `ANTHROPIC_API_KEY`), `LLM_BASE_URL`, `LLM_DEFAULT_MODEL`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODELS`
- **Settings UI dynamic**: Cloud agent section shows "OpenAI-kompatibel 🌐" when `OPENAI_BASE_URL` active; reverts to "Claude ☁️" otherwise
- **Tool format handling**: Anthropic built-in tools (`web_search_20250305`) filtered; Anthropic custom tools converted to OpenAI function format
- **Backward compatible**: Without new vars, behavior identical to before (Claude + Ollama setup unchanged)
- **Testing**: 30 new unit tests for provider + tool conversion; 564+ tests passing

### Security Audit & RED TEAM Fixes (2026-04-24)

**Complete security hardening: Privacy audit + App red team testing. 7 findings fixed.**

**Privacy & Git Security**
- Git history cleaned: `wealth_data.db` permanently removed (was recoverable from commit `477cc3a`)
- Git history cleaned: `:memory:-shm` + `:memory:-wal` test files removed
- `.claude/settings.json` removed from tracking (contained personal paths `/Users/erik/...`)
- `.gitignore` hardened: Added `*.db` pattern + `.claude/settings.json`
- Remote force-pushed with cleaned history

**App Security: HIGH Priority (4 fixes)**
1. **Session Timeout & Logout** (`app.py`)
   - Added 8-hour session timeout (prevents unattended workstation access)
   - `auth_time` tracked on login, validated on every page load
   - Logout button in sidebar clears session state
   - Addresses: Unbeaufsichtigter PC = vollständiger Zugriff auf Finanzdaten

2. **YAML Injection Prevention** (`pages/analyse.py`)
   - Bargeldregel min/max_pct: Changed from `yaml.safe_load()` to string parsing + validation
   - User can no longer inject `min_pct: -999` to disable cash checks
   - Prevents logic manipulation via skill prompts

3. **LLM Prompt Injection Mitigation** (4 agent files)
   - `portfolio_agent.py`: Skills wrapped in `<skill_config>` tags
   - `structural_change_agent.py`: user_focus wrapped in `<user_focus>` tags
   - Added security note to system prompts: config data treated as untrusted
   - Signals to Claude that injected content is data, not instructions

4. **Exception Sanitization** (3 pages)
   - `storychecker.py`, `portfolio_chat.py`, `structural_scan.py`
   - Raw SDK exceptions no longer displayed to users
   - Detailed errors logged only; generic messages shown
   - Prevents leaking API state, auth tokens, portfolio data in error messages

**App Security: MEDIUM Priority (2 fixes)**
5. **Backup Script Security** (`~/scripts/wm_backup.sh`)
   - `.env` now encrypted before staging (was exposed in plaintext in `/tmp`)
   - Uses `openssl AES-256-CBC` with `ENCRYPTION_KEY` as passphrase
   - Stored as `.env.enc` in restic backup (double-encrypted: OpenSSL + Restic)
   - Restore documented: `openssl enc -aes-256-cbc -d -in .env.enc -out .env -k KEY`
   - Prevents plaintext secret exposure if backup process killed mid-run

**Testing & Verification**
- 562/562 tests passing (unchanged)
- 69% code coverage
- Session timeout verified (8h expiry triggers re-auth)
- YAML fix verified (min/max_pct validation works)
- Exception sanitization verified (no raw SDK strings in UI)

**Non-Fixed (Deliberate Design Decisions)**
- SQL f-strings in `usage.py`: Only internal constants, no user input → deferred
- Demo mode auth bypass: Config-dependent, not currently active
- setuptools CVE-2024-6345: Install-time only, runtime safe

---

### Schema Migration & App Startup Fixes (2026-04-23)

**Session 3 Completion + Infrastructure Robustness.**

- **Schema Migration: Nullable Stability Fields**
  - Fixed `sqlite3.IntegrityError: NOT NULL constraint failed: portfolio_story_analyses.stability_verdict`
  - Root cause: PortfolioStoryAgentV2 intentionally doesn't generate stability data (separate check), but schema enforced NOT NULL
  - Solution: Added migration in `core/storage/base.py` that recreates table with nullable stability columns
  - Handles both new installs and existing databases seamlessly

- **Improved Dock App Launcher (`start.command`)**
  - Previous: Terminal closed after Streamlit started → killed background process
  - Fixed: Use `nohup` to decouple Streamlit from terminal session
  - Added: Health check (polls `/_stcore/health` until server ready, max 10s)
  - Added: Auto-browser launch to `http://localhost:8501`
  - Added: Logging to `~/.wealth-management/streamlit.log` for debugging
  - Added: Validation that `.venv` exists with helpful error messages
  - Robust startup: Kills old instances cleanly before starting new one

- **Tests**: 562/562 passing (69.80% coverage)

---

### Watchlist Checker UX Refactor + Ollama Settings (2026-04-21)

**Watchlist Checker Section 1 auf Checkbox-Pattern umgebaut (analog Portfolio Story Check V2).**

- **Watchlist Checker Section 1 komplett neu**
  - Alte UI: Info-Box + 2 separate rote Buttons ("Story + Konsens starten", "Fundamental-Analysen starten")
  - Neue UI: Info-Meldungen (ausstehend + Timestamp) + 2 Checkboxen + 1 Haupt-Button
  - Checkboxen disabled wenn keine offenen Checks vorhanden
  - Pre-Checks laufen blocking (synchron im Spinner) vor dem Hauptcheck — analog `portfolio_story.py`
  - Nur offene Positionen werden gecheckt (Filter analog Portfolio Story)
  - Session-State-Polling-Block entfernt (nicht mehr nötig)
  - Fokus-Bereich Skill-Selector entfernt — `selected_skill=None` an Agent

- **Ollama Modellwahl in Settings**
  - `portfolio_story` und `watchlist_checker` als Ollama-Agents in Settings Page hinzugefügt
  - 3-spaltig statt 1-spaltig unter "Ollama Agents"

- **cloud_notice() Provider-Fix**
  - Zeigt jetzt `🏠 (lokal)` für Ollama-Agents statt `☁️ (Claude API)`
  - Watchlist Checker zeigt nun cloud_notice (war bisher nicht vorhanden)
  - `provider: str = "claude"` Parameter hinzugefügt (default für Claude-Agents unverändert)

- **Bug-Fix: WatchlistCheckerAgent max_tokens**
  - `max_tokens` von default 1024 → 4096
  - Root Cause: Bei 14 Positionen truncated der LLM die Antwort, Parser findet letzte Positionen nicht

- **Tests**: 566/566 passing

---

### Portfolio Story UX Refactor (2026-04-20, Part 2)

**Unified interface for Bargeldregel, Stabilitäts-Check, Story-Check with symmetric design.**

- **New UX Structure**
  - Section 2: Collapsed-by-default "Details & Einstellungen" expander
    - Skill selectors for Bargeldregel, Stabilitäts-Check, Story-Check
    - Josef-Vorschau-Metriken (Aktien/Renten/Rohstoffe %) visible when expanded
  - Main CTA: Always-visible row of 2 checkboxes + "🔄 Story-Check durchführen" button
    - `☑ 💰 Bargeldregel` (default True)
    - `☑ 🏛️ Stabilitäts-Check` (default True)
  - Results Zone: Unified display of all check results (Bargeldregel badge, Stabilitäts-Urteil, Story/Performance Urteile)
  - Section 3: Simplified nav buttons (no pre-checks checkbox/logic)

- **Symmetric Treatment of Checks**
  - Bargeldregel and Stabilitäts-Check now equal: both skill-based, both optional, both runnable via main button
  - Bargeldregel: upgraded from hard-coded YAML to skill-based (like Stability)
  - All 3 checks run on single button click in sequence: Bargeldregel → Stabilitäts-Check → Story-Check

- **Use Cases**
  - UC1 (Simple): Default load → click button → all 3 checks run
  - UC2 (Manual): Open Section 2 → adjust Skills/preview → click button → custom settings apply

- **Code Changes**
  - Removed 3 standalone renderer functions: `_render_cash_rule_check()`, `_render_stability_check()`, `_render_story_check()`
  - Consolidated logic into main button handler (~366 lines removed, net consolidation)
  - Bargeldregel logic now inline (YAML skill params → deterministic check)
  - All results stored in `session_state` with unified display

- **Tests**: 565/565 passing (no breakage from UX refactor)

### FEAT-18: Portfolio-Checker Modularisierung (2026-04-20)

**Split monolithic PortfolioStoryAgent.analyze() into modular, independently toggleable checks.**

- **Agent Refactor**: Split `analyze()` into two independent methods
  - `analyze_stability()` — LLM check for portfolio stability (Josef's Regel, Sektor-Limits, Geo-Streuung)
  - `analyze_story_and_performance()` — LLM check for story alignment + performance
  - `analyze()` remains as wrapper for backward compatibility
  
- **Skill Area Split**: Reorganized portfolio checks into three independent areas
  - `portfolio_cash_rule` — Bargeldregel (deterministic pre-check, optional if skill missing)
  - `portfolio_stability` — Josef's Regel, Sektor-Limits, Geo-Streuung (optional if no skill)
  - `portfolio_story` — Reserved for future Story-specific skills (e.g., DividendenCheck)
  - **Migration**: Existing user DBs auto-migrated on startup; existing skills moved to new areas

- **Page Refactor**: Section 2 (Portfolio Analysis) now modular with separate renderers
  - `_render_cash_rule_check()` — Updated to use `portfolio_cash_rule` area
  - `_render_stability_check()` — NEW: Skill selector + LLM button for stability analysis
  - `_render_story_check()` — NEW: Skill selector + LLM button for story/performance analysis
  - Each check shows info message if required skill not configured (graceful degradation)
  - Checks are independent: users can selectively enable/disable based on skills configured
  
- **Pattern**: Follows modular pattern established by position-level checkers (StorycheckerAgent, FundamentalAgent, ConsensusGapAgent)
  - Each check has its own skill area, allowing selective toggling
  - No skill → info message, not error; user can add skill via `/skills` page

- **DB Migration**: Automatic on first run
  - `UPDATE skills SET area='portfolio_cash_rule' WHERE name='Bargeldregel'`
  - `UPDATE skills SET area='portfolio_stability' WHERE name IN ('Josef's Regel...', 'Sektor-Limits...', 'Geographische Streuung...')`
  - Idempotent: existing migrations are skipped

- **Tests**: 564/564 passing; smoke tests for portfolio_story page verified

### Portfolio Story Bug Fixes (2026-04-19)

**Three linked bugs from user testing: SQLite path, auto-run recovery, Josef hallucination.**

- **Fixed SQLite `file is not a database`**: Relative DB paths now converted to absolute anchored on project root
  - Root cause: `.env` relative path `"data/portfolio.db"` resolved against wrong cwd when app launched from `.app` bundle
  - Solution: `_resolve_db_path()` helper in `config.py` ensures all DB paths absolute regardless of cwd or env override
  - Also fixed `salt.bin` path in `state_db.py`
  - Impact: App now starts without crashes when launched from any directory
  
- **Fixed Auto-Run from Portfolio Checker**: Automatically resolved by above fix
  - Storychecker batch jobs now trigger immediately when "→ Story Checker" button clicked
  - Root cause was SQLite error on line 37, blocking flag consumption at line 64

- **Fixed Josef's Regel hallucinating missing physical real estate**: Added explicit Immobilien section to portfolio snapshot
  - LLM now sees explicit list of physical Immobilien with values (if any exist)
  - Or explicit statement "keine im Portfolio" if none (prevents inference hallucination)
  - Verdict accuracy improved by anchoring LLM with facts instead of omission

- **Tests**: 564/564 passing, no regressions

### Position & Dividend Management Polish (2026-04-19)

**Resolved dividend override display issues and improved fund valuation handling.**

- **Fixed Dividend Overrides**: Dividend override calculations now use `cost_basis` as fallback when market price unavailable (e.g., bond funds without yfinance tickers)
  - Both auto-fetch and manual-valuation code paths updated
  - Fixes `TypeError: unsupported operand type(s) for *: 'float' and 'NoneType'` when `div_record.rate_eur` is None
- **Enhanced Funds Valuation**: `estimated_value` from detail dialog now used as fallback in auto-fetch code path
  - Allows funds without valid yfinance tickers to calculate P&L and dividends
  - Schätzwert (estimated value) input now visible for all fund classes in detail view
- **Config**: Enabled `manual_valuation: true` for Aktienfonds, Rentenfonds, Immobilienfonds, Infrastrukturfonds
  - Users can now set estimated position values in the detail dialog when market prices unavailable
- **Refactored**: Moved position story update from Story Checker page to position create/edit form
  - Story editing consolidated in dedicated position form (PositionStoryService)
  - Story Checker page now focused on analysis verdicts only
- **Tests**: 564/564 passing

### DEBT-10: Page Smoke Tests (2026-04-19)

**Streamlit UI smoke tests for all 19 pages — catches initialization crashes.**

- **Added**: `tests/integration/test_watchlist_checker_ui.py` — expanded from 5 pages to all 19
- **Coverage Impact**: Pages import triggers new code paths; coverage 76% → 69% (expected, acceptable)
- **Tests**: 564 total, all passing
- **Scope**: Agent pages (9), Admin & Dashboard (7), System pages (3)
- **Goal**: Safety layer for page refactoring — catches import errors, syntax errors, runtime crashes on startup

---

### Cleanup: Langfuse, Benchmark, Empfehlungs-Labels removed (2026-04-19)

**Removed experimental/unused features. No functional regressions.**

- **Removed Langfuse**: `monitoring/langfuse_client.py`, `monitoring/agentmonitor_helpers.py`, `pages/agentmonitor.py`, `docker-compose.yml`, `state_services.get_langfuse_client()`, config keys, health check, test files
- **Removed Benchmark**: `pages/benchmark.py`, `benchmark_runs` table (init_db + migrate_db), `UsageRepository.record_benchmark()` + `get_benchmark_runs()` + `get_benchmark_scenarios()`, navigation entry, test functions
- **Removed Empfehlungs-Labels**: Settings UI section (subheader + textarea + save), dropdown in Positionen/Watchlist. DB field `empfehlung` preserved; existing values kept silently.
- **Replaced Agent Monitor**: New "Letzte Calls" tab in Statistics page using existing `UsageRepository.get_recent_calls()`. Duration color-coded (🟢 <1s / 🟡 <3s / 🔴 ≥3s).
- **Tests**: 550 passing (down from 578; deleted test files account for the difference)

### Agent i18n Support (2026-04-17)

**Multi-language agent responses while preserving internal verdict codes.**

- **Added**: `agents/agent_language.py` with language instruction helpers
- **Changed**: 7 agents now accept `language` parameter (defaults to "de" for backward compatibility)
  - StorycheckerAgent, WatchlistCheckerAgent, ResearchAgent, StructuralChangeAgent
  - FundamentalAgent, ConsensusGapAgent, FundamentalAnalyzerAgent
- **Changed**: All 6 agent pages updated to pass `current_language()` to agent calls
  - Captures language in main thread before spawning background threads (session_state safety)
- **Design**: Verdict codes remain German (internal DB identifiers); only free-text output language-ized
  - `response_language_instruction()` for simple responses
  - `response_language_with_fixed_codes()` for agents with schema enums (fundamental, consensus_gap)
- **Tests**: 578/578 passing, no test changes needed (all default to "de")

---

### DEBT Stack Completion (2026-04-16)

**Complete architectural modernization: 3 technical debts resolved in 1 session.**

#### DEBT-9: Async Anti-Pattern Cleanup
- **Changed**: Replaced deprecated `asyncio.get_event_loop().run_until_complete()` → `asyncio.run()`
- **Files**: 2 agents (StorycheckerAgent, FundamentalAnalyzerAgent)
- **Impact**: Python 3.12+ compatible, modern async pattern

#### DEBT-7: God Module Decomposition
- **Changed**: state.py monolith (437 lines, 38 exports) → 5 focused modules + facade
  - `state_db.py`: DB + encryption initialization
  - `state_repos.py`: 17 repository factories
  - `state_llm.py`: LLM provider creation
  - `state_agents.py`: 15 agent factories (with logging fix)
  - `state_services.py`: 5 service factories
  - `state.py`: Pure re-export facade (nest_asyncio.apply() preserved)
- **Impact**: Zero disruption to 21 pages (all still use `from state import X`)
- **Tests**: All 573 passing, coverage maintained

#### DEBT-4: Service Layer + Agent Encapsulation
**Part A: Service Migration (4 pages)**
- `structural_scan.py`: 1 call → AnalysisService.get_verdicts()
- `positionen.py`: 1 call → AnalysisService.get_verdicts()
- `watchlist_checker.py`: 6 calls → AnalysisService + PortfolioService
- `portfolio_story.py`: 9 calls → AnalysisService + PortfolioService

**Part B: Agent Encapsulation (2 agents)**
- `WatchlistCheckerAgent`: Now owns persistence (wc_repo.save_analysis + agent_runs_repo.log_run)
- `PortfolioStoryAgent`: Now owns persistence (portfolio_story_repo.save_* + agent_runs_repo.log_run)
- `state_agents.py`: Updated factories to inject repos into agents

**Architecture Changes:**
- Pages are now thin UI layers (input → agent → display)
- Services centralize repository patterns (AnalysisService, PortfolioService)
- Agents encapsulate full lifecycle (analyze → persist → log)

#### Testing & Validation
- **Tests**: 573/573 passing, 77.55% coverage
- **Smoketest**: All 5 updated pages load without errors
- **Git**: 
  - Commit 5e69c3d: DEBT-4 completion (service migration + agent encapsulation)
  - Commit 4efc424: DEBT-9 + DEBT-7 (async cleanup + state decomposition)

#### Commits
```
5e69c3d refactor: DEBT-4 — Complete service migration + agent encapsulation
4efc424 refactor: DEBT-9 + DEBT-7 + DEBT-4 — async cleanup, state decomposition, service layer
```

---

### Skills Architecture Cleanup & Completion (2026-04-15)

**Major Refactor**: Completed 5-phase skills system restructuring with dead code elimination.

#### Phase-Based Implementation
1. **Phase 1**: Josef's Regel extraction to `core/portfolio_stability.py` (reusable module)
2. **Phase 2**: Deleted dead agents (rebalance_agent, investment_compass_agent) + related storage/pages/tests (7 files removed)
3. **Phase 3a**: YAML restructure — removed `rebalance` and `structural_scan` areas, kept 10 active areas
4. **Phase 3b**: WatchlistCheckerAgent skill support + UI selector (default=Standard, optional=Josef's Regel)
5. **Phase 3c**: PortfolioStoryAgent skill support + UI selector (default=Standard, optional=Josef's Regel)
6. **Phase 4**: Fundamental Analyzer navigation (removed duplicate fundamental.py, kept fundamental_analyzer.py)
7. **Phase 5**: Skills management page separation (System → Skills, removed from Settings)

#### Changes
- **Deleted**: 7 files (dead agents, pages, storage, tests)
- **Created**: 2 files (core/portfolio_stability.py, pages/skills.py)
- **Modified**: 11 files (agents, pages, state, app, YAML, tests)
- **Net Impact**: -292 lines code (dead code removal + test cleanup)

#### Fixed Issues
- ✅ Old skill areas (wealth_snapshot, rebalance) no longer appear in UI
- ✅ FundamentalAnalyzer session_id validation error (AsyncMock fix)
- ✅ Watchlist Checker results parsing (Standard option added)
- ✅ All FundamentalAnalyzer tests passing (21/21)

#### Testing & Validation
- **Tests**: 563/563 passing (all previously failing tests resolved)
- **Coverage**: 78.35% (improved from 77.95%)
- **UI Integration Testing**: Performed (3 issues caught: old YAML areas, async mocks, auto-selected skills)

### Fixed — Portfolio Story: Josef's Regel Comprehension (2026-04-13)
- **LLM prompt clarification**: Added explicit warning that three Säulen are independent and must NOT be summed together
- Previously LLM incorrectly calculated (e.g., "Aktien 40% + Rohstoffe 30% = 70% = too high")
- Now prompt clearly explains:
  - Säule 1 = Aktien, Säule 2 = Renten/Geld, Säule 3 = Rohstoffe + Immobilien TOGETHER
  - Crisis-protection works because in any scenario, at least one Säule stabilizes or grows
  - 1/3 distribution IS the strength, not a problem to fix
- Restructured stability assessment to evaluate each Säule independently with deviation metrics

### Technical Debt Remediation (2026-04-12)

**Status**: 10 of 16 debt items completed. See [BACKLOG.md § Technische Schulden](BACKLOG.md) for full inventory.

#### Completed ✅
- [DEBT-14] agentmonitor.py wired to navigation
- [DEBT-15] Expired Easter egg removed
- [DEBT-16] O(n) deletes replaced with batch SQL operations
- [DEBT-11] Coverage configuration added to pytest.ini
- [DEBT-3] core/constants.py created; all 8 files updated with model imports (benchmark, positionen, app_config, usage)
- [DEBT-6] Public agent APIs (model property, get_latest_fetch_time, get_historical) — eliminated private attribute access from pages
- [DEBT-5] Position story proposal extraction to PositionStoryService with usage tracking
- [DEBT-1] DDL duplication removed (usage_resets, dividend_data from migrate_db)
- [DEBT-2] Legacy portfolio/watchlist tables removed from init_db (verified unused in production)

#### Planned 📋
- [DEBT-4] Service layer extraction (high effort, separate session)
- [DEBT-7] Decompose state.py (high effort, separate session)
- [DEBT-8] migrate_db() documentation
- [DEBT-9] Async anti-pattern (nest_asyncio) — high effort
- [DEBT-10] Page unit tests (blocked by DEBT-4)
- [DEBT-12] peewee dependency (transitive, no action needed)
- [DEBT-13] requirements.txt version bounds (low risk)

### Added

- Documentation: Structured documentation framework (CLAUDE.md, ARCHITECTURE.md, BACKLOG.md as Single Source of Truth)
- Memory system for session persistence and debugging context
- Architektur-Guards section (anti-patterns to prevent)
- Technical Debt tracking in CHANGELOG for visibility

---

## [1.6.0] — 2026-04-11

### Added — Portfolio Story: Role-Based Story Fits

**Per-Position Story Assessment**
- New **role-based verdict system** for portfolio positions: 5 roles instead of 3 verdicts
  - 🔵 **Wachstumsmotor** (Growth Engine) — capital appreciation
  - 🟡 **Stabilitätsanker** (Stability Anchor) — downside protection
  - 🟢 **Einkommensquelle** (Income Source) — dividends/interest
  - 🟣 **Diversifikationselement** (Diversification) — non-correlated
  - 🔴 **Fehlplatzierung** (Misallocation) — doesn't fit story
- **Story-first assessment**: Portfolio narrative is primary, fundamentals are confirmatory
- Batch check all positions in Storychecker with background job + auto-refresh (5s interval)

**Position Story Updates**
- New "📝 Position-Story aktualisieren" button in Storychecker
- Generate story proposals on-demand (independent of check context)
- Expander UI pattern for compact, collapsible story display
- Iterative workflow: update → auto-applied to next analysis

### Fixed

- StorycheckerRepository now correctly loads verdicts from position_analyses table
- Position story UI now full-width below narrative text
- Helper functions moved to correct positions in file (fixes runtime errors)

---

## [1.5.0] — 2026-04-10

### Added — Wealth Snapshots & Historical Wealth Tracking

**New Wealth Assistant Page**
- Capture wealth snapshots on-demand with optional notes
- Automatic asset class breakdown (Aktie, Immobilie, Festgeld, Rohstoffe, etc.)
- Coverage tracking — percentage of positions with valid valuations
- Stale valuation detection — identifies manual positions >30 days old

**Snapshot Management**
- **Take Snapshot** — capture current wealth state
- **Prepare** — preview calculation, detect stale valuations
- **Edit** — modify asset class values retroactively
- **Delete** — remove incorrect snapshots
- **Overwrite** — replace existing snapshot

**Dashboard Integration**
- New **Wealth Timeline** visualization on dashboard
- Line chart + optional stacked area breakdown by asset class
- Historical wealth trend analysis

**Data Model & Testing**
- New `wealth_snapshots` table with JSON breakdown and coverage tracking
- 6 new test classes (edit, delete, overwrite scenarios)
- 523 → 527 tests passing

### Added — Currency & Valuation Improvements

- **BASE_CURRENCY** config (default EUR) for flexible currency display
- Display-only currency conversion without changing stored values
- **Infrastrukturfonds** asset class added to taxonomy
- **Estimated value fields** for manual asset classes in position creation
- **Dividend yield override** for manual dividend corrections
- **Expected annual dividend & interest income** tracking

### Added — Cost Forecasting & Validation

- Exact position count tracking for accurate cost forecasts (vs. estimates)
- Input validation for new positions (positive quantity, valid dates, ticker format)
- Auto-fetch market data on position creation (non-blocking fallback)
- Cost alert system for LLM usage thresholds

### Changed

- Wealth Timeline snapshots clarified as **manual**, not automatic
- Structured logging infrastructure for better observability
- Lazy agent initialization to reduce startup overhead
- Removed ANTHROPIC_BASE_URL and corporate proxy support

### Fixed

- Asset class snapshot breakdown now includes all classes even with zero values
- Comprehensive audit and cleanup of wealth_assistant.py
- All translation function calls corrected (t() usage)
- Correct YAML indentation in default_skills.yaml

---

## [1.4.0] — 2026-04-08 to 2026-04-09

### Added — Consensus Gap & Structural Analysis

**ConsensusGap Agent (Claude ☁️)**
- Identifies positions where market consensus diverges from fundamental value
- Verdicts: wächst | stabil | schließt | eingeholt
- Tool-use integration for robust parsing
- Verdicts stored in position_analyses for Rebalance context

**Structural Change Scanner (Claude ☁️)**
- Monthly web-search scan for structural market themes before consensus catches up
- Auto-adds candidates to watchlist
- Identifies second-order effects of major shifts

**Rebalance Integration with Cloud Agents**
- Rebalance snapshot now includes Fundamental Value and Consensus Gap signals
- Watchlist candidates enriched with cloud agent verdicts
- Graceful handling of missing analyses (skips signal if unavailable)

**Storychecker Enhancements**
- Batch check all positions simultaneously with background job
- Auto-refresh every 5 seconds during batch analysis
- Error counting and display in completion message

### Added — Investment Management

**Investment Search Agent (Cloud ☁️)**
- Tavily-powered search for investment opportunities
- Story auto-capture: investment rationale stored as position story
- Recommendation source tracking

**Portfolio Agent Improvements**
- Auto-validates new watchlist candidates with StorycheckerAgent
- Watchlist candidates now appear in Rebalance with story + signals
- Validation: positive quantity/price, purchase date not future, ticker format

### Added — Settings & Model Selection

**Model Selection Per Agent**
- `CLAUDE_MODELS` from environment (default: all three models)
- Agent-specific model overrides (read from AppConfigRepository)
- Settings page: 2 Ollama dropdowns + 3 Claude dropdowns
- Cache invalidation on model changes

**Default Skills Framework**
- Warren Buffett, Norwegischer Pensionsfonds, André Kostolany investment strategies
- Josef's Regel as hidden system skill for Invest/Rebalance
- Skills repository seeding with area-specific defaults

### Fixed

- Josef's Regel categorization: Immobilien now combined with Rohstoffe (not separate)
- Crypto added to Rohstoffe category (not separate)
- Watchlist-only positions excluded from rebalancing analysis
- Precious metals gram unit conversion (e.g., XAU)
- GBX pence bug (100x inflation for UK stocks)
- DEMO_MODE unencrypted warning (P0 security)
- Silent error swallowing in error handling

### Technical

- Agent-to-agent orchestration: structural scan auto-triggers story check on new candidates
- Tavily prompt-injection defense + LLM output validation
- Portfolio valuation accuracy improvements

---

## [1.3.0] — 2026-03 to early 2026-04

### Added — Fundamental Value Agent

**FundamentalAgent (Claude ☁️) — Säule 3**
- KGV, P/B, EV/EBITDA, DCF, PEG, analyst price targets
- Verdicts: unterbewertet | fair | überbewertet | unbekannt
- Fair Value (EUR) and Upside (%) in position_analyses
- Web search integration for analyst consensus
- Skills: Fundamentalbewertung Standard, Dividendenbewertung
- Default model: Sonnet (requires web_search_20250305)

### Added — Story Checker Agent & Investment Narrative

**StorycheckerAgent (Claude ☁️)**
- Analyzes investment theses for story integrity and thesis alignment
- Session-based chat for iterative refinement
- Verdicts guide position allocations in portfolio
- Integration with Portfolio Story for narrative coherence

**Portfolio Story Framework**
- Narrative-driven portfolio analysis page
- Investment thesis editor for capturing portfolio rationale
- Story-fit assessment for each position
- Stability criteria including Josef's Rule + dividend analysis

### Added — Scheduling & Automation

**APScheduler Integration**
- Background job scheduling for agents (News, Story Checker, etc.)
- `scheduled_jobs` table for job persistence
- `AgentSchedulerService` with dedicated background scheduler
- Settings page: enable/disable, modify frequency, delete jobs
- Skills selection per scheduled job

**Demo Mode & Seed Data**
- Full demo portfolio with realistic scenarios
- Seed demo analyses for all agent types
- [Demodaten] markers for demo-generated content

### Added — macOS Integration

- Native macOS app bundle with icon
- Apple Passwords integration (optional app password authentication)
- Username field in login form for Keychain differentiation

### Fixed

- Position detail dialog refresh issues
- Dialog close button functionality
- Rebalance session crash without error message (wrapped in try/except)
- DB migration: OperationalError on in_watchlist index
- Duplicate key error when position in portfolio AND watchlist simultaneously
- Löschen von Watchlist springt auf Portfolio (tab layout persistence)

---

## [1.2.0] — 2026-02 to 2026-03

### Added — Internationalization & Multi-Language Support

- **i18n infrastructure** (de/en)
- YAML-based translation files (694 lines German, 688 lines English)
- Dynamic language switching in Settings
- Bilingual UI across all pages and agents

### Added — Rebalancing & Investment Guidance

**RebalanceAgent (Private 🔒 — Ollama)**
- Rebalancing recommendations aligned with Josef's Regel
- Watchlist candidate integration for portfolio building
- Geld/Immobilien handling (non-tradeable vs. liquid assets)
- Position exclusion from rebalancing analysis

**Investment Management Features**
- Position "exclude from rebalancing" toggle
- Money & Real Estate handled separately in snapshots
- Watchlist candidates appear as purchase recommendations

### Added — Admin & Monitoring

**Settings Page Redesign**
- Model selection (Ollama local, Claude cloud)
- Health checks (Anthropic API, Ollama availability, Database)
- Cost tracking and alert configuration
- Skill editor for custom prompts

**System Monitoring (Langfuse)**
- Optional Langfuse integration for LLM tracing
- Agent execution monitoring
- Cost tracking dashboard
- Docker Compose stack for Langfuse (Postgres, ClickHouse, Redis, MinIO)

### Fixed

- Story-Skill-Selector always disabled (removed from st.form)
- Dashboard sum calculation (Geld-Anlagen with manual_valuation)
- Decimal formatting: Punkt → Komma (German locale)
- Recommendation source visibility and form integration
- Name not prefilled from ticker search (FIGI lookup)
- No feedback after saving position (added _pos_just_saved flag)
- Streamlit deploy button hidden (config.toml: toolbarMode = minimal)

### Technical

- System Health checks (static + dynamic)
- Langfuse Docker Compose for observability
- Structured logging

---

## [1.1.0] — Early 2026

### Added — Research & Analysis Infrastructure

**Research Agent (Cloud ☁️)**
- Claude-powered stock research with web search
- Session-based chat interface
- Company analysis and investment memo generation

**News Agent (Cloud ☁️)**
- Daily news digest per portfolio position
- LLM-summarized market context
- One-shot stateless execution

**Portfolio Chat**
- Natural language interface to portfolio CRUD
- Validation + confirmation flow for additions
- Ollama-powered with tool-use

**Performance Analytics**
- Historical performance analysis page
- Day PnL tracking (current value - previous close)
- Performance charts by position
- Benchmark comparisons

### Added — Data Management & Market Data

**MarketDataAgent (Private 🔒)**
- yfinance integration for price updates
- Automatic fetch on position creation
- Rate limiting and error handling

**Market Data Features**
- Manual fetch triggers
- Historical data API (daily close prices)
- Previous close tracking for daily PnL
- Currency conversion support

### Fixed

- Positions table alphabetical sorting
- Portfolio → Watchlist tab persistence
- Duplicate key errors with position IDs

---

## [1.0.0] — Initial Release

### Added — Core Portfolio Management

**Portfolio Pages**
- Portfolio CRUD (Create, Read, Update, Delete)
- Position management with ticker search (FIGI API)
- Watchlist for tracking potential investments

**Dashboard & Analytics**
- Portfolio overview with KPIs
- Asset allocation visualization
- Market data display
- Performance snapshots

**Agent Framework**
- LLM provider abstraction (Claude + Ollama)
- Session-based chat agents
- Tool-use for structured outputs
- SQLite-backed persistence

**Storage & Security**
- Fernet encryption for sensitive fields (quantity, price, notes, story)
- PBKDF2 key derivation from master password
- SQLite with WAL mode for concurrency
- Repository pattern for data access

**Configuration & Deployment**
- Environment-based configuration
- Multi-environment support (.env.work, .env.prod)
- Demo mode for testing
- Health checks for system readiness

### Technical Foundation

- Streamlit UI framework
- Python 3.9+ with async support
- Anthropic SDK for Claude API
- yfinance for market data
- Encryption: cryptography library
- Testing: pytest with async support

---

[Unreleased]: https://github.com/esc1899/wealth_management/compare/v1.6.0...HEAD
[1.6.0]: https://github.com/esc1899/wealth_management/releases/tag/v1.6.0
[1.5.0]: https://github.com/esc1899/wealth_management/releases/tag/v1.5.0
[1.4.0]: https://github.com/esc1899/wealth_management/releases/tag/v1.4.0
[1.3.0]: https://github.com/esc1899/wealth_management/releases/tag/v1.3.0
[1.2.0]: https://github.com/esc1899/wealth_management/releases/tag/v1.2.0
[1.1.0]: https://github.com/esc1899/wealth_management/releases/tag/v1.1.0
[1.0.0]: https://github.com/esc1899/wealth_management/releases/tag/v1.0.0
