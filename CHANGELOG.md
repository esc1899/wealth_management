# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

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
