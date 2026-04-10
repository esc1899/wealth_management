# Changelog

All notable changes to this project are documented here. The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added — Wealth Snapshots Feature (April 10, 2026)

**Historical Portfolio Wealth Tracking**
- New **Wealth Assistant** page for managing portfolio wealth snapshots
- Automatic daily snapshots with asset class breakdown (Aktie, Immobilie, Festgeld, etc.)
- Dashboard **Wealth Timeline** visualization — line chart + optional stacked area by asset class
- Snapshot coverage tracking — percentage of positions with valid values; warnings for incomplete data
- Stale valuation detection — identifies manual positions >30 days old without updates

**Snapshot Management**
- **Take Snapshot** — capture current wealth state on demand with optional note
- **Prepare** — preview wealth calculation, detect stale valuations, check data completeness
- **Edit Snapshots** — modify individual asset class values retroactively; total recalculates automatically
- **Delete Snapshots** — remove incorrect snapshots
- **Overwrite** — replace existing snapshot if corrections needed; triggered via confirmation dialog
- Manual valuation updates for real estate, land, fixed deposits, and other non-tradeable assets

**Data Model**
- New `wealth_snapshots` table with coverage tracking, asset breakdown, and manual flag
- JSON storage for breakdown and missing positions list
- Immutable snapshots — corrections via update() with audit trail via is_manual flag
- Scheduler support for automatic daily snapshots

**Testing**
- 6 new test classes covering edit, delete, overwrite scenarios
- Edge cases: None values in stale positions, empty portfolios, all positions missing values
- Total 523 tests passing

### Fixed — April 10, 2026

- Comprehensive audit and cleanup of `wealth_assistant.py`
- Removed LLM chat section (complexity not justified; core snapshot management is the focus)
- Fixed all translation function calls (`t()`)
- Streamlined UI focused on snapshot management operations

### Technical Details

**Files Added**
- `agents/wealth_snapshot_agent.py` — agent for snapshot logic (take, prepare, edit, delete)
- `core/storage/wealth_snapshots.py` — repository for snapshot CRUD
- `pages/wealth_assistant.py` — UI for snapshot management
- `pages/dashboard.py` — wealth timeline visualization

**Files Modified**
- `core/storage/base.py` — added `wealth_snapshots` table schema
- `core/storage/models.py` — added `WealthSnapshot` dataclass
- `core/scheduler.py` — added wealth snapshot job handler
- `app.py` — registered Wealth Assistant page in navigation
- `config/default_skills.yaml` — added wealth_snapshot skill
- `translations/de.yaml`, `en.yaml` — added UI strings
- `tests/test_wealth_snapshot_agent.py` — added comprehensive test coverage

**Architecture**
- Reuses `MarketDataAgent.get_portfolio_valuation()` for deterministic snapshot calculation
- `@st.dialog` pattern for edit/overwrite confirmations (per codebase conventions)
- Session state management for edit dialogs
- Integration with existing scheduler for automatic snapshots

---

## Release Notes

### v1.0.0 (Previous stable release)
See git log for prior changes.
