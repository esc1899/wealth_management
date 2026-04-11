# Arbeitsweise in diesem Projekt

## 📍 Dokumentations-Struktur (Single Source of Truth)

Damit zukünftige Sessions alles finden:

| Datei | Inhalt | Wer updatet |
|---|---|---|
| **CLAUDE.md** (diese Datei) | Arbeitsweise, Process, Stack-Fallstricke | Claude bei Prozess-Änderungen |
| **ARCHITECTURE.md** | Architektur-Entscheidungen, Design-Patterns, Data-Model | Claude bei Arch-Änderungen |
| **BACKLOG.md** | Features (geplant + abgeschlossen), Status, Prioritäten | User/Claude beim Planning |
| **Memory/user_profile.md** | Wer ist Erik, wie arbeitet er | Claude nach User-Feedback |
| **Memory/feedback.md** | Feedback zur Arbeitsweise mit Claude | Claude nach User-Feedback |
| **Memory/private_skills.md** | Persönliche Skills (Wu-Wei, Lindy+Potential, etc) | User-Configured |

**Regel**: Projekt-Sachen → Git-Repo (CLAUDE/ARCHITECTURE/BACKLOG). Persönliche Erkenntnisse → Memory. Nicht duplizieren.

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
