# Arbeitsweise in diesem Projekt

## Vor jeder Änderung
- Alle relevanten Dateien lesen, bevor Code geändert wird
- Bei nicht-trivialen Aufgaben: Plan Mode nutzen (`/plan`)
- Verwandte Fehler zusammen beheben — keine Einzelfix-Iterationen

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
