# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added

- Documentation: Structured documentation framework (CLAUDE.md, ARCHITECTURE.md, BACKLOG.md as Single Source of Truth)
- Memory system for session persistence and debugging context

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
