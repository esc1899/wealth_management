"""
Story Checker Agent — validates investment theses against established strategies.

Cloud-only (ClaudeProvider). Watchlist positions only — no portfolio quantities
or purchase prices are passed to the API.

One-shot analysis: no sessions, no persistent history. Call analyze() directly.
"""

from __future__ import annotations

from core.llm.claude import ClaudeProvider
from core.storage.models import Position

# ------------------------------------------------------------------
# Strategy definitions
# ------------------------------------------------------------------

STRATEGIES: dict[str, str] = {
    "Value Investing": (
        "Graham/Buffett: Kaufe nur zu einem Preis deutlich unter dem inneren Wert "
        "(Sicherheitsmarge). Verlässliche Gewinne, starke Bilanz, niedriges KGV/KBV, "
        "stabile freie Cash Flows, robuste Geschäftsmodelle."
    ),
    "Growth": (
        "Fokus auf überdurchschnittliches Umsatz- und Gewinnwachstum (>15 % p.a.). "
        "Großer adressierbarer Markt (TAM), starkes Produkt, Skalierbarkeit, "
        "Netzwerkeffekte, disruptives Potenzial."
    ),
    "Dividende": (
        "Regelmäßige, steigende Dividendenausschüttung (Dividend Aristocrats). "
        "Payout Ratio < 75 %, solide freie Cashflows, niedrige Verschuldung, "
        "stabile Branche, langfristig verlässliche Ausschüttungen."
    ),
    "Momentum": (
        "Starke relative Kursstärke gegenüber dem Markt (RS-Rating > 80, nahe 52-Wochen-Hoch). "
        "Positiver Preistrend, Volumenbestätigung, kaum belastende Katalysatoren am Horizont, "
        "breite institutionelle Nachfrage."
    ),
    "GARP": (
        "Growth at a Reasonable Price: solides Wachstum kombiniert mit vernünftiger Bewertung. "
        "PEG-Ratio < 1,5, KGV relativ zum Wachstum attraktiv, keine Überbewertung trotz "
        "Wachstumsgeschichte."
    ),
    "ESG": (
        "Umwelt- (E), Sozial- (S) und Governance- (G) Kriterien erfüllt. "
        "Hohes Nachhaltigkeitsrating (z.B. MSCI ESG A/AA), keine Ausschlusskriterien "
        "(Waffen, Tabak, Kohle, Glücksspiel), transparente Berichterstattung, "
        "ambitionierte Klimaziele."
    ),
}

# ------------------------------------------------------------------
# System prompt
# ------------------------------------------------------------------

BASE_SYSTEM_PROMPT = """Du bist ein kritischer Investment-Analyst der Investment-Thesen prüft.

Du erhältst eine Watchlist-Position (Name, Ticker, Asset-Klasse, ggf. aktuelle Empfehlung \
und die hinterlegte Investment-These) sowie eine gewählte Anlage-Strategie. \
Deine Aufgabe: prüfe ob die These konsistent mit der Strategie ist.

Antworte IMMER in exakt diesem Format (Markdown):

## Bewertung: {NAME} ({TICKER})

**Strategie:** {STRATEGIE} · **Urteil:** {AMPEL}

> {EIN-SATZ-FAZIT}

### Stärken
- ...

### Risiken & Red Flags
- ...

### Strategie-Konsistenz
{2–3 Sätze: Passt die These zur Strategie? Warum / warum nicht? Konkrete Bezüge zur Strategie-Definition.}

### Fazit
{1–2 Sätze abschließendes Urteil mit konkreter Begründung.}

---

Ampel-Regeln (genau eines wählen):
- 🟢 **Passt** — These ist konsistent mit der Strategie, keine wesentlichen Widersprüche
- 🟡 **Bedingt** — Teilweise passend, aber wichtige Aspekte fehlen oder widersprechen der Strategie
- 🔴 **Passt nicht** — These widerspricht der Strategie fundamental oder enthält schwere Red Flags

Sei kritisch und präzise. Keine unverbindlichen Relativierungen. Antworte ausschließlich auf Deutsch. \
Maximal 400 Wörter."""


# ------------------------------------------------------------------
# Agent
# ------------------------------------------------------------------


class StorycheckerAgent:
    """
    Stateless cloud agent that checks an investment thesis against a strategy.
    No DB sessions — results live in Streamlit session_state.
    """

    def __init__(self, llm: ClaudeProvider) -> None:
        self._llm = llm

    async def analyze(self, position: Position, strategy: str) -> str:
        """Analyze position story against strategy. Returns formatted markdown."""
        strategy_desc = STRATEGIES.get(strategy, strategy)
        user_msg = _build_user_message(position, strategy, strategy_desc)
        response = await self._llm.chat_with_tools(
            messages=[{"role": "user", "content": user_msg}],
            tools=[],
            system=BASE_SYSTEM_PROMPT,
            max_tokens=1024,
        )
        return response.content


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _build_user_message(position: Position, strategy: str, strategy_desc: str) -> str:
    ticker_str = f" ({position.ticker})" if position.ticker else ""
    lines = [
        f"## Position: {position.name}{ticker_str}",
        f"**Asset-Klasse:** {position.asset_class}",
    ]
    if position.empfehlung:
        lines.append(f"**Aktuelle Empfehlung:** {position.empfehlung}")
    if position.story:
        lines.append(f"\n**Investment-These:**\n{position.story}")
    else:
        lines.append("\n**Investment-These:** (keine Story hinterlegt — prüfe bitte anhand des Namens und der Asset-Klasse)")

    lines.append(f"\n---\n**Zu prüfende Strategie:** {strategy}")
    lines.append(f"**Strategie-Beschreibung:** {strategy_desc}")
    lines.append("\nBitte erstelle jetzt deine Bewertung im vorgegebenen Format.")

    return "\n".join(lines)
