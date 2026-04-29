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

