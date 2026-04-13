# Backlog

Personal planning overview. User feedback and bug reports: [GitHub Issues](https://github.com/esc1899/wealth_management/issues)

## Legend
- `[P1]` High / `[P2]` Medium / `[P3]` Low
- `[BUG]` Bug / `[FEAT]` Feature / `[IMPR]` Improvement

---

## In Progress

*(empty)*

---

## Planned

---

### Portfolio Story

#### [P2] [IMPR] Portfolio Story: Erweiterte Stabilitäts-Kriterien
Stability-Check könnte zusätzliche Kriterien einbeziehen:

1. **Diversifikation:** Position-Anzahl, Top-3-Klumpen-Risiko (Konzentration)
   - Warnung: Zu wenige Positionen → Klumpenrisiko
   - Analyse: Top-3 Positionen sollten <60% des Portfolios nicht übersteigen

2. **Sektor-Konzentration:** Branchenverteilung analysieren
   - "Zu viel Tech/Finanzsektor/Einzelbranchen?"
   - Vergleich: Ist Sektor-Gewichtung vs. Portfolio-Ziel angemessen?

3. **Währungsrisiko (FX-Exposure):** Non-EUR-Anteil
   - USD, CHF, GBP, etc. — Volatilität durch Wechselkurse
   - Zielzonen je nach Risikotoleranz/Zeithorizont

4. **Zeitlicher Horizont vs. Volatilität:** Je näher target_year, desto defensiver
   - 2025: >50% Aktien → Warnung
   - 2040+: Aktienanteil defensiv für Endjahrzehnt anpassen

5. **Notfall-Reserve:** Bargeld für Emergencies
   - Sollte 3–6 Monate Lebenshaltungskosten abdecken
   - Zeigt Liquiditäts-Puffer für Krisen auf

**Aktuell implementiert:**
- Josef's Rule: Aktien/Renten/Rohstoffe Gewichtung (1/3 + 1/3 + 1/3 Richtlinie)
- Inflationsschutz: Rohstoffe + Immobilien als Hedge
- Liquidität: Renten + Dividenden (jährliche Cashflows)
- Dividendenbewertung: Absolute Dividenden vs. Ziel/Priorität

**Zukünftig (gute Kandidaten für Phase 2):**
- Top-3-Konzentration automatisch analysieren
- Sektor-Mapping und Häufung identifizieren
- FX-Exposure summieren
- Bargeld-Adäquatheit bewerten

#### [P2] [FEAT] Portfolio Story: Per-Position Story-Fit Assessment ✅ UMGESETZT
**Phase 1** (ursprünglich): Batch LLM-Call analysiert Positionen gegen Portfolio-These (stärkt/schwächt/neutral).

**Phase 2** (2026-04-11): **Role-Based Redesign** (84d27bb)
- `fit_role` ersetzt `fit_verdict`: 5 Rollen statt 3 Verdicts (Wachstumsmotor 🔵 / Stabilitätsanker 🟡 / Einkommensquelle 🟢 / Diversifikationselement 🟣 / Fehlplatzierung 🔴)
- **Story-Primacy**: Für bestehende Positionen ist Portfolio-Story #1, Fundamentals nur "confirmatory signal"
- LLM-Prompt role-focused: "Rolle basiert auf Story-Logik, nicht absoluter Qualität"
- Alle 527 Tests grün

**Phase 3** (2026-04-11): **Position-Story Update — Expander Pattern, Check-unabhängig** (407d490)
- Neuer Button "📝 Position-Story aktualisieren" im Storychecker (col_left, immer verfügbar, nicht Session-abhängig)
- Expander-Pattern wie "Hinterlegte Story anzeigen" (kompakt, kollabiert)
- `generate_story_proposal()` akzeptiert jetzt Position direkt (ohne Check-Kontext)
- Iterativer Prozess: User kann jederzeit Story-Update generieren & speichern → wird bei nächstem Check genutzt

#### [P2] [FEAT] Portfolio Story: Rebalancer-Integration
Portfolio Story als Kontext in Rebalancer injizieren → Rebalancing-Vorschläge werden goal-aware und story-aligned.

---

### Invest / Rebalance

#### [P2] [IMPR] Investment Kompass & Watchlist Checker: Inhaltlicher Feinschliff
**Status:** Funktional fertig (2026-04-13), alle Tests grün, 78.69% Coverage

**Was noch poliert werden kann:**
1. **System-Prompts:** Präzision/Nuance bei komplexen Portfolio-Szenarien
2. **Output-Formatierung:** Wie Ergebnisse präsentiert werden (Reihenfolge, Länge, Fokus)
3. **Context-Priorität:** Welche Verdicts/Analysen werden zuerst gezeigt?
4. **Parsing-Robustheit:** Edge-Cases in LLM-Response-Extraktion
5. **Watchlist-Parsing:** Zusammenfassung der LLM-Responses aus 🟢🟡⚪🔴 verdicts
6. **Investment Kompass UX:** Query-Beispiele, Strategy-Auswahl Klarheit

**Approach:** Nach echtem Einsatz (User-Feedback) iterativ verfeinern.

---

#### [P3] [FEAT] Invest/Rebalance: Zusammenhang Skill ↔ geplante Cloud-Agents
Architektur-Frage: Wenn Agents (News, Storychecker) automatisch eingeplant werden, sollen ihre Ergebnisse als Kontext in Invest/Rebalance einfließen. Skill-Auswahl im Rebalance könnte steuern, welche Agent-Outputs relevant sind.

Klärungsbedarf: Design-Session vor Umsetzung.

---

### Research / Story / Investment Search

#### [P2] [IMPR] Investment Search: Begründung als Story absichern
Wenn eine Investment-Search-Empfehlung in die Watchlist übernommen wird, soll die Begründung (aus dem Chat) automatisch als Story gespeichert werden.

Umsetzung: "In Watchlist" Button übergibt Begründungstext an Story-Feld.

#### [P3] [FEAT] Story: AI-generiertes Bild
Passend zum Investment (Name, Asset-Klasse, Story) ein Bild generieren lassen — z.B. via DALL-E oder Claude Vision-to-Image (falls verfügbar).

Klärungsbedarf: API-Kosten, Speicherort (Blob oder DB), UI-Integration.

---

### Architektur




---

## Ideas / Later

#### [P3] [FEAT] Rebalance: planned deposits / withdrawals input
Allow users to enter an expected cash in- or outflow before running the analysis.

#### [P3] [FEAT] Empfehlungsquelle auswerten
`recommendation_source` ist im Modell vorhanden. Statistik-Seite: "Quelle → Ø G/V %" über alle empfohlenen Positionen.

#### [P3] [FEAT] Währungsflexibilisierung
`BASE_CURRENCY` Config-Eintrag (default EUR) für CH/GB/US-Nutzer.

#### [P3] [IMPR] UI: Lokale vs. Cloud LLM visuell trennen
Privater Bereich (Ollama 🔒) und Cloud-Bereich (Claude ☁️) klarer abheben — z.B. eigene Navigationsgruppen-Farben oder Badges.

#### [P3] [IMPR] Tonfall-Skill pro Agent
`st.selectbox` "Kommunikationsstil" in der Seitenleiste jedes Chat-Agents (Präzise, Erklärend, Motivierend, Kritisch, Formal).

---

## Discovery: Investment Kompass Prototype (2026-04-13)

**Outcome:** Funktioniert technisch, aber Anforderungen noch unklar. Iteratives Lernen durch Testen.

### Learnings & Open Questions

#### [P1] [DISC] Investment Kompass: Zu konkret vs. Portfolio Story Agent
**Finding:** Investment Kompass erzeugt zu granulare Handlungsempfehlungen (10k€ auf 5 kleine Positionen verteilt statt 1-2 große).
- Portfolio Story Agent: Zu vage
- Rebalance Agent (alt): Zu vage
- Investment Kompass (neu): Zu konkret & detailliert
- **Open:** Ist Investment Kompass nötig oder nur alternative UI zum Portfolio Story Agent?

**Next:** Klären ob Investment Kompass eine echte Lösung ist oder ob das Problem beim Portfolio Story Agent liegt.

#### [P2] [DISC] Farmer Strategy wird nicht richtig eingebaut
**Finding:** User wählte "Farmer Strategy" aber LLM ignoriert sie. Prompts sind nicht skill+usecase kombiniert.
- Allocation + Farmer sollte andere Empfehlungen als Allocation + Growth
- Skills sind im Code, aber nicht in Prompt eingebaut
- **Cause:** Phase 2 baut skill_prompt rein, aber nicht skill-spezifisch für Usecase

**Next:** Prompts überarbeiten — ALLOCATION sollte Farmer berücksichtigen (Dividenden, Einkommen, nicht "Sow/Harvest/Prune")

---

## Technische Schulden

Identified during code review (2026-04-12). Impacts on architecture, maintainability, and testing.

### Datenverwaltung & Migrations

#### [DEBT-1] [P1] Duplizierter DDL-Code in init_db() und migrate_db()
**Problem:** Tabellen wie `portfolio_story_position_fits`, `benchmark_runs`, `usage_resets`, `dividend_data` sind in beiden Funktionen mit identischen `CREATE TABLE IF NOT EXISTS`-Statements definiert.

**Impact:** Schema-Änderungen müssen an 2 Stellen synchron gehalten werden. Fehlerquelle für Inkonsistenzen zwischen Init und Migration.

**Lösung:** Schema zu Migrationssystem (Alembic/Flyway) oder zentrales Migrations-Register, `init_db()` nur für Fresh-Start, `migrate_db()` für alle Updates.

**Files:** `core/storage/base.py` (init_db: Zeilen 24-46, 210-229, 265-271, 303-311; migrate_db: Zeilen 352-393)

#### [DEBT-2] [P2] Legacy-Tabellen portfolio / watchlist noch in init_db
**Problem:** Alte Tabellen `portfolio` und `watchlist` werden noch bei `init_db()` angelegt, obwohl `positions`-Modell diese vollständig ersetzt hat.

**Impact:** Verwirrung für neue Entwickler, unnötige Tabellen in Schema, Migration-Pfade unklar.

**Lösung:** Legacy-Tabellen entfernen oder Migrations-Dokumentation schreiben, warum sie noch da sind.

**Files:** `core/storage/base.py` (Zeilen 24-46), `core/storage/models.py` (comment: "legacy models")

---

### Konfiguration & Konstanten

#### [DEBT-3] [P1] Hardcoded Modellnamen an 7+ Stellen
**Problem:** Model-Strings wie `"claude-haiku-4-5-20251001"`, `"claude-sonnet-4-6"` sind verstreut in State, Pages, Config, Agents.

**Impact:** Modell-Update erfordert Änderungen an mindestens 7 Dateien. Inkonsistente Defaults. Schwer zu testen.

**Lösung:** Zentrale `constants.py` mit `CLAUDE_MODELS` dict, überall importieren.

**Files:** 
- `state.py` (Zeilen 50, 227, 284, 294, 301)
- `positionen.py` (Zeile 31)
- `benchmark.py` (Zeilen 236, 248)
- `core/llm/factory.py` (Zeile 32)
- `core/llm/claude.py` (Zeile 32)
- `core/storage/app_config.py` (Zeilen 68-70)
- `core/storage/usage.py` (Zeile 210)

---

### Architektur & Layering

#### [DEBT-4] [P1] Keine Service-Layer — Direkte Repo-Zugriffe in UI-Pages
**Problem:** Pages greifen direkt auf Repositories zu statt über Agents/Services. Beispiele:
- `positionen.py`: `get_positions_repo()`, `_market_repo.get_price()`, `app_config.get()`
- `portfolio_chat.py`: `repo.get_portfolio()` direkt in UI
- `rebalance_chat.py`: `_positions_repo.get_portfolio()` + `_analyses_repo.get_latest_bulk()`

**Impact:** UI-Code vermischt mit Business Logic. Schwer testbar (Pages haben keine Tests). Datenbeschaffung bei jedem Rerun (Performance).

**Lösung:** Service-Layer (z.B. `PortfolioService`, `DashboardService`) kapselt Repo-Zugriffe. Pages sprechen nur mit Services.

**Files:** `pages/positionen.py`, `portfolio_chat.py`, `rebalance_chat.py`, `portfolio_story.py`, `fundamental.py`, `statistics.py`

#### [DEBT-5] [P1] LLM direkt in positionen.py instanziiert — kein Usage-Tracking
**Problem:** `_generate_story_proposal()` in `positionen.py:29–52` erstellt `ClaudeProvider` direkt mit hartkodiertem Modell, kein Usage-Tracking Callback.

**Impact:** Verwendung wird nicht getrackt (nicht in Cost/Statistics). Modell nicht über `AppConfigRepository` konfigurierbar. Umgeht gesamtes Tracking-System.

**Lösung:** LLM-Calls in Agent/Service-Klasse verschieben, mit `on_usage` Callback verkabeln.

**Files:** `pages/positionen.py` (Zeilen 29–52), `pages/settings.py` (Zeilen 184–191)

#### [DEBT-6] [P2] Private Attribut-Zugriff aus Pages — verletzt Kapselung
**Problem:** Pages greifen direkt auf private Attribute von Agents zu:
- `dashboard.py:56`: `market_agent._market.get_latest_fetch_time()`
- `marktdaten.py:33`: `agent._market.get_latest_fetch_time()`
- `analyse.py:136`: `agent._market.get_historical()`
- `research_chat.py:17`: `agent._llm.model`
- `portfolio_chat.py:22, 28–30`: `agent._llm.model`

**Impact:** Kapselung verletzt. Schwer zu refaktorieren. Abhängigkeit von Implementierungsdetails.

**Lösung:** Öffentliche Properties/Methods (z.B. `agent.model`, `agent.get_latest_fetch_time()`) exponieren.

**Files:** `pages/dashboard.py`, `marktdaten.py`, `analyse.py`, `research_chat.py`, `portfolio_chat.py`, `rebalance_chat.py`

#### [DEBT-7] [P2] state.py ist ein God-Module
**Problem:** `state.py` importiert alle 13 Agents, alle 16 Repositories, versteckt hinter `@st.cache_resource` Factories.

**Impact:** Massive Abhängigkeit. Jeder neue Agent verlängert Datei. Import-Error in einem Agenten lädt ganze App.

**Lösung:** Dependency-Registry mit Lazy-Loading oder Module-per-Feature-Struktur.

**Files:** `state.py`

#### [DEBT-8] [P2] migrate_db() wird an 3 unabhängigen Stellen aufgerufen
**Problem:** Migrations werden aufgerufen in:
1. `state.py:57` (App startup)
2. `agents/market_data_agent.py:344` (Background thread)
3. `core/scheduler.py:357–358` (Scheduler)

**Impact:** Keine zentralen Migration-Guard. Schwer zu debuggen wenn Migrations asymmetrisch laufen.

**Lösung:** Single Entry-Point für Migrations (z.B. `migrate_if_needed()` Guard), oder Background-Services kriegen bereits-initialisierte Connections.

**Files:** `state.py`, `agents/market_data_agent.py`, `core/scheduler.py`, `core/storage/base.py`

---

### Async & Events

#### [DEBT-9] [P2] asyncio.run() + nest_asyncio Anti-Pattern
**Problem:** Streamlit-Pages rufen `asyncio.run()` direkt auf (~17 Stellen). `nest_asyncio.apply()` als Workaround in `state.py` patcht den globalen Event-Loop.

**Impact:** Nicht produktionstauglich. Anti-Pattern für Streamlit. Race Conditions bei gleichzeitigen Requests möglich.

**Lösung:** Durchgehend async-kompatible Streamlit-Integration (z.B. `st.experimental_fragment` für async Teile) oder Task-Queue.

**Files:** `state.py` (Zeile 5-8), 17+ Pages

---

### Testing & Quality

#### [DEBT-10] [P2] Pages sind vollständig ungetestet (19 Dateien, 0 Tests)
**Problem:** Alle `pages/*.py` Dateien enthalten Business Logic aber keine Tests. Beispiele:
- `_generate_story_proposal()` in `positionen.py`
- Formatting-Funktionen in `dashboard.py`
- Session State Management in vielen Pages

**Impact:** Regressionen sind schwer zu finden. UI-Logic kann ungetestet brechen.

**Lösung:** Factories/Services aus Pages extrahieren und testen, Pages selbst haben minimale Logik.

**Files:** All `pages/*.py`

#### [DEBT-11] [P3] Keine Coverage-Konfiguration
**Problem:** `pytest.ini` hat keine `--cov` Einstellungen. `.coverage` existiert, aber kein Coverage-Ziel ist definiert.

**Impact:** Unbekannte tatsächliche Coverage. Schwer zu messen ob neue Code-Pfade getestet sind.

**Lösung:** Coverage-Target (z.B. >80%) in pytest.ini, `--cov=.` in CI.

**Files:** `pytest.ini`, `.github/workflows/` (falls vorhanden)

---

### Dependencies & Tooling

#### [DEBT-12] [P2] peewee 4.0.4 ist installiert aber nicht in requirements.txt
**Problem:** `peewee` ist eine Dependency (vermutlich transitive), erscheint aber nicht in `requirements.txt`.

**Impact:** Fresh install via `pip install -r requirements.txt` würde fehlen. Nicht reproduzierbar.

**Lösung:** `peewee` explizit zu `requirements.txt` hinzufügen oder Dependency überprüfen ob noch notwendig.

**Files:** `requirements.txt`

#### [DEBT-13] [P3] Keine oberen Versionsgrenzen in requirements.txt
**Problem:** Alle Packages spezifiziert als `>=` ohne obere Grenze. `langfuse>=2.0.0` aber installiert `3.7.0`.

**Impact:** Breaking Changes in zukünftigen Releases können Installation brechen.

**Lösung:** Lock-File (`requirements.lock` oder `poetry.lock`) oder präzisere Constraints.

**Files:** `requirements.txt`

---

### Bugs & Minor Debt

#### [DEBT-14] [P3] agentmonitor.py nicht in app.py Navigation
**Problem:** `/pages/agentmonitor.py` existiert als Datei, erscheint aber nicht in `st.navigation()`.

**Impact:** Seite ist nur via direktem URL-Aufruf erreichbar.

**Solution:** Seite zu Navigation hinzufügen oder löschen wenn nicht mehr nötig.

**Files:** `app.py`, `pages/agentmonitor.py`

#### [DEBT-15] [P3] Easter-Egg mit abgelaufenem Datum
**Problem:** `_EASTER_SUNDAY = date(2026, 4, 5)` und `_EGG_ACTIVE_UNTIL = date(2026, 4, 6)` in `dashboard.py:21–22` sind hart eincodiert.

**Impact:** Toter Code ab 2026-04-07 (bereits abgelaufen ab heute 2026-04-12). Harmlos aber confusing.

**Lösung:** Datum entfernen oder Dynamic-Easter-Egg-System bauen.

**Files:** `pages/dashboard.py` (Zeilen 21-22)

#### [DEBT-16] [P3] O(n) Einzeldeletes in portfolio_agent.py
**Problem:** `_tool_clear_portfolio()` und `_tool_clear_watchlist()` loopen und rufen `delete()` einzeln auf.

**Impact:** Ineffizient, O(n) Transaktionen statt 1. Auch weniger atomar.

**Lösung:** `DELETE FROM positions WHERE in_portfolio = 1` o.ä.

**Files:** `agents/portfolio_agent.py` (Zeilen 399–413)

---

### Investment Kompass & Agents (2026-04-13)

#### [DEBT-17] [P2] Skills nicht in Datenbank gepflegt
**Problem:** 6 Strategien (FARMER, VALUE, GROWTH, BALANCE, CRISIS-RESILIENCE, TAX-OPTIMIZED) sind nur im Code/Design definiert, nicht als Skill-Einträge in der Datenbank gespeichert.

**Impact:** Pages laden Skills aus DB via `skills_repo.get_by_area()`, finden nichts → leere Auswahl oder Fallback. User können Strategien nicht wählen.

**Lösung:** Seed-Daten (`config/default_skills.yaml` oder `seed_demo.py`) mit allen 6 Strategien + usecase-spezifischen Prompts erstellen.

**Files:** `agents/investment_compass_agent.py`, `config/default_skills.yaml`, `scripts/seed_demo.py`

#### [DEBT-18] [P2] Prompts nicht skill+usecase kombiniert
**Problem:** Investment Kompass Phase 2 injiziert skill_prompt, aber Prompts sind nicht usecase-spezifisch für jede Skill.
- Beispiel: ALLOCATION + Farmer Strategy sollte Dividenden-fokussiert sein, aber aktueller Prompt ist generic
- Aktuelle Architektur: ALLOCATION prompt + skill_prompt konkateniert, aber nicht intelligent kombiniert

**Impact:** Skills modifizieren Behavior nicht wirklich. Farmer Strategy und Value Strategy erzeugen ähnliche Outputs.

**Lösung:** Skill-Datenbank sollte usecase_mapping haben — pro Skill 4 Prompts (ALLOCATION, REBALANCING, WITHDRAWAL, ANALYSIS).

**Files:** `agents/investment_compass_agent.py` (Prompts Zeilen 152–186), `core/storage/skills.py` (Skill-Schema)

#### [DEBT-19] [P2] Hardcoded "Antworte auf Deutsch" verletzt i18n
**Problem:** Alle neuen Agent-Prompts (Investment Kompass, Watchlist Checker, etc.) enthalten hardcoded `"Antworte auf Deutsch"`.

**Impact:** Verletzung von DEBT-3 (Magic Strings). App hat i18n-System, sollte das nutzen statt hardcoded Sprache.

**Lösung:** Prompts sollten `{LANGUAGE}` placeholder haben, zur Laufzeit mit `app_config.get("ui_language")` gefüllt.

**Files:** `agents/investment_compass_agent.py` (Zeilen 152–186), `agents/watchlist_checker_agent.py` (Zeilen 44–84)

#### [DEBT-20] [P3] Neue Agents nicht in Settings/Monitoring sichtbar
**Problem:** Investment Kompass, Watchlist Checker sind implementiert, aber tauchen nicht auf in:
- Skill-Management UI
- Agent Runs Übersicht
- Settings-Seite (wo User LLM-Auswahl treffen können)

**Impact:** User können nicht sehen, welche Agents laufen oder mit welchem Modell.

**Lösung:** Agent Runs-Page erweitern oder neue "Agent Management" Dashboard erstellen.

**Files:** `pages/` (neue oder bestehende Settings-Page)

---

## Done

#### [P2] [FEAT] Storychecker: Alle Positionen auf einmal prüfen
`batch_check_all()` async Methode im `StorycheckerAgent`: iteriert alle Positionen mit Story sequenziell, 15s Sleep zwischen Calls wegen Rate Limit. `start_session_async()` als async Pendant zu `start_session()`. Storychecker-Page: "Alle prüfen" Expander oben mit Background-Thread-Pattern (session_state), Skill-Auswahl, Auto-Refresh alle 5s, Fehler-Count in Erfolgsmeldung. Konsistent mit Fundamental- und Konsens-Lücken-Page.

#### [P2] [IMPR] Rebalance: Cloud-Agent-Ergebnisse in Kontext einbeziehen
`_build_portfolio_context()` lädt jetzt `fundamental`- und `consensus_gap`-Verdicts für alle Portfolio-Positionen und Watchlist-Kandidaten. Positionszeilen zeigen bis zu 3 Signale: `thesis: 🟢 intact | fundamental: 🟢 unterbewertet (+24%) | gap: 🟢 wächst`. Watchlist-Kandidaten ebenfalls mit Cloud-Verdicts angereichert. Graceful: fehlende Analysen werden einfach weggelassen.

#### [P2] [IMPR] Demo-Daten: Analysen für alle Positionen
`seed_demo.py` befüllt `position_analyses` mit fiktiven aber plausiblen Ergebnissen für alle 3 Agenten (storychecker, fundamental, consensus_gap). Summaries mit `[Demodaten]` gekennzeichnet. Werden automatisch überschrieben sobald echte Analysen laufen (neuester Eintrag gewinnt).

#### [P2] [BUG] Scheduling: Agent-Wechsel aktualisiert Skills nicht
Agent-Selectbox im "Geplante Aufgaben"-Formular war innerhalb `st.form` — kein Rerun bei Änderung, Skills-Dropdown blieb statisch. Fix: Agent-Selectbox aus dem Form herausbewegt (triggert Rerun), Skills werden reaktiv neu geladen.

#### [P2] [BUG] Strukturwandel-Scanner: leeres Ergebnis ohne Fehlermeldung
`web_search_20250305` wird von Haiku nicht als Server-Side-Tool ausgeführt — Claude emittiert einen `tool_use`-Block, der nicht in `CLIENT_TOOL_NAMES` ist → agentic loop bricht sofort ab → `response.content = ""`. Fix: Sonnet als Default für alle web-search-lastigen Agenten (structural_scan, consensus_gap, fundamental). Agentic loop zusätzlich auf `stop_reason == "end_turn"` geprüft.

#### [P1] [IMPR] Input validation when creating positions
Agent-extracted values validated before saving: quantity/price positive, purchase date not in the future, ticker format check. UI form: `max_value=date.today()` on date input, ticker required for auto-fetch classes.

→ [GitHub Issue #7](https://github.com/esc1899/wealth_management/issues/7)

#### [P2] [IMPR] Auto-fetch market data on position creation
When a new position with a ticker is added (via form or portfolio chat), current price is automatically fetched via `MarketDataFetcher`. Graceful fallback if fetch fails. Non-blocking.

→ [GitHub Issue #6](https://github.com/esc1899/wealth_management/issues/6)

#### [P2] [IMPR] Portfolio Chat: validation + save confirmation
`_tool_add_portfolio()` validates date format, future dates, quantity > 0, price >= 0. Returns `{"error": "..."}` on failure. Follow-up prompt requests explicit German confirmation with all saved fields (name, ticker, quantity+unit, purchase price, purchase date).

#### [P2] [FEAT] Invest/Rebalance: Weitere Strategien als Skills
Warren Buffett, Norwegischer Pensionsfonds, André Kostolany als wählbare Skills in `default_skills.yaml` geseedet. `SkillsRepository.seed_new_skills(area, list)` fügt neue Skills in bestehende Areas ein (INSERT OR IGNORE per name+area).

#### [P3] [FEAT] Fundamentalwert-Agent ✅ UMGESETZT
`FundamentalAgent` (Säule 3): KGV, P/B, EV/EBITDA, DCF, PEG, Analystenkursziele. Verdicts (unterbewertet/fair/überbewertet/unbekannt) mit Fair-Value-EUR und Upside-% in `position_analyses`. Neue Nav-Seite in "Claude-Strategie". Skills: Fundamentalbewertung Standard, Dividendenbewertung. Default-Modell: Sonnet (benötigt web_search_20250305).

#### [P3] [FEAT] Grosses Experiment: "Claude-Strategie Strukturwandel" ✅ UMGESETZT
`StructuralChangeAgent` (Säule 1): Monatlicher Web-Search-Scan, identifiziert strukturelle Themen vor dem Konsens, fügt Kandidaten direkt zur Watchlist hinzu. `ConsensusGapAgent` (Säule 2): Analysiert Portfolio-Positionen auf Konsens-Lücke, Verdicts (wächst/stabil/schließt/eingeholt) in `position_analyses`. Neue Nav-Gruppe "Claude-Strategie". Skills: Strukturwandel-Identifikation, Second-Order Effects, Konsens-Lücken-Standard, Contrarian-Check. Rebalance-Skill "Claude-Strategie (Strukturwandel)". Scheduling für beide Agenten.

#### [P2] [IMPR] Modellauswahl pro Agent
`config.CLAUDE_MODELS` aus Umgebungsvariable (Default alle drei Modelle, per `.env.work` einschränkbar). `state.py`: `_get_agent_model(agent_key, type, default)` — liest zuerst agentenspezifischen Key (`model_ollama_portfolio`), dann globalen Key, dann Env-Default. Settings-Seite: 2 Ollama-Dropdowns + 3 Claude-Dropdowns, ein Save-Button, `st.cache_resource.clear()` bei Speicherung.

#### [P2] [FEAT] Datenpflege: Anlagearten & Stammdaten
`anlageart` (TEXT, optional) in `positions` (DB-Migration + `init_db`). `AssetClassConfig.anlagearten: List[str]` — befüllt aus `asset_classes.yaml`. Position-Formular zeigt konditionalen Selectbox nur wenn Anlagearten vorhanden. Detail-Dialog zeigt Anlage-Art an. Portfolio-Agent-Tool um optionales `anlageart`-Feld erweitert.

#### [P2] [FEAT] Scheduling: Agents automatisch einplanbar
`scheduled_jobs`-Tabelle + `ScheduledJobsRepository`. `AgentSchedulerService` (eigene BackgroundScheduler-Instanz, eigene DB-Verbindung für Thread-Safety). News-Agent als erster planbarer Agent. Settings-Seite: Liste bestehender Jobs (Enable/Disable-Toggle, Löschen), Formular für neue Jobs (Skill, Häufigkeit, Zeit, Modell). `reload_jobs()` bei jeder Änderung.

#### [P2] [FEAT] Investment Search: Begründung als Story absichern
`add_to_watchlist`-Tool in `search_agent.py` um Feld `story` erweitert. Wird beim Tool-Aufruf von Claude gefüllt und als `Position.story` gespeichert.

#### [P2] [FEAT] Krypto-Warnung
Warnhinweis im Detail-Dialog für `Kryptowährung`-Positionen. Krypto-Positionen im Rebalance-Snapshot mit `⚠️ [HOCHSPEKULATIV — Krypto]` markiert.

#### [P2] [FEAT] Tages-G/V in Analysen + automatisch aktualisierte Kurse
`PortfolioValuation` um `day_pnl_eur` / `day_pnl_pct` erweitert. `MarketDataRepository.get_prev_close()` liefert zweitletzten historischen Schlusskurs. Analyse-Seite zeigt Tages-Performance-Chart. Auto-Fetch beim Seitenaufruf wenn letzte Kurse > 1 Stunde alt.

#### [P1] [IMPR] Rebalancing: Geld und Immobilien separat behandeln
`_build_portfolio_context()` in `rebalance_agent.py` aufgeteilt: "Handelbares Portfolio" (Börsentitel) vs. "Nicht-handelbares Vermögen" (Festgeld, Bargeld, Immobilie, Grundstück). Agent-Kontext macht die Trennung explizit.

#### [P1] [FEAT] Invest/Rebalance: Josef's Regel (Hidden Skill)
Hidden Skill (`area=rebalance`) in `config/default_skills.yaml` geseedet. LLM wird silently über Zielverteilung 1/3 Aktien / 1/3 Renten+Geld / 1/3 Immobilien instruiert. Portfolio-Snapshot liefert Josef's Regel-Tabelle (Ist vs. 33%-Ziel). `SkillsRepository.get_system_skills(area=)` mit optionalem Area-Filter erweitert.

#### [P1] [FEAT] Invest/Rebalance: Position vom Rebalance ausschließen
`rebalance_excluded` Spalte in `positions` (DB-Migration + `init_db`). Position trägt trotzdem zu Josef's Regel und Gesamtvermögen bei. Toggle im Detail-Dialog der Positionen-Seite. Im Snapshot mit `[AUSGESCHLOSSEN]` markiert.

#### [P1] [IMPR] Invest/Rebalance: Watchlist-Kandidaten einbeziehen
Watchlist-Positionen mit Story erscheinen als "Kaufkandidaten"-Sektion im Snapshot — ohne Mengen/Preise. Nur Positionen die nicht schon im Portfolio-Teil sind.

#### [P1] [BUG] Rebalance crashes without error message
`start_session()` and `chat()` in `pages/rebalance_chat.py` are both wrapped in try/except with `st.error()` display.

#### [P1] [BUG] DB migration: OperationalError on existing DBs (in_watchlist index)
`CREATE INDEX idx_positions_in_watchlist` war in `init_db` — schlägt fehl wenn `positions`-Tabelle schon ohne die Spalte existiert. Fix: Index in `migrate_db` verschoben (nach ALTER TABLE).

#### [P1] [BUG] Duplicate key error when position is in portfolio AND watchlist
`_render_table` verwendete `det_{pos.id}` als Button-Key — bei gleicher Position in beiden Listen doppelt. Fix: `key_prefix` Parameter (`pf_` / `wl_`).

#### [P2] [BUG] Storychecker: nur Watchlist-Positionen prüfbar
Storychecker hat nur `get_watchlist()` geladen — Portfolio-Positionen mit Story wurden nicht angezeigt. Fix: `get_all()`.

#### [P2] [BUG] Story-Skill-Selector immer disabled
`disabled=not bool(form_story)` innerhalb `st.form` reagiert nicht auf live Eingabe. Fix: `disabled` entfernt.

#### [P2] [BUG] Dashboard-Summe falsch (Geld-Anlagen)
Festgeld + Bargeld hatten `manual_valuation: false` → kein Schätzwert-Dialog → `current_value = None`. Fix: `manual_valuation: true` + `estimated_value` in extra_fields. Bargeld mit `unit=€` nutzt `quantity` direkt als Wert.

#### [P2] [BUG] Löschen von Watchlist springt auf Portfolio
Tab-Layout hat beim Rerun die Tab-Selektion verloren. Fix: Tabs entfernt — Portfolio + Watchlist jetzt untereinander mit Subheadern.

#### [P2] [BUG] Dezimalzahlen als Punkt statt Komma
`f"{x:,.2f}"` → englisches Format. Fix: `_fmtnum()` Hilfsfunktion mit deutschem Format (`1.234,56`).

#### [P2] [IMPR] Empfehlung / recommendation_source inkonsistent
`recommendation_source` war im Modell, aber nicht im Formular sichtbar. Fix: "Empfohlen von" Freitextfeld im Formular + Detail-Dialog.

#### [P2] [IMPR] Name nicht aus Tickersuche vorausgefüllt
FIGI Apply setzte nur `_pos_ticker`, nicht `_pos_name`. Fix: `chosen["name"]` → `_pos_name` wenn noch leer.

#### [P2] [IMPR] Kein Feedback nach Speichern
`st.success()` vor `st.rerun()` wird nicht angezeigt. Fix: `_pos_just_saved` Session-State-Flag → Erfolgsanzeige oben nach Rerun.

#### [P2] [IMPR] Alphabetisch sortieren in Positions-Tabellen
`_render_table` sortiert jetzt nach `name.lower()`.

#### [P2] [IMPR] Streamlit Deploy-Button ausblenden
`.streamlit/config.toml` mit `toolbarMode = "minimal"`.

#### [P2] [FEAT] System Health / Setup Checks
`core/health.py` mit statischen Checks + Ollama-Connectivity-Check.

#### [P1] [FEAT] Investment Search Agent (Cloud ☁️)
`SearchAgent` mit `SearchRepository` + session-based chat.

#### [P1] [FEAT] Invest & Rebalance Agent (Private 🔒)
`RebalanceAgent` using local Ollama.

#### [P2] [IMPR] Seed example skills in all environments
`config/default_skills.yaml` covers all areas.

#### [P1] [FEAT] Multi-environment setup
`ENV_PROFILE=work` for machine-specific overrides (OLLAMA_HOST, DB_PATH, etc.)

#### [P2] [FEAT] News Agent (Cloud ☁️)
`NewsAgent` — stateless, one-shot digest per run.

#### [P1] [IMPR] Rename "Rebalance" to "Invest / Rebalance"

#### [P2] [IMPR] News Digest: expandable detail per position

#### [P2] [IMPR] News Digest: session history
