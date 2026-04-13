# Investment Kompass — Skill/Strategy Matrix

## Konzept: Strategie ist Usecase-abhängig

Die **gleiche Strategie** hat in jedem Usecase eine **andere Ausführungsform**:

- **ALLOCATION**: Wie investiere ich nach dieser Strategie?
- **REBALANCING**: Wie rebalanciere ich zu dieser Strategie hin?
- **WITHDRAWAL**: Wie fahre ich diese Strategie zurück?
- **ANALYSIS**: Wie robust ist diese Strategie aktuell?

---

## Die 6 Strategien × 4 Use Cases = 24 Kombinationen

### 1. FARMER-STRATEGIE (Einkommen-fokussiert)

**Leitgedanke**: "Ich lebe von den Erträgen, nicht von Kapitalverkäufen"

| Usecase | Ausführung | Konkrete Aktion |
|---------|-----------|-----------------|
| **ALLOCATION** | "Welche Positionen generieren regelmäßige Erträge?" | Dividenden-Aktien, Renten, REITs, Geldmarkt priorisieren |
| **REBALANCING** | "Schneide schwach verdienende Positionen zurück, stärke die Ertragshebel" | Verkaufe wachstumsstarke aber ertragsschwache Positionen; erhöhe Dividenden-Anteil |
| **WITHDRAWAL** | "Entnehme zuerst die laufenden Erträge, dann minimal vom Kapitalstock" | 1. Dividenden + Zinserträge abheben; 2. Notfalls die ertragsschwächsten Positionen (Sparen) verkaufen |
| **ANALYSIS** | "Wie stabil sind meine Erträge? Reichen sie für meinen Bedarf?" | "Du hast 8% Rendite/Jahr, brauchst 5% zum Leben — 3% Puffer" |

**Farmer-Skill-Prompt**:
```
Strategie: FARMER (Einkommen-fokussiert)
Leitgedanke: Leben von Erträgen, nicht von Kapitalverkäufen.
Priorisiere bei Entscheidungen:
1. Laufende Erträge (Dividenden, Zinsen) — diese werden für Lebenshaltung verwendet
2. Stabilität der Erträge — Schwankungen sind problematisch
3. Kapitalwachstum ist sekundär

[Usecase-spezifisch ausfüllen]
```

---

### 2. VALUE-STRATEGIE (Vermögen-fokussiert, unterbewertete Chancen)

**Leitgedanke**: "Ich kaufe mit Abschlag, warte auf Wiederherstellung"

| Usecase | Ausführung | Konkrete Aktion |
|---------|-----------|-----------------|
| **ALLOCATION** | "Suche unterbewertete Positionen relativ zu Fundamentals" | Tiefere KGV, höhere Eigenkapitalquote, "Schnäppchen" im Portfolio |
| **REBALANCING** | "Verkaufe übergewichtete, teure Positionen; kaufe unterbewertete" | "Tech-Position zu teuer → Verkaufen; Commodities unterbewichtet+günstig → Kaufen" |
| **WITHDRAWAL** | "Verkaufe die teuersten, übergewerteten Positionen zuerst" | "Welche Position hat die beste KGV-Bewertung? Verkauf wenn noch fair, nicht wenn fallend" |
| **ANALYSIS** | "Wie viel Wertsteigerungs-Potenzial habe ich?" | "Portfolio ist 15% unterbewertet vs. Fundamentals — gutes Aufwärtspotenzial" |

**Value-Skill-Prompt**:
```
Strategie: VALUE (Unterbewertungs-fokussiert)
Leitgedanke: Gute Unternehmen zu günstigen Preisen kaufen, auf Wiederherstellung warten.
Beachte bei Entscheidungen:
1. Bewertung relativ zu Fundamentals (KGV, Dividend Yield, Eigenkapitalquote)
2. "Margin of Safety" — wie viel Abschlag ist noch vorhanden?
3. Qualität — auch günstig ist teuer, wenn Unternehmen schlecht ist

[Usecase-spezifisch ausfüllen]
```

---

### 3. GROWTH-STRATEGIE (Wachstum-fokussiert)

**Leitgedanke**: "Kapitalwachstum über Erträge — für langfristige Ziele"

| Usecase | Ausführung | Konkrete Aktion |
|---------|-----------|-----------------|
| **ALLOCATION** | "Welche Positionen haben Wachstumspotenzial?" | Tech, Biotech, EM-Growth, Wachstums-Renten |
| **REBALANCING** | "Erhöhe Wachstumspositionen wenn untergewichtet, reduziere Reife-Positionen" | "Tech ist nur 20%, sollte 35% sein (pro Story) → Kaufen" |
| **WITHDRAWAL** | "Verkaufe reife Positionen ohne Wachstum zuerst, behalte Wachstumshebel" | "Utility-Stocks (stabil aber flach) verkaufen; Tech behalten" |
| **ANALYSIS** | "Wie viel annualisiertes Wachstum kann ich erwarten?" | "Portfolio mit 60% Growth sollte 8-10% CAGR bringen" |

**Growth-Skill-Prompt**:
```
Strategie: GROWTH (Kapitalwachstum)
Leitgedanke: Vermögen aufbauen für langfristige Ziele, nicht für Einkommen heute.
Beachte bei Entscheidungen:
1. Annualisiertes Wachstum (CAGR) — nicht aktuelle Rendite
2. "Runway" — wie lange bis ich die Zielgröße erreiche?
3. Volatilität ist OK, wenn Zeithorizont lang genug

[Usecase-spezifisch ausfüllen]
```

---

### 4. BALANCE-STRATEGIE (ausgewogen, konfliktfreie Mittellösung)

**Leitgedanke**: "Mischung aus Ertrag und Wachstum, je nach Lebenssituation"

| Usecase | Ausführung | Konkrete Aktion |
|---------|-----------|-----------------|
| **ALLOCATION** | "Mische Einkommen und Wachstum gemäß Story-Profil" | 50% Einkommen / 30% Wachstum / 20% Rohstoffe+Defensive |
| **REBALANCING** | "Halte Verhältnis, aber nutze Gelegenheiten um Über/Untergewichte zu glätten" | "Tech zu teuer (Gewinn nehmen), Renten zu billig (kaufen)" |
| **WITHDRAWAL** | "Verkaufe proportional aus allen Kategorien, nicht selektiv" | "10k abheben? → 5k Einkommen, 3k Wachstum, 2k Rohstoffe" |
| **ANALYSIS** | "Bin ich noch im Balance-Ziel oder bin ich abgedriftet?" | "War 60/40, bin jetzt 65/35 — zu growth-lastig" |

**Balance-Skill-Prompt**:
```
Strategie: BALANCE (ausgewogene Mischung)
Leitgedanke: Flexibilität zwischen Ertrag und Wachstum, je nach Situation.
Beachte bei Entscheidungen:
1. Zielallokation (gemäß Portfolio Story)
2. Aktuelle Abweichungen — sind sie gewollt oder Drift?
3. Neugewichtung wenn zu weit weg vom Ziel (>5-10% Abweichung)

[Usecase-spezifisch ausfüllen]
```

---

### 5. CRISIS-RESILIENCE-STRATEGIE (defensiv, krisenfest)

**Leitgedanke**: "Ich will schlafen können, auch in schwierigen Zeiten"

| Usecase | Ausführung | Konkrete Aktion |
|---------|-----------|-----------------|
| **ALLOCATION** | "Addiere Puffer: Liquidität, Renten, defensive Sektoren" | 30% Cash/Geldmarkt, 40% Investment-Grade Renten, 20% Utility/Defensive Aktien, 10% Rohstoffe |
| **REBALANCING** | "Verkaufe riskante Positionen, erhöhe Liquiditäts-Reserve" | "High-Yield Bonds → weg; Staatsanleihen rauf" |
| **WITHDRAWAL** | "Entnehme aus Liquiditäts-Reserve und Renten zuerst, nicht aus Aktien" | "Brauche 10k? → 5k aus Geldmarkt, 5k aus Renten-Portion, KEINE Aktien!" |
| **ANALYSIS** | "Wie lange halte ich durch in einer 30%-Baisse?" | "Mit 30% Liquidität + 6 Monate Einkommen halten — OK" |

**Crisis-Resilience-Skill-Prompt**:
```
Strategie: CRISIS-RESILIENCE (defensiv)
Leitgedanke: In jeder Krise sicher schlafen können. Geld für 6-12 Monate verfügbar.
Beachte bei Entscheidungen:
1. Liquiditäts-Puffer (6-12 Monate Lebenshaltung)
2. "Duration" der Renten — nicht zu lang (weniger Zinsrisiko)
3. Diversifikation — keine Klasse >40% (auch Renten!)

[Usecase-spezifisch ausfüllen]
```

---

### 6. TAX-OPTIMIZED-STRATEGIE (Steuer-fokussiert)

**Leitgedanke**: "Maximale nach-Steuer-Rendite" (für Deutschland relevant)

| Usecase | Ausführung | Konkrete Aktion |
|---------|-----------|-----------------|
| **ALLOCATION** | "Einkommen in Steuer-geschützten Wrappers (Pensionsvermögen), Growth im Depot" | Renten im Riester/Rente; Wachstums-Aktien im normalen Depot (für Kursverlust-Offset) |
| **REBALANCING** | "Rebalanciere durch Zukäufe, nicht durch Verkäufe (um Gewinne zu realisieren)" | "Statt Gewinner zu verkaufen → kaufe die Verlierer" |
| **WITHDRAWAL** | "Realisiere Verluste zuerst, Gewinne später (oder gar nicht)" | "Position mit -20% vs. +30%? Verkauf die -20%, nicht die +30%" |
| **ANALYSIS** | "Was ist meine effektive Rendite nach Steuern und Gebühren?" | "Brutto 8%, Steuern 1%, Gebühren 0.5% → Netto 6.5%" |

**Tax-Optimized-Skill-Prompt**:
```
Strategie: TAX-OPTIMIZED (Steueroptimiert)
Leitgedanke: Nach-Steuer-Rendite ist was zählt. Realisiere Verluste, halte Gewinne.
Beachte bei Entscheidungen:
1. Realisierter Gewinn = Steuer — vermeide wenn möglich
2. Verlust-Harvesting — realisiere Verluste um Gewinne zu offsetten
3. "Wash Sale" Regeln — nicht sofort wiederankaufen
4. Timing — Januar für Verluste, Dezember für Gewinne?

[Usecase-spezifisch ausfüllen]
```

---

## Die Matrix (Einfache Übersicht)

```
                  ALLOCATION           REBALANCING          WITHDRAWAL           ANALYSIS
FARMER            Ertrag kaufen        Ertrag erhöhen       Ertrag abheben       Stabilität Check
VALUE             Günstig kaufen       Rebalance + günstig  Teuer verkaufen       Potenzial
GROWTH            Wachstum kaufen      Growth erhöhen       Alte verkaufen        CAGR-Ziel
BALANCE           Mix kaufen           Ziel halten          Proportional          Drift checken
CRISIS            Puffer aufbauen      Liquidität erhöhen   Reserve nutzen        Durchhaltbarkeit
TAX-OPTIMIZED     Struktur optimieren  Über Zukauf          Verlust realisieren   Netto-Rendite

```

---

## Implementation (Technisch)

### Skills-DB Schema:

```python
class Skill:
    name: str                    # "Farmer", "Value", "Growth", ...
    area: str                    # "rebalance" (alle 4 Use Cases)
    usecase_mapping: Dict[str, str]  # { 
                                      #   "ALLOCATION": "Prompt für Farmer + Allocation",
                                      #   "WITHDRAWAL": "Prompt für Farmer + Withdrawal",
                                      #   ...
                                      # }
    prompt: str                  # Fallback (generic)
    created_at: datetime
```

### In Investment Kompass:

```python
async def analyze(self, user_query, skill_name, usecase):
    skill = get_skill(skill_name)
    
    # Use-case-specific prompt if available
    skill_prompt = skill.usecase_mapping.get(usecase, skill.prompt)
    
    # Combine with system prompt for that usecase
    full_prompt = (
        USECASE_PROMPTS[usecase]
        + "\n\n## Strategie: " + skill.name
        + "\n" + skill_prompt
    )
```

---

## Open Questions

1. **TAX-OPTIMIZED**: Nur für Deutschland? Oder generisch "minimize fees"?
2. **Andere Strategien?** "ESG-focused"? "Momentum"? "Dividend Aristocrats"?
3. **Skill-Mixing**: Darf der User mehrere Skills kombinieren? Oder nur eins?
   - Beispiel: "FARMER + TAX-OPTIMIZED" (Einkommen + Steuer-Effizient)?

