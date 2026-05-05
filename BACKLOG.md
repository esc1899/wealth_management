# Backlog

Personal planning overview. User feedback and bug reports: [GitHub Issues](https://github.com/esc1899/wealth_management/issues)

## Legend
- `[P1]` High / `[P2]` Medium / `[P3]` Low
- `[BUG]` Bug / `[FEAT]` Feature / `[IMPR]` Improvement / `[DEBT]` Technical Debt

---

## In Progress

(None)

---

## Planned

### Features

| ID | Priority | Type | Description | Status | Session |
|---|---|---|---|---|---|
| FEAT-17 | P2 | [IMPR] Terminology & Chart | Rename "Investment-Typ" → "Anlageklasse" (UI only); add Sunburst chart (Anlageklasse innen, Anlageform außen) | ✅ DONE | 2026-04-20 |
| FEAT-18 | P2 | [IMPR] Portfolio-Checker Refactor | Split monolithic PortfolioStoryAgent into modular, optional checks (CashRule, Stability, Story) — parallel to Position-Checkers pattern | ✅ DONE | 2026-04-20 |
| FEAT-19 | P2 | [IMPR] UI Unification — Agent Pages | Unified UX for Consensus Gap + Fundamental Analyzer to match Storychecker gold standard: help expanders, batch sections with pending/total counts, 2-column layouts, current/older output splits, error handling | ✅ DONE | 2026-04-26 |
| FEAT-20 | P2 | [BUG] Cost Tracking — Web-Search Requests Not Logged | Root-cause: Statistics page shows $5.20 but Anthropic charges $8.13. Missing: Web-Search API charges ($10 per 1,000 searches) not tracked in llm_usage. Solution: Add web_search_requests column to llm_usage, extract from API response, update cost calculation. Estimated ~40 min. | ✅ DONE | 2026-05-04 |
| FEAT-21 | P2 | [BUG] Scheduler Skill Config — FundamentalAnalyzer | Root-cause analysis: Scheduler UI has no Skill field → jobs created with empty skill_name/skill_prompt. When batch runs, unclear what skill is used or if it crashes. Need: full trace through analyze_portfolio() → start_session() → _resolve_skill() to understand fallback logic. Then either: (A) add Skill field to Scheduler UI, or (B) implement smart default in analyze_portfolio(). | ✅ DONE | 2026-05-05 |
| FEAT-22 | P2 | [IMPR] Einheitliche Checker-Darstellung (FA, SC, CG) | Alle 3 Checker zeigen jetzt Ergebnisse mit gleichem Detailgrad: Full-Text expandable (via session_id oder analysis_text) + Inline-History rechts. Linke Session-Listen entfernt. Datengrundlage: CG speichert jetzt auch analysis_text (das `analysis`-Feld aus Tool-Call). Pages: fundamental_analyzer, storychecker, consensus_gap. Tests: 601 passing. | ✅ DONE | 2026-05-05 |
| FEAT-23 | P2 | [IMPR] News Agent — Einheitliche Darstellung | News Agent hat separate Datenstruktur (NewsRun, nicht position_analyses). Soll nach FA-Muster: Full-Text expandable + History. Entscheidung erforderlich: per-Run-History oder per-Ticker-History? Separate Session für News? Komplexere Änderung — später. | 🔲 TODO | 2026-05-05 |
| FEAT-24 | P2 | [FEAT] Scheduler Job Logs | Show execution history for scheduled jobs in Settings UI. User needs visibility into: (1) when job last ran, (2) if it succeeded or failed, (3) error messages if failed. Implementation: new DB table `scheduled_job_runs(id, job_id, status, started_at, completed_at, error_msg)`, ScheduledJobRunsRepository, UI under each job in settings.py with "Last run: [timestamp] [status icon] [error details]". Status quo: only `last_run` timestamp visible, no failure tracking. | 🔲 TODO | 2026-05-04 |
| FEAT-25 | P2 | [FEAT] Position-Analysis Dashboard | Single page/modal that aggregates all verdicts for a selected position: Storychecker, Consensus Gap, Fundamental Analyzer, Watchlist Checker Fit, News Digest (tickers). Show all analyses side-by-side with unified format (icon + verdict + summary + full-text expandable). Two implementation options: (A) new page "Position Details" (similar to current Positionen), (B) inline panel in Portfolio Story (click position → shows analysis summary). Also usable as foundation for Portfolio Chat "tell me why you think this is good" → cite all checkers' verdicts. | 🔲 TODO | 2026-05-05 |
| FEAT-26 | P2 | [IMPR] ConsensusGap Sessions — Full-Text Persistence | CG Agent currently stores only Tool-Call fields (verdict, summary, analysis_text) but discards response.content (the LLM's freetext analysis). Solution: Add `consensus_gap_sessions` + `consensus_gap_messages` tables (like SC/FA pattern), make CG create sessions, store full response as assistant-message, reference session_id in position_analyses. Then CG will match SC/FA pattern exactly: Full-Text retrieved via session_id instead of analysis_text field. Impact: unified UX + proper data persistence. | 🔲 TODO | 2026-05-05 |

### Technical Debt

| ID | Priority | Description | Notes |
|---|---|---|---|
| DEBT-17 | P2 | Agent LLM Config — Explicit Thinking + Effort | Sonnet 4.6: set `thinking: {type: "adaptive", display: "summarized"}` + `output_config: {effort: "high"}` in ClaudeProvider.chat(). Currently: thinking runs implicitly, output limited by 1024-token overhead. Will reduce multi-turn loops (~50% token savings), longer answers. Investigate after next test cycle. |
| DEBT-8 | P3 | Document `migrate_db()` inline — add comments explaining the dual init+migrate pattern | Low risk, cosmetic |
| DEBT-13 | P3 | Tighten requirements.txt version bounds | Low urgency, no known conflicts |

---

## Completed

See CHANGELOG.md for full history of completed features and debt remediations.

### Bugs — Completed ✅

| ID | Completed | Description |
|---|---|---|
| BUG-1 | 2026-05-04 | Scheduler Catchup Not Running — Root cause: inverted condition in grace_period check (`<=` vs `>`). Fixed with test-first approach (7 scenarios), enhanced to run new jobs immediately, optimized to background thread. All 594 tests passing. |
| BUG-2 | 2026-05-04 | Scheduled Batch Jobs — Watchlist + analysis_excluded Ignored — Two issues: (A) Consensus Gap, Storychecker, Fundamental were including watchlist-only positions (should be portfolio only); (B) all 6 agents ignored analysis_excluded field. Both fixed with position filtering in scheduler + agent. Added 7 integration tests. 601 tests passing. |
| FEAT-20 | 2026-05-04 | Cost Tracking — Web-Search Requests Not Logged — Root cause: Anthropic charges for web_search_requests ($10/1000 = $0.01/request) but these weren't logged. Solution: Added web_search_requests column to llm_usage, extract from API response in chat_with_tools(), updated cost calculation. Statistics now match Anthropic billing exactly. |
| FEAT-22 | 2026-05-05 | Einheitliche Checker-Darstellung (FA, SC, CG) — Alle 3 Checker zeigen jetzt Ergebnisse mit gleichem Detailgrad: Full-Text expandable + Inline-History rechts. Datenlücke bei CG geschlossen (analysis_text Spalte). Linke Session-Listen entfernt (FA + SC). 601 tests passing. |

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
