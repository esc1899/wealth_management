# Arbeitsweise in diesem Projekt

## 📍 Dokumentations-Struktur (Single Source of Truth)

Damit zukünftige Sessions alles finden:

| Datei | Inhalt | Wer updatet |
|---|---|---|
| **CLAUDE.md** (diese Datei) | Arbeitsweise, Process, Stack-Fallstricke, Architektur-Guards | Claude bei Prozess-Änderungen |
| **ARCHITECTURE.md** | Architektur-Entscheidungen, Design-Patterns, Architektur-Guards, Schulden-Status | Claude bei Arch-Änderungen |
| **CHANGELOG.md** | Version-Historie, Technische Schulden Remediation Status | Claude beim Release |
| **BACKLOG.md** | Features (geplant + abgeschlossen), Technische Schulden Inventory | User/Claude beim Planning |
| **Memory/user_profile.md** | Wer ist Erik, wie arbeitet er | Claude nach User-Feedback |
| **Memory/feedback.md** | Feedback zur Arbeitsweise mit Claude | Claude nach User-Feedback |
| **Memory/private_skills.md** | Persönliche Skills (Wu-Wei, Lindy+Potential, etc) | User-Configured |

**Governance Rule**: Projekt-Sachen → Git-Repo (CLAUDE/ARCHITECTURE/CHANGELOG/BACKLOG). Persönliche Erkenntnisse → Memory. **Nicht duplizieren.**

---

## 📋 Dokumentations-Governance (Sessions-übergreifend konsistent)

**Problem**: Ohne explizite Regeln landen Informationen überall verteilt → nächste Session findet Dinge nicht.

### Konkrete Zuordnung (was gehört wohin)

| Art der Info | Ziel-Datei | Beispiel | Wann |
|---|---|---|---|
| **Bug/Issue entdeckt** | BACKLOG.md § Issues | "Hardcoded 'Antworte auf Deutsch' verletzt i18n" | sofort nach Discovery |
| **Neue technische Schuld** | BACKLOG.md § Technische Schulden | "DEBT-20: Skills nicht in DB gepflegt" | sofort |
| **Feature-Idee / zukünftige Arbeit** | BACKLOG.md § Features (geplant) | "Watchlist Checker sollte X auch können" | sofort |
| **Feature fertig & gemerged** | BACKLOG.md § Features (abgeschlossen) | "✅ Investment Kompass Phase 1+2" | nach Commit |
| **Prototyp-Learning (was wir lernten)** | BACKLOG.md § Discovery-Notes | "Investment Kompass zu konkret, Rebalance Agent zu vage" | sofort nach Test |
| **Architektur-Entscheidung getroffen** | ARCHITECTURE.md | "Systems Thinking Model mit 3 Ebenen" | bei Arch-Change |
| **Process/Arbeitsweise ändert sich** | CLAUDE.md § Changelog | "Begonnen mit Phase-based Implementation" | bei Process-Change |
| **Major Release / Milestone** | CHANGELOG.md | "v0.5: Investment Kompass MVP + Watchlist Checker" | bei Release |
| **Persönliches Feedback zu Claude Code** | Memory/feedback.md | "Claude arbeitet besser in Plan Mode" | nach User-Feedback |
| **Persönliche Skill-Definition** | Memory/private_skills.md | "Wu-Wei: Minimal Critical Path" | User-konfiguriert |

### Explizite Ausschlusskriterien

❌ **Nicht** in Memory.md:
- Code-Patterns, Konventionen, Architektur (→ CLAUDE.md/ARCHITECTURE.md)
- Issues/Bugs (→ BACKLOG.md)
- Feature-Status (→ BACKLOG.md)

❌ **Nicht** in CLAUDE.md:
- Detaillierte Feature-Status (→ BACKLOG.md)
- Issues einzeln auflisten (→ BACKLOG.md)
- Private Erkenntnisse über den Nutzer (→ Memory/user_profile.md)

❌ **Nicht** in BACKLOG.md:
- Wie ich arbeite (→ CLAUDE.md)
- Architektur-Begründungen (→ ARCHITECTURE.md)
- Persönliche Feedback-Notizen (→ Memory/)

---

**Verwandte Abschnitte:**
- [Architektur-Guards](#architektur-guards-anti-patterns-vermeiden) — siehe unten
- [Technische Schulden Remediation](#technische-schulden--remediation-status) — siehe unten
- Detaillierte Schulden-Inventory: [BACKLOG.md § Technische Schulden](BACKLOG.md)

---

## Vor jeder Änderung
- Alle relevanten Dateien lesen, bevor Code geändert wird
- Bei nicht-trivialen Aufgaben: Plan Mode nutzen (`/plan`)
- Verwandte Fehler zusammen beheben — keine Einzelfix-Iterationen

## Plan Mode – Systems Thinking
Motto: **try to improve the whole**
- **Teilsysteme**: Wie wirkt sich die Änderung auf einzelne Module/Komponenten aus?
- **Gesamtsystem**: Wie verändert sich das Verhalten des Gesamtsystems? Entstehen neue Abhängigkeiten oder Feedback-Schleifen?
- Vor Optimierungen: Nicht nur lokale Verbesserungen, sondern Auswirkungen auf das ganze System denken
- Emergente Effekte identifizieren: Was ergibt sich unerwarteterweise aus den Interaktionen zwischen Systemen?

## Test-Disziplin (kritisch)
- `pytest tests/` nach jeder Änderung ausführen — keine Ausnahme
- Bug gefunden → erst **Failing Test schreiben**, dann fixen
- Integration Tests nutzen echtes SQLite `:memory:`, kein Mocking von Repos

## UI Integration Tests (kritisch für Pages & Navigation)
**Lernpunkt (2026-04-14):** 3 Fehler hintereinander in wealth_history.py (i18n default-param, plotly template, duplikat) weil ich nur Unit-Tests lief, nicht die App.

**Regel:** Nach jeder neuen Page oder großen UI-Änderung:
1. `streamlit run app.py` starten
2. Zur neuen/geänderten Seite navigieren
3. Verifizieren: Charts rendern, Buttons funktionieren, keine Exceptions
4. **Erst dann** committen

**Checkpoints für neue Pages:**
- [ ] Page startet ohne Fehler
- [ ] Alle `t()` Calls funktionieren (keine `default=` Parameter!)
- [ ] Charts/Plotly: nur gültige Template-Namen (`plotly_white`, `plotly`, nicht `plotly_light`)
- [ ] Keine Duplikate in Navigation oder anderen Pages
- [ ] `pytest tests/` noch grün

## Test Coverage — Standards & Ziele

**Wichtig:** Coverage misst nur "wieviel Code wurde ausgeführt", nicht "sind Tests gut". Eine gute Coverage sagt nicht automatisch: keine Bugs, sondern: meiste Fehler-Szenarien werden gefunden.

| Coverage-Level | Bewertung | Anwendung |
|---|---|---|
| **< 50%** | ⚠️ Zu niedrig | Unakzeptabel — zu viele versteckte Bugs |
| **50–70%** | 🟡 Okay | Einfache Projekte, aber verbesserungswürdig |
| **70–80%** | ✅ Gut (Ziel) | Standard für professionelle Projekte — aktuell: **77.62%** |
| **80–90%** | 🟢 Sehr gut | High-Quality Code mit guter Regression-Protection |
| **90–95%** | 🌟 Ausgezeichnet | Für sicherheitskritische/finanzielle Systeme |
| **95%+** | ⚠️ Overkill | Aufwand meist nicht proportional zum Nutzen |

**Pro Code-Kategorie** (Richtlinien):
- **Critical** (Auth, Sicherheit, Finanzen): 85–95% Coverage
- **Business Logic** (Core Features): 70–85% Coverage
- **Repositories/Services**: 80%+ Coverage (relativ leicht zu testen)
- **Pages/UI**: 40–60% Coverage (schwer zu testen, weniger Priorität)
- **Utils/Helpers**: 80%+ Coverage (leicht zu testen, sollte hoch sein)

**Aktueller Stand:**
- **77.62% Overall** ✅ Sehr gut — Fehler-Scenario-Detection ist hoch
- Kommit-Befehl zeigt Abdeckung: `pytest tests/ --cov`
- Ziel: 77–80% halten (nicht obsessiv verfolgen, sondern kritischer Code priorisieren)

## Debug-Hygiene
- Kein Debug-Code committen (`/tmp`-Writes, print-Statements, Logging-Spam)
- Debug in einem Scratch-Branch oder mit pytest `-s` — nicht im Hauptcode
- Vor jedem Commit: `git diff` prüfen, keine temporären Artefakte

## Commit-Qualität
- Jeder Commit hat grüne Tests
- Zusammengehörige Fixes in einem Commit — nicht: fix1, fix2, fix3 separat
- Commit-Message erklärt Ursache, nicht nur Symptom

## Kontext-Management
- Bei Bugs: erst alle beteiligten Dateien lesen, dann einmal fixen
- Wenige große Änderungen > viele kleine Iterationen
- Bei unklarer Root Cause: AskUserQuestion statt raten

## Stack-Eigenheiten (bekannte Fallstricke)
- `web_search_20250305` nur mit Sonnet+ (Haiku loops)
- `@st.cache_resource`: nach Code-Änderungen Full Restart nötig
- `ClaudeToolCall.input` (nicht `.arguments`), `ClaudeResponse.raw_blocks`
- Haiku 4.5 bevorzugen für Research/Chat Agents (6x günstiger, höhere Rate Limits)

---

## Architektur-Guards (Anti-Patterns vermeiden)

Diese Muster haben zu technischen Schulden geführt. **Nicht wiederholen**:

### ❌ Hardcoded Strings (statt Konstanten)
**Problem**: Modellnamen, Feature-Flags, URLs an 7+ Stellen hardcoded (DEBT-3)

**Guard**: Alle Magic-Strings gehören in `core/constants.py`:
```python
# ✅ RICHTIG
from core.constants import CLAUDE_MODELS, LLM_TIMEOUTS

provider = ClaudeProvider(model=CLAUDE_MODELS['research'])
```

```python
# ❌ FALSCH
provider = ClaudeProvider(model="claude-sonnet-4-6")  # Hardcoded!
```

### ❌ LLM-Calls direkt in Pages (ohne Service-Layer)
**Problem**: Usage wird nicht getrackt, Modell nicht konfigurierbar (DEBT-5, DEBT-4)

**Guard**: LLM-Calls gehören nur in Agents/Services:
```python
# ✅ RICHTIG
class StoryProposalService:
    def generate(self, position: Position) -> str:
        agent = get_story_agent()  # mit Usage-Tracking
        return agent.propose_story(position)

# pages/positionen.py
service = get_story_service()
story = service.generate(position)
```

```python
# ❌ FALSCH
# pages/positionen.py
provider = ClaudeProvider(model="claude-haiku-4-5-20251001")  # Direkt in Page!
story = provider.chat(...)  # Kein Tracking!
```

### ❌ Direkter Repo-Zugriff in Pages
**Problem**: Pages werden untestbar, Business Logic in UI vermischt (DEBT-4)

**Guard**: Pages sprechen nur mit Agents oder Services:
```python
# ✅ RICHTIG
service = get_portfolio_service()
context = service.build_portfolio_context()  # Service encapsulates Repos

st.write(context)
```

```python
# ❌ FALSCH
# pages/rebalance_chat.py
repo = get_positions_repo()  # Direkter Repo-Zugriff!
portfolio = repo.get_portfolio()
_analyses_repo = get_analyses_repo()  # Multiple Repos!
analyses = _analyses_repo.get_latest_bulk(...)
```

### ❌ Private Attribute-Zugriff aus Pages
**Problem**: Kapselung verletzt, Refactoring unmöglich (DEBT-6)

**Guard**: Nur öffentliche Methoden/Properties von Agenten:
```python
# ✅ RICHTIG
class MarketDataAgent:
    @property
    def latest_fetch_time(self) -> Optional[datetime]:
        return self._market.get_latest_fetch_time()
    
    def get_historical(self, ticker: str, days: int):
        return self._market.get_historical(ticker, days)

# pages/dashboard.py
last_fetch = agent.latest_fetch_time  # Public property
```

```python
# ❌ FALSCH
# pages/dashboard.py
last_fetch = agent._market.get_latest_fetch_time()  # Private!
```

### ❌ Duplikate Schema-Definition
**Problem**: DDL in init_db + migrate_db mit Ausfall-Risiken (DEBT-1, DEBT-8)

**Guard**: Schema defined einmal, alle Aufrufe durch zentrale Guard:
```python
# core/storage/base.py
def get_db():
    """Singleton with idempotent migration guard."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(DB_PATH)
        _db_instance.migrate_if_needed()  # Single entry-point!
    return _db_instance

# state.py, market_data_agent.py, scheduler.py — alle nutzen get_db()
db = get_db()  # Migration happens once, automatically
```

### ❌ asyncio.run() in Streamlit
**Problem**: Event-Loop Konflikte, Race Conditions (DEBT-9)

**Guard**: Async nur in Services/Agents, nie direkt in Pages:
```python
# ✅ RICHTIG
class RebalanceAgent:
    async def analyze_async(self) -> str:
        # Echte async work hier
        return await self.llm.chat_async(...)

# pages/rebalance_chat.py (Sync!)
agent = get_rebalance_agent()
result = agent.analyze()  # Nicht async, Streamlit-safe
```

```python
# ❌ FALSCH
# pages/rebalance_chat.py
import asyncio
result = asyncio.run(agent.analyze_async())  # ⚠️ Event-Loop Conflict!
```

### ❌ Ungetestete Pages mit Business-Logic
**Problem**: Regressions schwer zu finden, Code-Qualität sinkt (DEBT-10)

**Guard**: Business Logic gehört in Services/Agents, Pages sind dünn:
```python
# ✅ RICHTIG
# core/services/portfolio_service.py (TESTBAR)
class PortfolioService:
    def calculate_position_value(self, pos: Position) -> float:
        return pos.quantity * pos.current_price
    
    def filter_positions(self, criteria) -> List[Position]:
        # Logic hier, leicht zu testen
        ...

# pages/positionen.py (Dünn, fokussiert auf UI)
service = get_portfolio_service()
for pos in service.filter_positions(criteria):
    value = service.calculate_position_value(pos)
    st.write(f"{pos.name}: {value}")
```

---

## Technische Schulden — Remediation Status

**16 Schulden identifiziert (2026-04-12). Status: 12 behoben, 4 ausstehend**

### ✅ Behoben (Gruppe 1 + 2)

- **[DEBT-14]** agentmonitor.py in Navigation verdrahtet ✅
- **[DEBT-15]** Abgelaufenes Easter-Egg entfernt ✅
- **[DEBT-16]** O(n) Deletes → Batch-Deletes (PositionsRepository) ✅
- **[DEBT-11]** Coverage-Konfiguration in pytest.ini ✅
- **[DEBT-3]** Constants-Registry — alle 8 Dateien mit Modell-Konstanten (2026-04-13 completed) ✅
- **[DEBT-5]** `_generate_story_proposal()` → PositionStoryService (2026-04-12) ✅
- **[DEBT-6]** Public Agent APIs (`model` property, `get_latest_fetch_time()`) (2026-04-12) ✅
- **[DEBT-1]** DDL-Duplikate bereinigt (usage_resets, dividend_data nur in init_db) (2026-04-12) ✅
- **[DEBT-2]** Legacy portfolio/watchlist Tabellen prüft und unused bestätigt (2026-04-12) ✅

### ⏳ Ausstehend (separate Sessions empfohlen, hoher Aufwand)

| Schuld | Aufwand | Grund |
|---|---|---|
| **DEBT-4** | Sehr Hoch | Service-Layer (8+ Pages, Multi-Session Refactor) |
| **DEBT-7** | Hoch | Decompose state.py (God Module) — breaking change für Imports |
| **DEBT-8** | Niedrig | migrate_db() Dokumentation (bereits funktionsfähig, nur Klarheit) |
| **DEBT-9** | Sehr Hoch | Async Anti-Pattern (nest_asyncio, 16 Stellen) |
| **DEBT-10** | Hoch | Pages ungetestet (blocked by DEBT-4) |
| **DEBT-12** | N/A | peewee nicht im Code verwendet — ignore |
| **DEBT-13** | Mittel | requirements.txt Version-Bounds (low risk) |

**Nächste Priority:** DEBT-4 (nur mit separater Session) oder DEBT-8+13 für low-risk Wins

---

## Changelog (CLAUDE.md Prozess-Updates)

### 2026-04-15 — Skills Architecture Cleanup & Completion (Session 4)

**Critical Milestone: Skills System Complete + Dead Code Removed**

**Phase-Based Implementation (All 5 Phases Completed):**
1. ✅ Phase 1: Josef's Regel Extraction → `core/portfolio_stability.py`
2. ✅ Phase 2: Dead Agents Deletion (rebalance, investment_compass)
3. ✅ Phase 3a: Skills YAML Restructure (10 areas, removed rebalance/structural_scan)
4. ✅ Phase 3b: WatchlistCheckerAgent Skills Support (skill-selectable)
5. ✅ Phase 3c: PortfolioStoryAgent Skills Support (skill-selectable)
6. ✅ Phase 4: Fundamental Analyzer Navigation (replaced fundamental.py)
7. ✅ Phase 5: Skills Management Page Separation (System → Skills)

**Issues Fixed:**
- ✅ Old skill areas (wealth_snapshot, rebalance) removed from UI
- ✅ FundamentalAnalyzer session_id validation error fixed (AsyncMock)
- ✅ Watchlist Checker "Standard (kein Fokus)" option added (default behavior preserved)
- ✅ Portfolio Story "Standard (kein Fokus)" option added
- ✅ All 6 test_fundamental_analyzer_agent.py failures resolved

**Files Changed:**
- Deleted: 7 files (rebalance_agent, investment_compass_agent, related pages/storage)
- Created: 2 files (core/portfolio_stability.py, pages/skills.py)
- Modified: 11 files (agents, pages, state, app, YAML, tests)
- Total Impact: -63 lines dead code, +259 lines features, net -292 lines

**Tests:** 563/563 passing ✓, Coverage 78.35% ✓
**Commits:** 3 (skills infrastructure, skill selectors, test fixes)

**Lernpunkt:** UI Integration Testing critical — 3 issues found only during manual testing:
1. Old skill areas still showing in YAML
2. Fundamental Analyzer async/await mocking issue
3. Watchlist Checker results parsing affected by auto-selected skill

**Next:** User to test UI manually (deferred to later session due to context limits)

---

### 2026-04-14 — UI Integration Tests Rule + Vermögenshistorie Automation (Session 3)

**Lernpunkt:** 3 UI-Fehler hintereinander in `wealth_history.py` weil Unit-Tests liefen (grün), aber App nicht gestartet wurde
- i18n: `t()` akzeptiert kein `default=` Parameter
- Plotly: `plotly_light` ist kein gültiger Template-Name
- Duplikat: Vermögenshistorie war sowohl im Dashboard als auch in Navigation

**Neue Regel — "UI Integration Tests (kritisch für Pages & Navigation)":**
- Nach jeder neuen Page/großen UI-Änderung: `streamlit run app.py` starten
- Zur neuen Seite navigieren → Charts/Buttons funktionieren, keine Exceptions
- Checkpoints: `t()` Calls, Plotly Templates, keine Duplikate, `pytest` grün
- **Erst dann** committen

**Completed:**
1. Rebalancing-Toggle aus Positions-Dialog entfernt
2. Auto-Snapshots nach Marktdaten-Fetch (Callback-Pattern in MarketDataAgent)
3. Dividenden-Zeitreihe neu (DividendSnapshotRepository + take_dividend_snapshot)
4. Vermögenshistorie-Page (mit Plotly Charts, i18n)
5. Entfernt Duplikat aus Dashboard

**Tests**: 586/586 grün, Coverage 78.96%
**Commits**: 5 (3 Fixes after errors, rest clean)

---

### 2026-04-13 — Analyst Agent Expansion & UX Improvements (Session 2)

**User Feedback Issues:**
1. Story Checker Sessions würden nicht wechseln bei Position-Neuauswahl
2. Fehlte Fundamental Analyzer für Einzelpositions-Analyse (Chat-basiert)
3. Watchlist Checker Details waren zu technisch (nur Agent Metadata)

**Completed:**
- **Story Checker Bug** (68640b3): Position-Wechsel leert jetzt alte Session-ID → neue Chat-Session wird angezeigt
- **Fundamental Analyzer** (737486d): 
  - Neuer Cloud-Agent für tiefgehende Fundamentalwert-Analyse
  - 100% Test-Coverage (21 Unit-Tests)
  - In-Memory Sessions, Verdict-Persistierung
  - Feature-Parity mit Story Checker aber für Fundamentalwerte
- **Watchlist Checker UX** (6b8dcce):
  - Per-Position Details-Expander (Story + Fundamental Verdicts)
  - Verbesserte Kontext-Details (Portfolio Story Context, Fit-Summaries)
  - Bessere visuelle Organisation

**Architecture:**
- FundamentalAnalyzerAgent: Vereinfacht vs. StorycheckerAgent (keine separate Repo)
- Sessions in Streamlit session_state, nicht persistent (können später zu DB migrieren)
- Nutzt PositionAnalysesRepository für Verdict-Tracking

**Tests:** All 586 passing, Coverage 91.85%, FundamentalAnalyzer 100%

**Commits:** 3 (Bug-Fix, Feature, UX-Impr)

**Next:** Integration mit Navigation (Fundamental Analyzer in Sidebar), oder andere Features aus Backlog

---

### 2026-04-13 — Investment Kompass Phase 2: Usecase-Specific Context

- **Completed**: Phase 1 (Query Validation) + Phase 2 (Usecase-Specific Execution)
- **Architecture**: Systems Thinking model with 3 nested levels (Portfolio Story → Query Validation → Usecase Execution)
- **New Methods**:
  - `_execute_usecase()`: Phase 2 main dispatcher, manages skill injection and context filtering
  - `_build_context_for_usecase()`: Filters context (portfolio, verdicts, story analysis) based on usecase
  - `_should_use_skill_for_usecase()`: Gate that controls skill usage (enabled for ALLOCATION/REBALANCING/ANALYSIS, disabled for WITHDRAWAL)
  - `_get_usecase_prompt()`: Usecase-specific system prompts (4 variants for each usecase)
- **Skill Integration**: Phase 3 complete — skills now modulate how analysis is performed, not whether it happens
- **Context Filtering**:
  - ALLOCATION: portfolio + watchlist + story (for position selection)
  - REBALANCING: + analyst verdicts (storychecker, fundamental, consensus_gap)
  - WITHDRAWAL: portfolio + watchlist + story (simpler context for fixed logic)
  - ANALYSIS: + analyst verdicts + portfolio story analysis (full context for robustness assessment)
- **Tests**: All 565 passing, Investment Compass agent at 100% coverage, overall 79.31%
- **Commits**: 1 (Phase 2 complete)
- **Next**: Phase 4 (prompt refinement, continuous), or features from larger plan (Watchlist Checker, Navigation reorg)

### 2026-04-13 — Josef's Regel Prompt Clarification

- **Fixed**: LLM misunderstanding of Säulen structure (was summing independent pillars)
- **Change**: Rewrote prompt to explicitly mark three Säulen as independent with "NICHT addieren!" warning
- **Context**: Added per-Säule stability assessment with deviation percentages
- **Benefit**: LLM now correctly evaluates 1/3 distribution as intentional crisis-protection
- **Tests**: 523 passing, Coverage 77.62%
- **Commits**: 2 (prompt fix + CHANGELOG update)

### 2026-04-12 — Technische Schulden Remediation

- **Added**: Architektur-Guards Sektion — Anti-Patterns zu vermeiden
- **Added**: Remediation Status Tabelle für alle 16 Schulden
- **Completed**:
  - Gruppe 1 (Quick Wins): DEBT-14, DEBT-15, DEBT-16, DEBT-11
  - Gruppe 2: DEBT-3 (core/constants.py created, 4/8 files updated)
- **Tests**: 523 passing
- **Commits**: 2 (Gruppe 1 + DEBT-3 partial)

### 2026-04-11
- **Added**: Dokumentations-Struktur Tabelle (Single Source of Truth)
- **Added**: Plan Mode Motto "try to improve the whole"
- **Initial**: Test-Disziplin, Debug-Hygiene, Commit-Qualität Guidelines

---
