# Backlog

Personal planning overview. User feedback and bug reports: [GitHub Issues](https://github.com/esc1899/wealth_management/issues)

## Legend
- `[P1]` High / `[P2]` Medium / `[P3]` Low
- `[BUG]` Bug / `[FEAT]` Feature / `[IMPR]` Improvement / `[DEBT]` Technical Debt

---

## In Progress

(None)

---

## Bekannte Probleme (nicht dringend)

| ID | Entdeckt | Beschreibung |
|---|---|---|
| NOTE-1 | 2026-06-06 | ~~**Tavily Monats-Limit erschöpft**~~ — Plan-Limit erhöht (2026-06-07). Verbrauch zusätzlich optimiert: search_depth=basic (alle außer FA), client-side max_uses-Enforcement, fehlende Limits nachgerüstet, NewsAgent-Formel gekappt. ✅ ERLEDIGT |
| NOTE-2 | 2026-06-06 | **SCANFL delisted/nicht gefunden** — yfinance liefert 404 für Symbol SCANFL. Position prüfen: Ticker noch aktuell? Ggf. aus Portfolio/Watchlist entfernen oder Ticker korrigieren. |

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
| FEAT-23 | P2 | [IMPR] News Agent — Einheitliche Darstellung | News Agent Layout refactored to match FA/SC/CG pattern: Left panel (form only) + Right panel (auto-loaded digest expander + older runs inline-history + chat). Root cause fix: removed run-list from left panel, added auto-load of latest run. Storage layer (NewsRun/NewsMessages) unchanged. 617 tests passing. | ✅ DONE | 2026-05-05 |
| FEAT-28 | P2 | [FEAT] Lindy Effect Scanner — Search Skill | Neuer Search-Skill "Lindy Effect Scanner" im SearchAgent (kein neuer Agent nötig). Findet Unternehmen mit Lindy-Eigenschaften: >50 Jahre alt + noch wachsend, Krisen 2008+2020 überlebt, "Boring" businesses mit 20+ Jahren Dividendenhistorie. Output: Kandidaten-Report mit Lindy-Verdict (`stark`/`moderat`/`schwach`). Kein Kauf-/Verkauf-Rat, nur Entdeckung. Implementierung: Eintrag in `default_skills.yaml` search-Bereich + `seed_new_skills("search")` in state_repos.py. | ✅ DONE | 2026-05-07 |
| FEAT-29 | P2 | [FEAT] Capital Allocator Quality Agent | Bewertet die Qualität des Managements als Kapitalallokator — nicht das Unternehmen selbst. Prüft: (1) Historische Entscheidungen: Buybacks zu welchen Preisen, M&A-Track-Record, Dividendenpolitik; (2) Insider-Ownership + Anreizstrukturen; (3) Kommunikation: Sagen sie was sie tun und tun sie was sie sagen? Output: "Capital Allocator Scorecard" pro Position. Kein Kauf-/Verkauf-Rat, nur Transparenz über Management-Qualität. Tools: web_search für Earnings-Calls, Proxy Statements, historische Entscheidungen. Verdict: `exzellent` / `solide` / `fragwürdig` / `destruktiv`. Implementiert als FundamentalAnalyzer-Skill (kein neuer Agent). | ✅ DONE | 2026-05-07 |
| FEAT-30 | P2 | [FEAT] Narrative Shift Detector Agent | Erkennt wenn sich die "Story" um ein Unternehmen in Medien/Analysten-Berichten fundamental ändert — bevor sich das im Kurs zeigt. Vergleicht aktuelle Berichterstattung mit historischem Narrativ. Sucht nach: (1) Tonalitäts-Shifts (z.B. "Growth" → "Value"), (2) neue Themen die vorher nie erwähnt wurden, (3) Analyst-Upgrades/Downgrades mit neuer Begründung. Output: "Narrative Timeline" — wie hat sich die Story über 6–12 Monate verändert? Kein Kauf-/Verkauf-Rat, nur Bewusstmachung. Tools: web_search für News-Archiv, Analysten-Reports. Verdict: `positiver_shift` / `stabil` / `negativer_shift` / `pivot`. Implementiert als SearchAgent-Skill (kein neuer Agent). | ✅ DONE | 2026-05-07 |
| FEAT-32 | P1 | [FEAT] Cowork Research Ingest — UX-Klärung & Dialog-Completion | Fundament + UX vollständig. Proposal Panel (Checkbox-Pattern wie Search Chat), kein Auto-Import, Idempotenz-Fix. 680 Tests. | ✅ DONE | 2026-05-08 |
| FEAT-31 | P3 | [FEAT] Capital Allocator Quality — Eigener Checker Agent | Eigenständiger Cloud-Agent (Sonnet + web_search) für Kapitalallokator-Qualität des Managements. 3 Dimensionen: historische Entscheidungen (Buybacks/M&A/Dividenden), Insider-Ownership + Anreize, Kommunikations-Track-Record. Verdicts: `exzellent`/`solide`/`fragwürdig`/`destruktiv`. Watchlist-only (kein Scheduler), 3. Pre-Check im Watchlist Checker (Checkbox + Background-Job), 4. Spalte im Position-Expander. DB: `capital_allocator_sessions` + `_messages`. 18 neue Tests. 748 gesamt. | ✅ DONE | 2026-05-11 |
| FEAT-24 | P2 | [FEAT] Scheduler Job Logs | New "Scheduler" page under System. Job management moved from settings.py. New `scheduled_job_runs` table + `ScheduledJobRunsRepository`. Scheduler logs every run (scheduled/manual/catchup) with status + duration + error_msg. Each job card shows expandable run history (last 10). 682 tests passing. | ✅ DONE | 2026-05-10 |
| FEAT-38 | P2 | [BUG] Attribution: Kaufdatum berücksichtigen | `compute_monthly_attribution` / `compute_yearly_attribution` ignorieren `purchase_date`. Wenn eine Position erst während des Analyse-Zeitraums gekauft wurde (z.B. März-Kauf bei Jahresanalyse), wird fälschlicherweise der Januar-Preis als Startpreis verwendet — ergibt verfälschte Beiträge. Fix: (1) `purchase_date` zu `PortfolioValuation` hinzufügen (`market_data_agent.py`), (2) in `_get_*_start_price`: wenn `purchase_date > period_start`, stattdessen `purchase_price_eur` als Startwert verwenden. Verkaufte Positionen: nicht lösbar ohne Verkaufshistorie-Tabelle (akzeptierter blinder Fleck). | ✅ DONE | 2026-05-11 |
| FEAT-39 | P3 | [IMPR] Attribution: Geschätzte Dividenden einberechnen | Monat- und Jahresanalyse zeigen aktuell nur Kursveränderung, keine Dividenden. Dividenden-Positionen werden dadurch strukturell benachteiligt. Lösung: `annual_dividend_eur` aus `PortfolioValuation` als Schätzung verwenden — Monat: `/12`, Jahr: voll. Neue Felder in `AttributionMonthRow`/`AttributionYearRow`: `dividend_contribution_eur`. UI: separate Spalte + Gesamt-Hinweis "inkl. geschätzte Dividenden". Einschränkung: ignoriert Zahlungszeitpunkte, Steuern, Wiederanlage — explizit als Schätzung kennzeichnen. | ✅ DONE | 2026-05-11 |
| FEAT-44 | P1 | [FEAT] Tax Loss Harvesting Assistant | Identifiziert Verlustpositionen (>€1000) für strategisches Jahresend-Verkaufen. Ollama-Agent liest Portfolio + Watchlist, berechnet Steuer-Impact (26,375%), empfiehlt Ersatz-Kandidaten aus Watchlist (gleiche Asset-Klasse), warnt vor Wash-Sale (30-Tage-Frist). UI: Threshold-Slider + Report + Download. Kein DB-Repo nötig (stateless). Neuer Agent `TaxLossHarvestingAgent` + Page `tax_loss_harvesting.py`. Privacy: alles lokal (Ollama). | ✅ DONE | 2026-05-20 |
| FEAT-45 | P1 | [FEAT] Dividenden-Kalender & Cashflow-Prognose | 12-Monats-Cashflow-Prognose aus `annual_dividend_eur`. Neue Komponenten: `core/dividend_calendar.py` (compute_monthly_cashflow_forecast + detect_dividend_cuts via NewsDigest), `DividendCalendarAgent` (Ollama), Page mit Bar-Chart (Monats-Cashflow) + Pie-Chart (Top-5-Anteil). Optional: DB-Migration `dividend_aristocrat_years` Spalte. Neuer SearchAgent-Skill "Dividend Aristocrats Scanner" in `default_skills.yaml`. Privacy: alles lokal (Ollama). | 🔲 TODO | |
| FEAT-46 | P1 | [FEAT] Sector Rotation Monitor | Cloud-Agent (Sonnet + web_search) analysiert Sektor-Rotation: Inflow/Outflow-Sektoren (YTD/3M/1M), Macro-Driver, Portfolio-Positionierung. Verdicts: `aligned`/`lagging`/`overexposed`/`rotation_risk` pro Sektor + Gesamt. DB: `sector_rotation_runs` + `sector_verdicts` Tabellen. Repository + Run-History UI. Privacy: nur `PublicPosition` (Ticker + Sektor) an Cloud, keine Portfolio-Größen. | 🔲 TODO | |
| FEAT-33 | P3 | [FEAT] Cowork Outbox — Rückkanal | ~~Ursprünglicher Ansatz (file-based) obsolet.~~ **Ersetzt durch FEAT-50 + FEAT-51.** | ↗ FEAT-50/51 | |
| FEAT-49 | P2 | [FEAT] MCP Server — Cowork Ingest via MCP | Lokaler MCP-Server ersetzt den File-System-Workflow für den Cowork Ingest. Statt `.md`-Dateien in den Outbox-Ordner zu schreiben, ruft Claude direkt ein MCP-Tool auf. **Ansatz (`.md`-basiert):** MCP-Server generiert korrekt formatierte Markdown-Dateien und legt sie in den bestehenden Outbox-Ordner — der existierende Watcher + Importer läuft unverändert weiter. Kein zweiter DB-Writer, kein SQLite-Concurrency-Problem. Claude braucht das Dateiformat nicht mehr zu kennen — Tool-Schema übernimmt Validierung. **MCP-Tools (write-only):** `propose_position(ticker, name, exchange, rationale, conviction, suggested_action, isin?, category?, story?, price?)` + `propose_multiple(candidates[])`. Kein Read-Zugriff auf Portfolio → Privacy clean. **Lernwert:** Lokaler MCP-Server mit Python SDK, Tool-Schema-Design, File-IO. **Neue Dateien:** `mcp_server/wealth_mcp.py` (standalone, `python -m mcp_server.wealth_mcp`). Keine Änderungen an bestehendem App-Code. Claude Code Integration: `claude mcp add wealth-research python mcp_server/wealth_mcp.py`. | 🔲 TODO | |
| FEAT-50 | P2 | [FEAT] MCP Rückkanal — Research Queue (App → Claude) | Erweiterung von FEAT-49: MCP-Server bekommt ein Read-Tool `get_research_queue()`. User klickt in der App "Research anfordern" für eine Position + Analyse-Typ (DA-Vertiefung, Regulierungs-Check, Deep Dive, etc.) → App schreibt strukturierten Request in eine leichte Queue (SQLite-Tabelle `research_requests`). Claude ruft `get_research_queue()` auf und sieht offene Anfragen mit Ticker + Fokus + Kontext (aktuelle Verdicts). Nach der Recherche: Claude ruft `propose_position()` auf (FEAT-49) oder markiert Request als erledigt via `complete_research_request(id)`. **Privacy:** Queue enthält nur Ticker + Fragestellung, keine Portfoliogrößen, keine Namen. **Schließt den Cowork-Loop:** App → MCP → Claude → MCP → App. Setzt FEAT-49 voraus. | 🔲 TODO | |
| FEAT-51 | P3 | [FEAT] Claude Code Hook — Auto-Anzeige offener Research-Requests | Ergänzung zu FEAT-50: Ein `PostToolUse`-Hook in `.claude/settings.json` prüft beim Start einer Claude Code Session automatisch ob offene Research-Requests in der Queue liegen (via `get_research_queue()`) und zeigt sie an — ohne dass der User aktiv fragen muss. **Vorteil:** Kein "vergessen" — beim Öffnen des Projekts in Claude Code erscheint sofort: "2 offene Research-Anfragen aus der App". Setzt FEAT-50 voraus. | 🔲 TODO | |
| FEAT-41 | P2 | [FEAT] Portfolio Checker Status Matrix + Navigation Refactoring | Status-Matrix (SC/CG/FA) im Portfolio Checker analog Watchlist Checker. Row-Level "fehlende Checks ausführen" Button in beiden Pages. `core/background_jobs.py` als shared Modul (~360 Zeilen Duplikat eliminiert). `fmt_verdict_matrix()` in `core/ui/verdicts.py`. Nav: "Portfolio Story" → "Portfolio Checker", Watchlist-Analyse ins Portfolio-Menu. Filter: nur Positionen mit Ticker und ohne `analysis_excluded`. Aktionsbuttons in `st.container(border=True)`. CA vorerst ausgeblendet (leicht ergänzbar). 787 tests. | ✅ DONE | 2026-05-16 |
| FEAT-40 | P2 | [FEAT] Watchlist Cockpit Refactoring | Status-Matrix (alle Positionen × 5 Checks), "▶️ Alle fehlenden Checks ausführen" mit 4 getrennten Jobs, neue Watchlist-Analyse-Seite (analog Positionsanalyse), CA Modell-Selector in Settings. 3 kritische Background-Job-Bugs behoben (CG missing cg_repo, FA get_connection() ohne Args, SC unnötige Re-Runs). Smoke-Tests ergänzt. | ✅ DONE | 2026-05-11 |
| FEAT-37 | P2 | [FEAT] Jahresanalyse | `core/yearly_attribution.py` + `core/yearly_digest_generator.py` + `core/storage/yearly_digest.py` + `yearly_digests` DB-Tabelle + `run_month` in `scheduled_jobs`. Jahresanalyse-Block in `pages/analyse.py` (Bar-Chart, Tabelle, Digest-Expander). `yearly_digest` System-Job (jährlich 1. Jan. 06:00) + `"yearly"` Frequency in Scheduler. Konsistent mit Tag/Monat: gleiche Gold-Unit-Konvention. 722 tests. | ✅ DONE | 2026-05-10 |
| FEAT-34 | P2 | [FEAT] Performance Attribution | `core/monthly_attribution.py` + Monatsanalyse-Block in `pages/analyse.py`. Bar-Chart + Tabelle (Symbol, Start/End-Preis, ∆%, Gewichtung, Beitrag€). Unit-Conversion-Fix für Gold (unit="g" → `/31.1035`). Verwendet `current_value_eur` als End-Wert (bereits korrekt konvertiert). MTD für laufenden Monat. 705 tests. | ✅ DONE | 2026-05-10 |
| FEAT-35 | P3 | [IMPR] Macro Context Overlay | `core/macro_context.py`. yfinance-only, kein LLM. Tickers: `^VIX`, `USDEUR=X`, `XAUUSD=X`, `^GDAXI`. Gold: `gold_usd × usd_eur` (multiply). Cache in app_config (4h TTL). 4 Metric-Chips in `pages/analyse.py`. 705 tests. | ✅ DONE | 2026-05-10 |
| FEAT-36 | P2 | [FEAT] Monatlicher Portfolio-Digest | `core/monthly_digest_generator.py` + `core/storage/monthly_digest.py` + `monthly_digests` DB-Tabelle (UNIQUE month). Deterministisches Markdown (Performance + Checker-Verdicts + Makro-Snapshot). Scheduler-Dispatch `monthly_digest`, System-Job auto-seeding in `pages/scheduler.py`. Expander in `pages/analyse.py`. 705 tests. | ✅ DONE | 2026-05-10 |
| FEAT-25 | P2 | [FEAT] Position-Analysis Dashboard | Single-page aggregation of all verdicts for a portfolio position: Storychecker + Consensus Gap + Fundamental Analyzer + Kursverlauf + News Digest (ticker section extraction). Portfolio-positions only. Dropdown selector + 3-column checker cards (badge + summary + expandable full-text) + news section (parses last digest, no new LLM call). Reusable components: _render_checker_card(), _extract_ticker_section(). 627 tests passing. | ✅ DONE | 2026-05-05 |
| FEAT-27 | P3 | [IMPR] Portfolio Story Integration — Position Verdict Rows | Portfolio Story "Positions-Details" expander: position buttons (clickable → Position Dashboard deeplink) + SC/CG/FA badges inline per position. Helper: `_render_position_details_expander()` reusable for both new and saved analyses. No agent context change. 627 tests passing. | ✅ DONE | 2026-05-05 |
| FEAT-26 | P2 | [IMPR] ConsensusGap Sessions — Full-Text Persistence | CG Agent now creates sessions per position (like SC/FA): stores full LLM response in consensus_gap_messages, references via position_analyses.session_id. Backward compat: old analysis_text records display via fallback. New tables: consensus_gap_sessions, consensus_gap_messages. New repo: ConsensusGapRepository. Updated agent + page + state factories. 25 unit tests. Full-Text retrieval unified across all 3 checkers. Verified: single position, batch, scheduler all work. | ✅ DONE | 2026-05-05 |

### FEAT-32 — Cowork Research Ingest: Abgeschlossen ✅

#### Gesamte Implementierung (Sessions 2026-05-08)

| Komponente | Datei | Status |
|---|---|---|
| Parser (YAML-Frontmatter → Domain-Objekte, Validation) | `core/cowork/parser.py` | ✅ |
| Importer (Status-Routing, Dedup, Archivierung, Idempotenz) | `core/cowork/importer.py` | ✅ |
| File-Watcher (watchdog, 500ms Debounce) | `core/cowork/watcher.py` | ✅ |
| DB-Tabellen (`cowork_research_entries`, `cowork_watchlist_suggestions`) | `core/storage/base.py` | ✅ |
| Repository | `core/storage/cowork.py` | ✅ |
| UI (Inbox + Proposal Panel + History) | `pages/cowork_inbox.py` | ✅ |
| Navigation (unter Research), watchdog in requirements.txt | `app.py`, `requirements.txt` | ✅ |
| Tests (28 Parser-Unit, 25 Importer-Integration, Fixture) | `tests/` | ✅ 53 Tests |
| Konfiguration (COWORK_*) | `config.py` | ✅ |

#### Dialog-Flow (implementiert)

1. Externes AI-Tool schreibt `.md`-Datei in `~/wealth-research/outbox/`
2. Watcher (500ms Debounce) oder App-Start-Scan erkennt die Datei
3. Importer parst, speichert Entry + Kandidaten als `pending`, archiviert Datei → Entry bleibt `ready_for_import`
4. User öffnet Research Inbox → Eintrag im Tab "Offen" sichtbar
5. Checkbox-Panel: `add`-Kandidaten vorselektiert, `watch`-Kandidaten unchecked
6. User wählt, klickt "Zur Watchlist hinzufügen" → ausgewählte als Positionen angelegt, Entry `imported`
7. Tab "Importiert" zeigt History (accepted/rejected pro Entry)

#### Offene technische Schulden

- `cowork_inbox.py` hat keine i18n-Nutzung (alle Strings hardcoded DE) — `t("cowork.*")`-Keys sind definiert aber nicht angebunden
- Kein Smoke-Test für `pages/cowork_inbox.py`
- `get_cowork_watcher()` in `state_agents.py` hat doppeltes `@st.cache_resource` (Zeile ~161/162) — prüfen

---

### Security

| ID | Priority | Description | Notes |
|---|---|---|---|
| SEC-1 | P1 | **Path Traversal in cowork_inbox.py** — `_write_status_to_file()` liest `entry.file_path` aus DB ohne zu prüfen ob der Pfad innerhalb des erwarteten Inbox-Verzeichnisses liegt. Fix: `path.resolve().is_relative_to(expected_inbox_dir)` Guard einbauen. | ✅ DONE 2026-05-14 |
| SEC-2 | P1 | **Prompt Injection — tavily.py title/url nicht sanitisiert** — Nur `content` der Suchergebnisse wird durch `sanitize_search_result()` geprüft; `title` und `url` werden ungefiltert in den LLM-Context übergeben. Fix: Sanitization auch auf `title` anwenden, URL-Protokoll prüfen (`https://` only). | ✅ DONE 2026-05-14 |
| SEC-3 | P2 | **XSS in portfolio_story.py** — `verdict_badge()` fällt auf den rohen LLM-String zurück wenn verdict nicht im config-Dict → landet ungefiltert in `unsafe_allow_html=True` Markdown. Fix: `html.escape(verdict)` im Fallback. | ✅ DONE 2026-05-14 |

### Technical Debt

| ID | Priority | Description | Notes |
|---|---|---|---|
| DEBT-8 | P3 | Document `migrate_db()` inline — add comments explaining the dual init+migrate pattern | Low risk, cosmetic |
| DEBT-13 | P3 | Tighten requirements.txt version bounds | Low urgency, no known conflicts |
| DEBT-21 | P1 | **Doppeltes `@st.cache_resource` in state_agents.py:162-163** — `get_fundamental_analyzer_repo()` hat zwei aufeinanderfolgende `@st.cache_resource`-Dekoratoren. Double-wrapping ist ein Fehler und kann zu unerwartetem Caching-Verhalten führen. Fix: eine der beiden Annotationen entfernen. | ✅ DONE 2026-05-14 |
| DEBT-22 | P1 | **GBp Pence Conversion Bug in fetch_historical()** — `_detect_currency()` macht `.upper()` und konvertiert GBp → GBP, fetcht dann EUR/GBP-Rate. Aber yfinance liefert historische Close-Preise für UK-Pence-Stocks in Pence, nicht Pfund. Ergebnis: `close_eur = pence × EUR/GBP = 100× zu hoch`. Fix: Vor `.upper()` auf `currency == "GBp"` prüfen, historische Closes durch 100 teilen (analog zu `_fetch_single()`). | ✅ DONE 2026-05-14 |
| DEBT-23 | P2 | **i18n-Violations in cowork_inbox + cowork_setup** — `cowork_inbox.py:71` hat `"Aktie"` hardcoded. `cowork_setup.py` verwendet keine `t()`-Calls, alle Subheaders + Texte sind deutsches Plaintext. Translation-Keys teilweise definiert (`t("cowork.*")`), aber nicht angebunden. | ✅ DONE 2026-05-14 |
| DEBT-24 | P2 | **Fehlende Smoke-Tests für 6 neue Pages** — Seit DEBT-10 (April 2026) hinzugekommen: `capital_allocator.py`, `watchlist_analysis.py`, `cowork_inbox.py`, `cowork_setup.py`, `position_dashboard.py`, `scheduler.py`. Keine AppTest-Smoke-Tests. | ✅ DONE 2026-05-14 |
| DEBT-25 | P3 | **isinstance-Redundanz in Attribution-Code** — `isinstance(purchase_date, date) and purchase_date > period_start` in `monthly_attribution.py` + `yearly_attribution.py`. `purchase_date` ist immer `date \| None`; einfacher: `if purchase_date and purchase_date > period_start`. Kein Bugrisiko, nur Lesbarkeit. | ✅ DONE 2026-05-14 |

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

### Security — Completed ✅

| ID | Completed | Description |
|---|---|---|
| SEC-2 | 2026-05-14 | Prompt Injection — tavily.py title sanitisiert + URL-Protokoll-Check eingebaut |
| SEC-3 | 2026-05-14 | XSS — verdict_badge Fallback mit html.escape() abgesichert |

### Technical Debt — Completed ✅

| ID | Completed | Description |
|---|---|---|
| DEBT-21 | 2026-05-14 | Doppeltes @st.cache_resource in state_agents.py entfernt |
| DEBT-22 | 2026-05-14 | GBp Pence Conversion Bug in fetch_historical() gefixt — UK-Aktien Kursverlauf jetzt korrekt |
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
| DEBT-17 | 2026-05-05 | Agent LLM Config — Extended Thinking with UI Toggles (SearchAgent + StructuralChangeAgent). Per-call enable_thinking parameter via UI toggles. Users can A/B test thinking cost/quality in real usage. Thinking only active for Sonnet/Opus. |
