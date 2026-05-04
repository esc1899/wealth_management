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

### Features

| ID | Priority | Type | Description | Status | Session |
|---|---|---|---|---|---|
| FEAT-17 | P2 | [IMPR] Terminology & Chart | Rename "Investment-Typ" → "Anlageklasse" (UI only); add Sunburst chart (Anlageklasse innen, Anlageform außen) | ✅ DONE | 2026-04-20 |
| FEAT-18 | P2 | [IMPR] Portfolio-Checker Refactor | Split monolithic PortfolioStoryAgent into modular, optional checks (CashRule, Stability, Story) — parallel to Position-Checkers pattern | ✅ DONE | 2026-04-20 |
| FEAT-19 | P2 | [IMPR] UI Unification — Agent Pages | Unified UX for Consensus Gap + Fundamental Analyzer to match Storychecker gold standard: help expanders, batch sections with pending/total counts, 2-column layouts, current/older output splits, error handling | ✅ DONE | 2026-04-26 |
| FEAT-20 | P2 | [BUG] Scheduler Skill Config — FundamentalAnalyzer | Root-cause analysis: Scheduler UI has no Skill field → jobs created with empty skill_name/skill_prompt. When batch runs, unclear what skill is used or if it crashes. Need: full trace through analyze_portfolio() → start_session() → _resolve_skill() to understand fallback logic. Then either: (A) add Skill field to Scheduler UI, or (B) implement smart default in analyze_portfolio(). | 🔲 TODO | 2026-05-04 |

### Technical Debt

| ID | Priority | Description | Notes |
|---|---|---|---|
| DEBT-17 | P2 | Agent LLM Config — Explicit Thinking + Effort | Sonnet 4.6: set `thinking: {type: "adaptive", display: "summarized"}` + `output_config: {effort: "high"}` in ClaudeProvider.chat(). Currently: thinking runs implicitly, output limited by 1024-token overhead. Will reduce multi-turn loops (~50% token savings), longer answers. Investigate after next test cycle. |
| DEBT-8 | P3 | Document `migrate_db()` inline — add comments explaining the dual init+migrate pattern | Low risk, cosmetic |
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
| DEBT-10 | 2026-04-19 | Page smoke tests — all 19 pages load without exceptions (Streamlit AppTest) |
| DEBT-11 | 2026-04-12 | Coverage configuration added to pytest.ini |
| DEBT-14 | 2026-04-12 | agentmonitor.py wired to navigation |
| DEBT-15 | 2026-04-12 | Expired Easter egg removed |
| DEBT-16 | 2026-04-12 | O(n) deletes replaced with batch SQL operations |
| DEBT-18 | 2026-04-29 | FundamentalAgent consolidated into FundamentalAnalyzerAgent; deleted old agent module |
| DEBT-19 | 2026-04-29 | Token caching infrastructure removed (enable_cache parameter, cache_control blocks) — uneconomical for web-search agents |
