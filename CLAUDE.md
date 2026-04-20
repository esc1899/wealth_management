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

