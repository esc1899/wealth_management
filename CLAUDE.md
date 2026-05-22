# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run all tests (coverage enabled by default via pytest.ini)
pytest tests/

# Run a single test file or specific test
pytest tests/unit/test_xyz.py
pytest tests/unit/test_xyz.py::TestClass::test_method

# Run unit tests only (fast)
pytest tests/unit/

# Run integration tests only (use real SQLite :memory:, slower)
pytest tests/integration/

# Start the app (development)
streamlit run app.py

# Start on the fixed Dock-app port
streamlit run app.py --server.port 6655

# Restart after DB-schema, agent-signature, or repository-method changes
kill $(pgrep -f "streamlit run") && streamlit run app.py

# Restart the LaunchAgent (Dock-App) — use this when .env was changed
launchctl unload ~/Library/LaunchAgents/com.erik.wealth-management.plist
launchctl load ~/Library/LaunchAgents/com.erik.wealth-management.plist

# Scheduled job debugging — real tracebacks are here, not in the UI
tail -100 /tmp/wm_streamlit.log | grep -A5 "Error\|Exception\|Traceback"
```

---

## Reference Implementations

When building new components, use these as canonical examples:

| What to build | Reference file |
|---|---|
| Cloud agent — batch only (no chat) | `agents/consensus_gap_agent.py` |
| Cloud agent — session-based chat + batch | `agents/fundamental_analyzer_agent.py` |
| Local Ollama agent | `agents/watchlist_checker_agent.py` |
| Repository (sessions + messages tables) | `core/storage/fundamental_analyzer.py` |
| Analysis page (batch + inline history) | `pages/consensus_gap.py` |
| Chat page (session nav + multi-turn) | `pages/fundamental_analyzer.py` |

## State Layer — 5-Module DI Factory

`state.py` is a re-export facade. All singletons live in the four implementation modules:

| Module | Responsibility |
|---|---|
| `state_db.py` | `get_db_connection()` — one SQLite connection + runs `migrate_db()` once at startup |
| `state_repos.py` | `@st.cache_resource` repository singletons |
| `state_agents.py` | `@st.cache_resource` agent singletons |
| `state_services.py` | Service singletons (AnalysisService, PortfolioService, …) |

Pages always import from `state`, never from `state_agents` / `state_repos` directly.

## DB Migrations

All schema changes go into the single `migrate_db()` function in `core/storage/base.py`. It runs once per process start via `state_db.py`. After any schema change: **restart Streamlit** (cached connection won't re-run migrations).

## Adding a New Page

1. Create `pages/<name>.py`
2. Add `st.Page(...)` entry in the correct section dict inside `app.py`'s `st.navigation()` call
3. Add a smoke test in `tests/unit/` (AppTest pattern, see existing smoke tests)

## Required Environment Variables

```
ENCRYPTION_KEY=<Fernet key>   # required — generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ANTHROPIC_API_KEY=<key>       # required for all cloud agents
APP_PASSWORD=<password>       # optional — enables login gate
DEMO_MODE=true                # optional — switches DB to data/demo.db
```

---

# Arbeitsweise in diesem Projekt

## 🔒 Dieses Projekt ist öffentlich auf GitHub

**Security ist nicht optional.** Jede Änderung am Code kann von beliebigen Personen gelesen und ausgeführt werden. Das bedeutet konkret:

- Keine Secrets, API-Keys oder Encryption-Keys in den Code oder in Git-History committen
- User-Input (Datei-Inhalte, Formularfelder, externe Daten) niemals ungefiltert in SQL, Markdown, Shell oder Subprozesse einbauen
- Neue Input-Quellen (Files, APIs, Websockets) sofort auf Injection-Vektoren prüfen: URL-Protokolle, Pfad-Traversal, Dateigröße
- Bei `st.markdown()`: kein `unsafe_allow_html=True` ohne explizite Prüfung; keine f-Strings mit User-Daten
- Alle Abhängigkeiten (requirements.txt) auf bekannte CVEs prüfen bevor sie hinzukommen

**Bisherige Security Reviews:** 2026-04-24 (Red Team, alle HIGH/MEDIUM fixes), 2026-05-09 (Cowork ingest: URL-Injection, Markdown-Injection, Dateigrößen-Limit), 2026-05-11 (FEAT-34–39 + Sonnet-Switch: SQL-Injection, Privacy-Boundary, LLM-Prompt-Injection, XSS — alle clean)

**LLM Prompt-Injection via Web Search**: Sonnet ist fähiger als Haiku und folgt komplexeren Anweisungen. Malicious web pages, die von SearchAgent/NewsAgent/StructuralChangeAgent indexiert werden, könnten versuchen, Instruktionen in die LLM-Antwort zu injizieren. Mitigation: Cloud-Agents haben keinen Schreibzugriff auf die DB (außer news_repo/analyses_repo) und sehen keine Private-Daten. Risiko ist begrenzt, aber bei neuen Web-Search-Agents auf diesen Vektor prüfen.

---

## 🚨 Kritische Architektur-Invarianten — immer gültig, nie brechen

Diese Regeln gelten für **jede** Änderung, unabhängig vom Task. Bei Unsicherheit: ARCHITECTURE.md lesen.

### 1. Privacy-Grenze: Local vs. Cloud LLM

**Sensitive Portfolio-Daten verlassen niemals das lokale System.**

| Provider | Agents | Darf sehen |
|---|---|---|
| **Ollama (lokal 🔒)** | PortfolioAgent, PortfolioStoryAgent, WatchlistCheckerAgent, MarketDataAgent | Alles — Positionen, Namen, Stories, Zahlen |
| **Claude API (Cloud ☁️)** | ResearchAgent, NewsAgent, SearchAgent, StorycheckerAgent¹, ConsensusGapAgent, StructuralChangeAgent, FundamentalAnalyzerAgent, WealthSnapshotAgent, **CapitalAllocatorAgent** | Nur öffentliche Daten (Ticker, Marktdaten, News) |

¹ **StorycheckerAgent Ausnahme**: Sendet `position.name` + `position.story` an die Claude API — bewusstes Design, da der Storychecker die Investment-These braucht um sie zu prüfen. Stories verlassen also das lokale System. Das ist ein akzeptierter Privacy-Trade-off, aber keine neue Einführung ohne explizite Zustimmung.

→ Neuer Agent mit Portfolio-Zugriff? → **muss Ollama sein**
→ Neuer Cloud-Agent? → **kein Zugriff auf Positionen/Stories/Namen** (außer StorycheckerAgent-Muster mit expliziter Begründung)

### 2. Zweisprachigkeit (i18n)

Die App ist **Deutsch/Englisch** schaltbar. Gilt für jeden neuen Code:

- Agents: `language: str = "de"` Parameter auf allen Analyse-Methoden — dynamisch via `agent_language.py`
- Pages: `current_language()` vor Background-Thread-Spawn captern (session_state nicht thread-safe)
- Verdict-Codes bleiben **immer Deutsch** (`unterbewertet`, `intact`, `wächst`, …) — das sind DB-Identifier, keine UI-Texte
- Hardcodierte deutsche UI-Labels sind **technische Schulden**, keine neue einführen
- Translation-Keys: `translations/de.yaml` + `translations/en.yaml` — Zugriff via `from core.i18n import t; t("section.key")`

### 3. Session-Persistenz für Chat-Agents

Multi-turn Agents → **immer DB-Persistenz**, niemals in-memory Dict.
Muster: `start_session()` → `repo.create_session()`, `chat()` → `repo.get_messages()` + `repo.add_message()`
Referenz-Implementierung: StorycheckerAgent / FundamentalAnalyzerAgent

### 4. Verschlüsselte Felder

Position-Namen, Stories, Notes, extra_data (JSON) sind **Fernet-verschlüsselt** in der DB.
Nie direkt als Plaintext schreiben — immer über das Repository-Layer.

### 5. Neue Agents: Checkliste

Vor dem ersten Commit prüfen:
- [ ] Richtiger Provider (Ollama vs. Cloud)? Privacy-Grenze beachtet?
- [ ] Cloud-Agent: `PublicPosition` statt `Position` verwenden (`core/storage/models.py`)
- [ ] `language` Parameter vorhanden?
- [ ] Session-Persistenz (wenn Chat)? DB-Repo erstellt?
- [ ] `state.py` Factory-Funktion ergänzt?
- [ ] Verdict-Config in `core/ui/verdicts.py` → `VERDICT_CONFIGS` dict ergänzt?
- [ ] Tests: Unit + Integration + Page Smoke?

---

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


## Vor jeder Änderung
- Alle relevanten Dateien lesen, bevor Code geändert wird
- Bei nicht-trivialen Aufgaben: Plan Mode nutzen (`/plan`)
- Verwandte Fehler zusammen beheben — keine Einzelfix-Iterationen

## Architektur-Guards (FEAT-18)

**Modular Checks Pattern**: Portfolio-level und Position-level Checks folgen dem gleichen Muster:
- Jeder Check hat eine eigene **Skill-Area** (z.B. `portfolio_stability`, `portfolio_cash_rule`)
- Kein Skill in Area → Check wird übersprungen mit Info-Meldung (kein Fehler)
- **Page Renderer**: Separate Funktionen für jeden Check (`_render_*_check()`)
- **Agent Methoden**: Unabhängige Analyse-Methoden per Check (z.B. `analyze_stability()`, `analyze_story_and_performance()`)

Dies erlaubt Usern, Checks selektiv zu aktivieren/deaktivieren durch Skills im `/skills` Admin-Interface.

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

## Streamlit @st.cache_resource — Fallstricke (DEBT-20)

**Lernpunkt (2026-04-29):** FundamentalAnalyzerAgent DB-Persistenz konnte nach Code-Änderungen nicht funktionieren, obwohl die Implementierung korrekt war. Root cause: @st.cache_resource hielt eine alte DB-Connection im RAM.

### Das Problem

`@st.cache_resource` speichert Ressourcen (DB-Connections, Agent-Singletons) für die **gesamte Lebensdauer des Python-Prozesses**.

**Fallstrick 1: DB-Migrationen werden nicht erneut ausgeführt**
- `get_db_connection()` in `state_db.py` ruft `migrate_db()` **einmalig** beim Startup auf
- Wenn Code sich ändert und neue Tabellen hinzufügt: Die bereits laufende App-Instanz hat die alte Verbindung und sieht die neuen Tabellen nicht
- `sqlite3.OperationalError: no such table` bei der ersten Query nach Code-Change

**Fallstrick 2: Agent-Singletons halten alte Konfiguration**
- Wenn sich eine Agent-Signatur ändert (z.B. neuer Parameter `fa_repo`): Die gecachte Instanz wurde mit alten Parametern erstellt
- UI-Code, der den neuen Parameter nutzt, crasht

**Fallstrick 3: Config-Verwirrung**
- `config.DB_PATH` zeigt auf `data/portfolio.db`
- Ist leicht, manuell eine andere DB-Datei zu manipulieren (z.B. `wealth.db` im Root)
- Nach Restart lädt die App wieder die echte DB → Verwirrung über "wo waren meine Änderungen"

### Lösung

1. **Nach Code-Änderungen, die DB-Schema oder Agent-Signaturen ändern: Streamlit neu starten**
   - `ps aux | grep streamlit` → PID finden → `kill <PID>`
   - Dann: `streamlit run app.py`

2. **In Entwicklung: Visibility in DB-Init**
   - `state_db.py` loggt welche DB-Datei geladen wird und wann Migrationen laufen
   - Bei unerwarteten "no such table"-Fehlern: Check Logs um zu sehen ob `migrate_db()` aufgerufen wurde

3. **Vor Merges: Changelog mit "DB-Schema-Änderung" kennzeichnen**
   - Deployment-Teams wissen: "Streamlit muss restarted werden"

4. **Tests müssen kritische Tabellen verifizieren**
   - Integration-Test prüft dass all erwarteten Tabellen nach `migrate_db()` existieren
   - Fehler im Test würde Pre-Merge CI abfangen

