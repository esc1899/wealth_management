# Backlog

Personal planning overview. User feedback and bug reports: [GitHub Issues](https://github.com/esc1899/wealth_management/issues)

## Legend
- `[P1]` High / `[P2]` Medium / `[P3]` Low
- `[BUG]` Bug / `[FEAT]` Feature / `[IMPR]` Improvement / `[DEBT]` Technical Debt

---

## In Progress

*(empty)*

---

## Planned

### Technical Debt

| ID | Priority | Description | Notes |
|---|---|---|---|
| DEBT-8 | P3 | Document `migrate_db()` inline — add comments explaining the dual init+migrate pattern | Low risk, cosmetic |
| DEBT-10 | P2 | Page unit tests — smoke-test page rendering without real agents (mock at service boundary) | Unblocked since DEBT-4 complete |
| DEBT-13 | P3 | Tighten requirements.txt version bounds | Low urgency, no known conflicts |

---

## Completed

See CHANGELOG.md for full history of completed features and debt remediations.

### Technical Debt — Completed ✅

| ID | Completed | Description |
|---|---|---|
| DEBT-1 | 2026-04-12 | DDL duplication removed (usage_resets, dividend_data from migrate_db) |
| DEBT-2 | 2026-04-12 | Legacy portfolio/watchlist tables removed from init_db |
| DEBT-3 | 2026-04-12 | core/constants.py created; all 8 files updated with model imports |
| DEBT-4 | 2026-04-16 | Service Layer + Agent Encapsulation (AnalysisService, PortfolioService) |
| DEBT-5 | 2026-04-12 | Position story proposal extraction to PositionStoryService |
| DEBT-6 | 2026-04-12 | Public agent APIs — eliminated private attribute access from pages |
| DEBT-7 | 2026-04-16 | state.py decomposed (437 → 60 lines + 5 modules) |
| DEBT-9 | 2026-04-16 | asyncio.get_event_loop() → asyncio.run() (Python 3.12+ safe) |
| DEBT-11 | 2026-04-12 | Coverage configuration added to pytest.ini |
| DEBT-14 | 2026-04-12 | agentmonitor.py wired to navigation |
| DEBT-15 | 2026-04-12 | Expired Easter egg removed |
| DEBT-16 | 2026-04-12 | O(n) deletes replaced with batch SQL operations |
