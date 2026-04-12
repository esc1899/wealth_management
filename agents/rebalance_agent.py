"""
Rebalance Agent — portfolio rebalancing analysis using local Ollama LLM.
Private 🔒 — all portfolio data stays local, nothing is sent to external APIs.

Flow per start_session() call:
  1. Load all portfolio positions from DB
  2. Fetch current market prices from DB
  3. Build a structured portfolio snapshot (stored in DB for follow-up context)
  4. Send to local LLM with the selected skill strategy + optional user context
  5. Persist user + assistant messages and return the session

Flow per chat() call:
  1. Load session (for portfolio snapshot + skill) and message history from DB
  2. Send full conversation to LLM
  3. Persist and return the assistant reply
"""

from __future__ import annotations
import logging


from datetime import date
from typing import Optional, Tuple

from core.asset_class_config import get_asset_class_registry
from core.currency import symbol
from core.llm.base import Message, Role
from core.llm.local import OllamaProvider
from core.storage.analyses import PositionAnalysesRepository
from core.storage.market_data import MarketDataRepository
from core.storage.models import Position, RebalanceSession
from core.storage.positions import PositionsRepository
from core.storage.rebalance import RebalanceRepository
from core.storage.skills import SkillsRepository


logger = logging.getLogger(__name__)
# ------------------------------------------------------------------
# Asset class categorization for Josef's Regel + handelbar split
# ------------------------------------------------------------------

# These asset classes are not tradeable via exchanges — excluded from
# active rebalancing recommendations but still counted in total wealth.
_NON_TRADEABLE_CLASSES = {"Festgeld", "Bargeld", "Immobilie", "Grundstück"}

# Josef's Regel: target 1/3 per category (Rohstoffe + Immobilien together = 1/3).
# Maps investment_type → Josef category
# Note: "Immobilien" investment_type maps to "Rohstoffe" category so they combine
JOSEF_CATEGORY = {
    "Wertpapiere": "Aktien",
    "Edelmetalle": "Rohstoffe",
    "Renten": "Renten/Geld",
    "Geld": "Renten/Geld",
    "Immobilien": "Rohstoffe",  # Combined with Edelmetalle, not separate
}

# Legacy name for backwards compatibility
_JOSEF_CATEGORY = JOSEF_CATEGORY


def compute_josef_allocation(valuations: list) -> dict[str, float]:
    """
    Compute Josef-Regel allocation percentages from portfolio valuations.

    Args:
        valuations: List of PortfolioValuation objects with investment_type and current_value_eur

    Returns:
        Dict with keys "Aktien", "Renten/Geld", "Rohstoffe" and percentage values
    """
    totals = {"Aktien": 0.0, "Renten/Geld": 0.0, "Rohstoffe": 0.0}
    grand_total = 0.0

    for v in valuations:
        value = v.current_value_eur or 0.0
        if value <= 0:
            continue
        category = JOSEF_CATEGORY.get(v.investment_type)
        if category:
            totals[category] += value
            grand_total += value

    if grand_total == 0:
        return {"Aktien": 0.0, "Renten/Geld": 0.0, "Rohstoffe": 0.0}

    return {k: (v / grand_total * 100) for k, v in totals.items()}

# ------------------------------------------------------------------
# System prompt
# ------------------------------------------------------------------

SYSTEM_PROMPT = """You are a portfolio management advisor.
You will receive a snapshot of the user's portfolio with current positions, market values, and portfolio weights.
Your task is to analyze the portfolio according to the provided strategy and give concrete, actionable rebalancing recommendations.

Rules:
- Recommendations only — you cannot execute trades
- Be cost-aware: only recommend actions where the benefit clearly outweighs transaction costs
- Flag drift if a position's weight has moved significantly from a balanced allocation
- Be specific: mention approximate EUR amounts and percentages where useful
- Keep the output structured and scannable
- Positions marked [AUSGESCHLOSSEN] are excluded from rebalancing — assess them but make no buy/sell recommendation
- Non-tradeable positions (cash, fixed-term deposits, real estate) cannot be rebalanced — include their value in the overall picture only
- **Crypto positions [HOCHSPEKULATIV — Krypto]**: Always recommend selling these immediately — crypto carries unmanageable volatility and does not fit into disciplined portfolio construction
- Today's date is {today}"""


class RebalanceAgent:
    """
    Conversational agent: start_session() triggers the initial analysis,
    chat() handles follow-up questions. Uses local Ollama LLM (private 🔒).
    """

    def __init__(
        self,
        positions_repo: PositionsRepository,
        market_repo: MarketDataRepository,
        analyses_repo: PositionAnalysesRepository,
        llm: OllamaProvider,
        skills_repo: Optional[SkillsRepository] = None,
    ):
        self._positions = positions_repo
        self._market = market_repo
        self._analyses = analyses_repo
        self._llm = llm
        self._skills_repo = skills_repo

    @property
    def model(self) -> str:
        return self._llm.model

    async def start_session(
        self,
        skill_name: str,
        skill_prompt: str,
        user_context: str,
        repo: RebalanceRepository,
    ) -> Tuple[RebalanceSession, str]:
        """
        Build portfolio snapshot, create a session in DB, run initial analysis.

        Args:
            skill_name:   Display name of the strategy
            skill_prompt: The strategy prompt
            user_context: Optional user input ("Ich möchte €2.000 investieren")
            repo:         RebalanceRepository for persistence

        Returns:
            (session, assistant_reply)
        """
        portfolio = self._positions.get_portfolio()
        watchlist = self._positions.get_watchlist()
        if not portfolio:
            snapshot = "Portfolio is empty."
        else:
            snapshot = self._build_portfolio_context(portfolio, watchlist)

        session = repo.create_session(
            skill_name=skill_name,
            skill_prompt=skill_prompt,
            portfolio_snapshot=snapshot,
        )

        user_message = user_context.strip() if user_context.strip() else (
            "Please analyze my portfolio and provide rebalancing recommendations according to the strategy."
        )
        repo.add_message(session.id, "user", user_message)

        self._llm.skill_context = skill_name
        system = (
            SYSTEM_PROMPT.format(today=date.today().isoformat())
            + f"\n\n## Strategy: {skill_name}\n{skill_prompt}"
        )
        # Inject hidden rebalance system skills (e.g. Josef's Regel)
        if self._skills_repo:
            for s in self._skills_repo.get_system_skills(area="rebalance"):
                system += f"\n\n{s.prompt}"
        system += f"\n\n## Portfolio\n{snapshot}"

        messages = [
            Message(role=Role.SYSTEM, content=system),
            Message(role=Role.USER, content=user_message),
        ]
        reply = await self._llm.chat(messages, max_tokens=2048)

        repo.add_message(session.id, "assistant", reply)
        return session, reply

    async def chat(
        self,
        session_id: int,
        user_message: str,
        repo: RebalanceRepository,
    ) -> str:
        """
        Send a follow-up message in an existing session.

        Args:
            session_id:   ID of the rebalance session
            user_message: The user's follow-up question
            repo:         RebalanceRepository for persistence

        Returns:
            Assistant reply string
        """
        session = repo.get_session(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")

        repo.add_message(session_id, "user", user_message)

        system = (
            SYSTEM_PROMPT.format(today=date.today().isoformat())
            + f"\n\n## Strategy: {session.skill_name}\n{session.skill_prompt}"
        )
        if self._skills_repo:
            for s in self._skills_repo.get_system_skills(area="rebalance"):
                system += f"\n\n{s.prompt}"
        system += f"\n\n## Portfolio\n{session.portfolio_snapshot}"

        history = repo.get_messages(session_id)
        messages = [Message(role=Role.SYSTEM, content=system)] + [
            Message(
                role=Role.USER if m.role == "user" else Role.ASSISTANT,
                content=m.content,
            )
            for m in history
        ]

        reply = await self._llm.chat(messages, max_tokens=2048)
        repo.add_message(session_id, "assistant", reply)
        return reply

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    _TROY_OZ_TO_G = 31.1035  # grams per troy ounce

    def _get_position_value(self, pos: Position) -> Optional[float]:
        """Determine EUR value of a position from market data or extra_data."""
        if pos.ticker:
            price_record = self._market.get_price(pos.ticker)
            if price_record is not None and pos.quantity is not None:
                # Precious metals stored in grams: price_eur is per Troy Oz
                if pos.unit == "g":
                    return (price_record.price_eur / self._TROY_OZ_TO_G) * pos.quantity
                return pos.quantity * price_record.price_eur
        # Bargeld: quantity IS the amount in EUR (unit="€")
        if pos.asset_class == "Bargeld" and pos.quantity is not None:
            return pos.quantity
        # Manual valuation types: use estimated_value from extra_data
        if pos.extra_data:
            est = pos.extra_data.get("estimated_value")
            if est is not None:
                return float(est)
        # Fallback to purchase_price only for manual-valuation classes (auto_fetch=false).
        # For auto-fetch classes (stocks, ETFs, crypto) a missing market price means
        # the data simply hasn't been fetched yet — purchase_price is in an unknown
        # currency and would produce a wrong EUR value.
        registry = get_asset_class_registry()
        cfg = registry.get(pos.asset_class)
        if cfg and not cfg.auto_fetch and pos.purchase_price is not None:
            if pos.quantity is not None:
                return pos.quantity * pos.purchase_price
            return pos.purchase_price
        return None

    def _build_portfolio_context(
        self,
        positions: list[Position],
        watchlist: list[Position],
    ) -> str:
        """Format portfolio + watchlist as structured LLM context.

        Sections:
          1. Tradeable portfolio (active rebalancing candidates)
          2. Non-tradeable wealth (for context only)
          3. Josef's Regel — actual vs. 1/3 target per category
          4. Buy candidates (watchlist positions with story)

        Note: Positions that are both in_portfolio and in_watchlist are included
        in the portfolio analysis (since get_portfolio() returns them), but this
        is a data consistency issue — ideally, each position should be either
        portfolio OR watchlist, not both.
        """
        # Filter out pure watchlist positions (in_watchlist=True but in_portfolio=False)
        # to ensure watchlist-only entries don't get counted in portfolio totals.
        # Portfolio positions can have in_watchlist=True, but that's a data anomaly
        # we tolerate here; the real fix is at the data layer.
        watchlist_ids = {w.id for w in watchlist if w.id and not w.in_portfolio}

        # Use only positions that are actually in the portfolio
        portfolio_positions = [p for p in positions if p.in_portfolio]

        all_ids = [p.id for p in portfolio_positions if p.id]

        verdicts    = self._analyses.get_latest_bulk(all_ids, "storychecker")
        fund_v      = self._analyses.get_latest_bulk(all_ids, "fundamental")
        gap_v       = self._analyses.get_latest_bulk(all_ids, "consensus_gap")
        fund_v_wl   = self._analyses.get_latest_bulk([w.id for w in watchlist if w.id], "fundamental")
        gap_v_wl    = self._analyses.get_latest_bulk([w.id for w in watchlist if w.id], "consensus_gap")
        story_v_wl  = self._analyses.get_latest_bulk([w.id for w in watchlist if w.id], "storychecker")

        # Separate tradeable vs non-tradeable
        tradeable: list[Position] = []
        non_tradeable: list[Position] = []
        for pos in portfolio_positions:
            if pos.asset_class in _NON_TRADEABLE_CLASSES:
                non_tradeable.append(pos)
            else:
                tradeable.append(pos)

        # Calculate values
        tradeable_values: dict[int, Optional[float]] = {
            p.id: self._get_position_value(p) for p in tradeable if p.id
        }
        non_tradeable_values: dict[int, Optional[float]] = {
            p.id: self._get_position_value(p) for p in non_tradeable if p.id
        }

        tradeable_total = sum(v for v in tradeable_values.values() if v is not None)
        grand_total = tradeable_total + sum(
            v for v in non_tradeable_values.values() if v is not None
        )

        lines = [f"**Portfolio snapshot — {date.today().isoformat()}**\n"]

        # ── Section 1: Tradeable portfolio ────────────────────────────
        lines.append("### Handelbares Portfolio (für Rebalancing verfügbar)")
        has_tradeable_data = False
        for pos in tradeable:
            value = tradeable_values.get(pos.id) if pos.id else None
            weight = (
                f"{value / tradeable_total * 100:.1f}%"
                if value and tradeable_total > 0
                else "n/a"
            )
            purchase = f"{symbol()}{pos.purchase_price:.2f}" if pos.purchase_price else "unknown"

            price_record = self._market.get_price(pos.ticker) if pos.ticker else None
            current_str = f"{symbol()}{price_record.price_eur:.2f}" if price_record else "no price"
            value_str = f"{symbol()}{value:,.0f}" if value is not None else "n/a"

            if pos.quantity is not None:
                qty = pos.quantity
                qty_str = (
                    f"{int(qty):,}" if qty == int(qty)
                    else f"{qty:,.4f}".rstrip("0").rstrip(".")
                )
            else:
                qty_str = "?"

            analysis = verdicts.get(pos.id) if pos.id else None
            verdict_str = ""
            if analysis and analysis.verdict:
                _icons = {"intact": "🟢", "gemischt": "🟡", "gefaehrdet": "🔴"}
                icon = _icons.get(analysis.verdict, "")
                verdict_str = f" | thesis: {icon} {analysis.verdict}"
                if analysis.summary:
                    verdict_str += f" — {analysis.summary}"

            fund = fund_v.get(pos.id) if pos.id else None
            if fund and fund.verdict:
                _ficons = {"unterbewertet": "🟢", "fair": "🟡", "überbewertet": "🔴", "unbekannt": "⚪"}
                verdict_str += f" | fundamental: {_ficons.get(fund.verdict, '⚪')} {fund.verdict}"
                if fund.summary:
                    verdict_str += f" — {fund.summary}"

            gap = gap_v.get(pos.id) if pos.id else None
            if gap and gap.verdict:
                _gicons = {"wächst": "🟢", "stabil": "🟡", "schließt": "🟡", "eingeholt": "🔴"}
                verdict_str += f" | gap: {_gicons.get(gap.verdict, '')} {gap.verdict}"
                if gap.summary:
                    verdict_str += f" — {gap.summary}"

            excluded_tag = " **[AUSGESCHLOSSEN]**" if pos.rebalance_excluded else ""
            crypto_tag = " ⚠️ **[HOCHSPEKULATIV — Krypto]**" if pos.asset_class == "Kryptowährung" else ""
            lines.append(
                f"- {excluded_tag}**{pos.ticker or pos.name}** ({pos.name}){crypto_tag}: "
                f"{qty_str} {pos.unit} × {current_str} = {value_str} "
                f"({weight} of tradeable) | "
                f"purchase: {purchase} | class: {pos.asset_class}"
                f"{verdict_str}"
            )
            has_tradeable_data = True

        if not has_tradeable_data:
            lines.append("*(keine handelbaren Positionen)*")
        if tradeable_total > 0:
            lines.append(f"\n**Handelbares Vermögen gesamt: {symbol()}{tradeable_total:,.0f}**")

        # ── Section 2: Non-tradeable wealth ───────────────────────────
        lines.append("\n### Nicht-handelbares Vermögen (kein Rebalancing möglich)")
        non_tradeable_total = 0.0
        for pos in non_tradeable:
            value = non_tradeable_values.get(pos.id) if pos.id else None
            value_str = f"{symbol()}{value:,.0f}" if value is not None else "kein Wert"
            if value:
                non_tradeable_total += value

            extra: list[str] = []
            if pos.extra_data:
                if pos.extra_data.get("bank"):
                    extra.append(f"Bank: {pos.extra_data['bank']}")
                if pos.extra_data.get("maturity_date"):
                    extra.append(f"Fälligkeit: {pos.extra_data['maturity_date']}")
                if pos.extra_data.get("interest_rate"):
                    extra.append(f"Zins: {pos.extra_data['interest_rate']}%")
            detail = f" ({', '.join(extra)})" if extra else ""
            lines.append(
                f"- **{pos.name}** [{pos.asset_class}]: {value_str}{detail}"
            )

        if not non_tradeable:
            lines.append("*(keine nicht-handelbaren Positionen)*")
        if non_tradeable_total > 0:
            lines.append(
                f"\n**Nicht-handelbares Vermögen gesamt: {symbol()}{non_tradeable_total:,.0f}**"
            )
        if grand_total > 0:
            lines.append(f"**Gesamtvermögen: {symbol()}{grand_total:,.0f}**")

        # ── Section 3: Josef's Regel breakdown ────────────────────────
        # Aktien: 1/3, Renten/Geld: 1/3, Rohstoffe (Edelmetalle + Immobilien): 1/3
        lines.append("\n### Josef's Regel — Ist-Verteilung vs. Ziel (je 1/3 = 33,3%)")
        josef_totals: dict[str, float] = {"Aktien": 0.0, "Renten/Geld": 0.0, "Rohstoffe": 0.0}
        # Use portfolio_positions (not original 'positions') to avoid double-counting watchlist positions
        for pos in portfolio_positions:
            value = (
                tradeable_values.get(pos.id)
                if pos.id in tradeable_values
                else non_tradeable_values.get(pos.id)
            ) if pos.id else None
            if value is None:
                continue
            category = _JOSEF_CATEGORY.get(pos.investment_type)
            if category:
                josef_totals[category] += value

        if grand_total > 0:
            lines.append(
                f"| Kategorie              | Wert         | Ist    | Ziel  | Abweichung |"
            )
            lines.append(
                f"|------------------------|--------------|--------|-------|------------|"
            )
            # Individual categories (Aktien, Renten/Geld each get 1/3)
            for cat in ["Aktien", "Renten/Geld"]:
                total = josef_totals.get(cat, 0.0)
                pct = total / grand_total * 100
                delta = pct - 33.33
                delta_str = f"+{delta:.1f}%" if delta >= 0 else f"{delta:.1f}%"
                lines.append(
                    f"| {cat:<22} | {symbol()}{total:>10,.0f} | {pct:>5.1f}% | 33.3% | {delta_str:>10} |"
                )
            # Rohstoffe + Immobilien combined (together = 1/3)
            # (Immobilien is already mapped to "Rohstoffe" category)
            raw = josef_totals.get("Rohstoffe", 0.0)
            pct = raw / grand_total * 100
            delta = pct - 33.33
            delta_str = f"+{delta:.1f}%" if delta >= 0 else f"{delta:.1f}%"
            lines.append(
                f"| Rohstoffe + Immobilien | {symbol()}{raw:>10,.0f} | {pct:>5.1f}% | 33.3% | {delta_str:>10} |"
            )
        else:
            lines.append("*(kein Vermögen mit Wertangabe — Kursdaten oder Schätzwerte fehlen)*")

        # ── Section 4: Watchlist buy candidates ───────────────────────
        # Only show watchlist positions that are NOT already in the portfolio section
        portfolio_ids = {p.id for p in portfolio_positions if p.id}
        candidates = [
            w for w in watchlist
            if w.id not in portfolio_ids and w.story
        ]
        if candidates:
            lines.append("\n### Kaufkandidaten (Watchlist mit Investment-These)")
            for w in candidates:
                skill_tag = f" [{w.story_skill}]" if w.story_skill else ""
                story_preview = (w.story[:120] + "…") if len(w.story or "") > 120 else (w.story or "")
                cloud_signals: list[str] = []
                ws = story_v_wl.get(w.id) if w.id else None
                if ws and ws.verdict:
                    _sicons = {"intact": "🟢", "gemischt": "🟡", "gefaehrdet": "🔴"}
                    cloud_signals.append(f"thesis: {_sicons.get(ws.verdict, '⚪')} {ws.verdict}")
                    if ws.summary:
                        cloud_signals[-1] += f" — {ws.summary}"
                wf = fund_v_wl.get(w.id) if w.id else None
                if wf and wf.verdict:
                    _ficons = {"unterbewertet": "🟢", "fair": "🟡", "überbewertet": "🔴", "unbekannt": "⚪"}
                    cloud_signals.append(f"fundamental: {_ficons.get(wf.verdict, '⚪')} {wf.verdict}")
                wg = gap_v_wl.get(w.id) if w.id else None
                if wg and wg.verdict:
                    _gicons = {"wächst": "🟢", "stabil": "🟡", "schließt": "🟡", "eingeholt": "🔴"}
                    cloud_signals.append(f"gap: {_gicons.get(wg.verdict, '')} {wg.verdict}")
                signal_str = f" | {' | '.join(cloud_signals)}" if cloud_signals else ""
                lines.append(
                    f"- **{w.ticker or w.name}** ({w.name}){skill_tag} "
                    f"[{w.asset_class}]{signal_str} — These: {story_preview}"
                )

        return "\n".join(lines)
