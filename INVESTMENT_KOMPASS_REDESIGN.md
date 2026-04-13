# Investment Kompass — Systems Thinking Redesign

## Problem Statement

Aktuell:
1. Agent lehnt Frage ab ✓
2. Aber Skill wird trotzdem ausgeführt ✗
3. Skill-Formulierung ist "dumm" (ignoriert Validierung)
4. Portfolio Story ist nicht zentral im Entscheidungsfluss

**Root Cause**: Fehlendes **Koordinations-System** zwischen Query-Validierung und Skill-Ausführung. Skill ist unabhängig, nicht in Hierarchie eingebunden.

---

## Systems-Thinking Model

### Die 3 Ebenen (nicht linear, sondern verschachtelt):

```
┌─────────────────────────────────────────────────────────────────┐
│ Portfolio Story (Foundation — gibt strategische Richtung)       │
│  - Target Year, Ziel, Priorität                                 │
│  - "Dieses Portfolio ist konservativ, langfristig auf Einkommen"│
│  - → Alle Usecases MÜSSEN diese Story respektieren             │
└─────────────────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────────────┐
│ User Query + Usecase Classification (Agent)                     │
│  - ALLOCATION: "10k investieren"                                │
│  - REBALANCING: "Portfolio umstrukturieren"                     │
│  - WITHDRAWAL: "10k abheben"                                    │
│  - ANALYSIS: "Wie robust?"                                      │
│  - INVALID: "Sag einen Witz" → STOP                            │
│  - → Agent validiert GEGEN Portfolio Story                      │
└─────────────────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────────────┐
│ Skill/Style Selection (Optional, Usecase-abhängig)             │
│  - ALLOCATION → **Skill optional** (Value/Growth/Income)        │
│  - REBALANCING → **Skill optional** (Conservative/Aggressive)   │
│  - WITHDRAWAL → **Skill maybe** (Tax-Optimization??) → maybe NO │
│  - ANALYSIS → **Skill optional** (Stress-Test/Scenario)        │
│  - → Skill ist **Modulator**, nicht Core                        │
└─────────────────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────────────┐
│ Context Building (Ebene 0,1,2)                                  │
│  - Portfolio-Daten                                              │
│  - Analyst-Verdicts (Story-Fit, Fundamental)                   │
│  - Portfolio Story Analysis                                     │
│  - → Usecase bestimmt WELCHE Verdicts relevant sind            │
└─────────────────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────────────┐
│ LLM Execution (Usecase-spezifischer Prompt)                    │
│  - Prompt ändert sich je nach Usecase                           │
│  - Skill (falls vorhanden) ist zusätzlicher Kontext            │
└─────────────────────────────────────────────────────────────────┘
```

### Die Feedback-Schleifen:

1. **Validation Loop**: Portfolio Story → Query-Klassifizierung → Rejection wenn nicht kompatibel
   - Beispiel: Story sagt "Keine Spekulation", User fragt "10k in Crypto?"
   - Agent: "Das passt nicht zu deiner Strategie" → STOP

2. **Context Loop**: Usecase → bestimmt welche Ebene-1 & 2 Daten relevant sind
   - ALLOCATION: "Welche Positionen passen zu meiner Story?"
   - WITHDRAWAL: "Welche Positionen kann ich gehen?"
   - REBALANCING: "Wo bin ich zu schwer gewichtet?"

3. **Skill Loop**: Optional, moduliert HOW (nicht WHETHER)
   - ALLOCATION + Value Skill: "Suche unterbewertete Positionen"
   - ALLOCATION + Growth Skill: "Suche Wachstumspotenzial"
   - Aber: **Beides muss die Story respektieren**

---

## Proposed Architecture

### Phase 1: Query Validation (Agent)

```python
class InvestmentCompassAgent:
    async def analyze(self, user_query: str, skill_name: Optional[str] = None):
        # Step 1: Fetch Portfolio Story (always first!)
        portfolio_story = self._portfolio_story.get_current()
        
        # Step 2: Classify query + validate against story
        usecase, is_valid, reason = self._classify_and_validate(
            user_query=user_query,
            portfolio_story=portfolio_story
        )
        
        if not is_valid:
            return InvestmentAnalysis(
                response=f"⚠️ {reason}",
                lineage={"rejected": True, "reason": reason}
            )
        
        # Step 3: Only if valid, continue to skill + context
        return await self._execute_usecase(usecase, skill_name, portfolio_story)
```

### Phase 2: Usecase-Specific Execution

```python
async def _execute_usecase(self, usecase, skill_name, portfolio_story):
    # Build context based on USECASE (not generic)
    context = await self._build_context_for_usecase(usecase, portfolio_story)
    
    # Skill is OPTIONAL and MODULATING
    skill_context = ""
    if skill_name and self._should_use_skill_for_usecase(usecase):
        skill = self._skills.get(skill_name)
        skill_context = f"\n\n## Strategie: {skill.name}\n{skill.prompt}"
    
    # Usecase-specific system prompt
    system_prompt = self._get_usecase_prompt(usecase)
    system_prompt += f"\n\n## Portfolio Story\n{portfolio_story.story}"
    if skill_context:
        system_prompt += skill_context
    
    # LLM call
    messages = [Message(role=Role.USER, content=system_prompt + "\n\n" + context)]
    response = await self._llm.chat(messages)
    
    return InvestmentAnalysis(
        response=response,
        lineage={"usecase": usecase, "skill": skill_name, "story_version": portfolio_story.id}
    )
```

### Phase 3: Usecase-Specific Prompts

```python
USECASE_PROMPTS = {
    "ALLOCATION": """
Du bist Allokations-Berater. Der Nutzer hat neue Mittel zu investieren.
Beachte:
- Die Portfolio Story gibt die strategische Richtung
- Aktuelle Gewichtung: Ebene 0 Daten
- Welche Positionen sind untergewichtet vs. Story?
- Passt die neue Allokation zur Story?
""",
    
    "REBALANCING": """
Du bist Rebalancing-Analyst. Der Nutzer überlegt sein Portfolio umzustrukturieren.
Beachte:
- Die Story ist der "Kompass" — in welche Richtung abweicht das Portfolio?
- Sind Positionen über/untergewichtet vs. Story + Analyst-Verdicts?
- Welche Positionen stärken die Story, welche schwächen sie?
""",
    
    "WITHDRAWAL": """
Du bist Liquiditäts-Berater. Der Nutzer muss Geld abheben.
Beachte:
- Liquidität erhalten (Renten, Einkommen zuerst?)
- Story-Fit: Welche Positionen kann man gehen, ohne die Story zu brechen?
- Steuern sind sekundär (nur erwähnen wenn relevant)
""",
    
    "ANALYSIS": """
Du analysierst die Robustheit des Portfolios gegen ein Szenario.
Beachte:
- Die Story definiert die Ziele (z.B. "stabiles Einkommen in 5 Jahren")
- Wie robust ist das Portfolio gegen Inflation/Rezession/Zinsanstieg?
- Fehlen Hedges oder Puffer?
"""
}
```

### Phase 4: Skill-Entscheidung (OPTIONAL)

Meine **Empfehlung**: Skills sollten OPTIONAL sein und nur bei **ALLOCATION** + **REBALANCING** sinnvoll.

| Usecase | Skill relevant? | Reason |
|---------|-----------------|--------|
| ALLOCATION | ✓ **Optional** | Value/Growth/Income moduliert Auswahl |
| REBALANCING | ✓ **Optional** | Conservative/Aggressive moduliert Zielgewichte |
| WITHDRAWAL | ✗ **No** | Logik ist fest: "Liquidität + Story-fit" |
| ANALYSIS | ? **Vielleicht** | "Stress-Test" oder "Szenario-Analyse" könnte Skill sein |

**Aber**: Skill-Formulierung muss **Story-aware** sein:

```python
# ❌ FALSCH (ignoriert Story):
skill_prompt = "Optimiere für maximales Wachstum"

# ✅ RICHTIG (respektiert Story):
skill_prompt = """
Optimiere für Wachstum im Rahmen der Story-Richtung.
Die Story sagt: [Story hier einfügen]
Finde Positionen die:
1. Zur Story passen (Analyst-Verdicts prüfen)
2. Wachstumspotenzial haben
3. Nicht zu viel Risiko (gegen Story) einbringen
"""
```

---

## Implementation Roadmap

### Sprint 1: Validation Layer (Kritisch)

1. `_classify_and_validate()` → Usecase + Validierung gegen Story
2. Early return wenn INVALID
3. Update: Tests für alle 4 Usecases

### Sprint 2: Usecase-Specific Context (Wichtig)

1. `_build_context_for_usecase(usecase)` → Filtert Ebene-1/2 Daten
2. ALLOCATION: "Was ist untergewichtet?"
3. REBALANCING: "Wo sind Abweichungen?"
4. WITHDRAWAL: "Was ist liquid + passend?"
5. ANALYSIS: "Stabilität vs. Story-Ziel?"

### Sprint 3: Skill Integration (Nett-zu-haben)

1. `_should_use_skill_for_usecase()` → Entscheidet ob Skill relevant
2. Skill-Prompt mit Portfolio Story erweitern
3. Default: Kein Skill (ist valide)

### Sprint 4: Prompts (Kontinuierlich)

1. Usecase-spezifische System-Prompts schärfen
2. User-Feedback: "Welche Usecases funktionieren gut?"
3. Skill-Formulierungen iterativ verbessern

---

## Emergent Properties (Systems-Effekt)

Wenn das System richtig designt ist:

1. **Agent wird selbstverteidigend** — lehnt unsinnige Fragen ab, BEVOR Skill lädt
2. **Portfolio Story wird zentral** — nicht optional, sondern Foundation
3. **Skills sind echte Modulation** — nicht "mache diesen Prompt", sondern "moduliere die Entscheidung unter dieser Strategie"
4. **Lineage wird aussagekräftig** — man sieht: "Story + ALLOCATION + Value-Skill = diese Analyse"
5. **User lernt die Struktur** — durch Wiederholung merken sie: "Erst Story, dann Frage, dann optional Stil"

---

## Offene Fragen

1. **Skill bei WITHDRAWAL?** Steuern-Optimierung als Skill? Oder lieber nicht (KISS)?
2. **ANALYSIS — welche Szenarios?** Stress-Test ist zu spezifisch. "Robustheit" ist vague. Was genau?
3. **Sprache**: Sollte Investment Kompass auf die App-Sprache reagieren (Deutsch/Englisch)?
4. **Fehler-Handling**: Was wenn Portfolio Story fehlt? (aktuell: null-safe, aber vielleicht sollte man early-stoppen?)

