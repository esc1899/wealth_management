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

## Changelog (CLAUDE.md Prozess-Updates)

Damit man sieht welche Arbeitsweise-Änderungen wann gemacht wurden:

### 2026-04-12
- **Added**: Architektur-Guards Sektion — Anti-Patterns und richtige Patterns dokumentieren
- **Added**: Constants-Registry Guard (hardcoded strings vermeiden)
- **Added**: Service-Layer Guard (LLM und Repos nicht in Pages)
- **Added**: Migration Guard (single entry-point für DB-Migrationen)
- **Reason**: DEBT-1, DEBT-3, DEBT-4, DEBT-5, DEBT-6, DEBT-8, DEBT-9 wurden identifiziert — strukturelle Guards verhindern Wiederholung

### 2026-04-11
- **Added**: Dokumentations-Struktur Tabelle (Single Source of Truth)
- **Added**: Plan Mode Motto "try to improve the whole"
- **Initial**: Test-Disziplin, Debug-Hygiene, Commit-Qualität Guidelines

---
