"""
Repository for LLM token usage tracking.
"""

import sqlite3
from datetime import datetime, date
from typing import Optional

from core.constants import CLAUDE_HAIKU


class UsageRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        agent: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        skill: Optional[str] = None,
        source: str = "manual",
        duration_ms: Optional[int] = None,
        position_count: Optional[int] = None,
        cache_read_tokens: Optional[int] = None,
        cache_write_tokens: Optional[int] = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO llm_usage"
            " (agent, model, skill, source, input_tokens, output_tokens, duration_ms, position_count, cache_read_tokens, cache_write_tokens, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (agent, model, skill, source, input_tokens, output_tokens, duration_ms, position_count, cache_read_tokens, cache_write_tokens, datetime.utcnow().isoformat()),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(
        self,
        agent: Optional[str] = None,
        model: Optional[str] = None,
        skill: Optional[str] = None,
    ) -> None:
        """Insert a reset marker.  NULL = wildcard (applies to all)."""
        self._conn.execute(
            "INSERT INTO usage_resets (agent, model, skill, reset_at) VALUES (?, ?, ?, ?)",
            (agent, model, skill, datetime.utcnow().isoformat()),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Helpers: apply reset filter to a WHERE clause fragment
    # ------------------------------------------------------------------

    _RESET_FILTER = """
        NOT EXISTS (
            SELECT 1 FROM usage_resets r
            WHERE (r.agent IS NULL OR r.agent = lu.agent)
              AND (r.model IS NULL OR r.model = lu.model)
              AND (r.skill IS NULL OR r.skill = lu.skill)
              AND r.reset_at > lu.created_at
        )
    """

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def total_today(self) -> list[dict]:
        """Sum of input+output tokens per agent/skill/model/source for today (UTC)."""
        today = date.today().isoformat()
        rows = self._conn.execute(
            f"""SELECT agent, skill, model, source,
                      SUM(input_tokens) AS input_tokens,
                      SUM(output_tokens) AS output_tokens,
                      SUM(cache_read_tokens) AS cache_read_tokens,
                      SUM(cache_write_tokens) AS cache_write_tokens
               FROM llm_usage lu
               WHERE date(created_at) = ?
               GROUP BY agent, skill, model, source
               ORDER BY agent""",
            (today,),
        ).fetchall()
        return [dict(r) for r in rows]

    def total_all_time(self) -> list[dict]:
        """Sum of tokens per agent/skill/model/source since last reset."""
        rows = self._conn.execute(
            f"""SELECT agent, skill, model, source,
                      SUM(input_tokens) AS input_tokens,
                      SUM(output_tokens) AS output_tokens,
                      COUNT(*) AS calls,
                      AVG(duration_ms) AS avg_duration_ms
               FROM llm_usage lu
               WHERE {self._RESET_FILTER}
               GROUP BY agent, skill, model, source
               ORDER BY agent"""
        ).fetchall()
        return [dict(r) for r in rows]

    def daily_totals(self, limit: int = 30) -> list[dict]:
        """Aggregated tokens per day (last N days) — for a chart."""
        rows = self._conn.execute(
            f"""SELECT date(created_at) AS day,
                      SUM(input_tokens) AS input_tokens,
                      SUM(output_tokens) AS output_tokens
               FROM llm_usage lu
               WHERE {self._RESET_FILTER}
               GROUP BY day
               ORDER BY day DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def avg_cost_per_call(
        self,
        agent: str,
        model: str,
        skill: Optional[str],
        model_prices: dict,
    ) -> float:
        """
        Average cost per call for a specific agent/model/skill combination.
        model_prices: {"model_id": {"input": float, "output": float}} (per million tokens)
        Returns 0.0 if no data.
        """
        skill_filter = "AND skill = ?" if skill else "AND skill IS NULL"
        params: list = [agent, model]
        if skill:
            params.append(skill)
        rows = self._conn.execute(
            f"""SELECT AVG(input_tokens) AS avg_in, AVG(output_tokens) AS avg_out
               FROM llm_usage lu
               WHERE agent = ? AND model = ? {skill_filter}
                 AND {self._RESET_FILTER}""",
            params,
        ).fetchone()
        if not rows or rows["avg_in"] is None:
            return 0.0
        return _compute_cost(rows["avg_in"], rows["avg_out"], model, model_prices)

    def avg_cost_per_position(
        self,
        agent: str,
        model: str,
        skill: Optional[str],
        model_prices: dict,
    ) -> float:
        """
        Average cost PER POSITION for a specific agent/model/skill combination.

        Uses position_count from llm_usage table if available (real data).
        Falls back to avg_cost_per_call if position_count not recorded.

        Returns 0.0 if no data.
        """
        skill_filter = "AND skill = ?" if skill else "AND skill IS NULL"
        params: list = [agent, model]
        if skill:
            params.append(skill)

        # First try: get data from calls with position_count recorded
        rows_with_positions = self._conn.execute(
            f"""SELECT AVG(input_tokens) AS avg_in,
                       AVG(output_tokens) AS avg_out,
                       AVG(CAST(NULLIF(position_count, 0) AS FLOAT)) AS avg_positions
                FROM llm_usage lu
                WHERE agent = ? AND model = ? {skill_filter}
                  AND position_count IS NOT NULL
                  AND {self._RESET_FILTER}""",
            params,
        ).fetchone()

        if rows_with_positions and rows_with_positions["avg_positions"]:
            cost_per_call = _compute_cost(
                rows_with_positions["avg_in"],
                rows_with_positions["avg_out"],
                model,
                model_prices,
            )
            return cost_per_call / rows_with_positions["avg_positions"]

        # Fallback: use avg_cost_per_call if no position_count data exists
        return self.avg_cost_per_call(agent, model, skill, model_prices) / 20

    def monthly_estimate(
        self,
        scheduled_jobs: list,
        model_prices: dict,
        positions_repo=None,
    ) -> list[dict]:
        """
        Estimate monthly cost per scheduled job based on avg tokens per position.

        scheduled_jobs: list of ScheduledJob instances
        model_prices:   {"model_id": {"input": float, "output": float}}
        positions_repo: PositionsRepository for counting relevant positions per job

        Returns list of dicts with agent, skill_name, model, calls_per_month, avg_cost, monthly_cost.
        """
        _CALLS_PER_MONTH = {"daily": 30.0, "weekly": 4.33, "monthly": 1.0}
        result = []

        for job in scheduled_jobs:
            if not job.enabled:
                continue

            model = job.model or CLAUDE_HAIKU
            calls = _CALLS_PER_MONTH.get(job.frequency, 0.0)

            # Count relevant positions for this agent
            position_count = 1  # fallback: treat as single call if no repo
            if positions_repo:
                all_positions = positions_repo.get_portfolio()
                if job.agent_name == "storychecker":
                    position_count = len([p for p in all_positions if p.story])
                elif job.agent_name == "news_digest":
                    # Positions with ticker and news-eligible asset classes
                    position_count = len([
                        p for p in all_positions
                        if p.ticker and p.asset_class in {"Aktie", "Aktienfonds", "Kryptowährung"}
                    ])
                elif job.agent_name in {"consensus_gap", "fundamental"}:
                    position_count = len(all_positions)
                elif job.agent_name == "structural_scan":
                    position_count = len(all_positions)

            # Cost per position (not per call)
            cost_per_position = self.avg_cost_per_position(
                job.agent_name, model, job.skill_name, model_prices
            )

            # Monthly cost = calls × position_count × cost_per_position
            monthly_total = round(calls * position_count * cost_per_position, 6)

            result.append({
                "agent": job.agent_name,
                "skill_name": job.skill_name,
                "model": model,
                "calls_per_month": calls,
                "avg_cost_eur": round(cost_per_position * position_count, 6),
                "monthly_cost_eur": monthly_total,
            })
        return result

    def get_recent_calls(self, limit: int = 50) -> list[dict]:
        """Last N LLM calls (newest first), regardless of reset filters."""
        rows = self._conn.execute(
            """SELECT created_at, agent, skill, model, source, input_tokens, output_tokens, duration_ms
               FROM llm_usage
               ORDER BY created_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


# ------------------------------------------------------------------
# Cost helper (module-level, reusable)
# ------------------------------------------------------------------

def compute_cost(
    input_tokens: float,
    output_tokens: float,
    model: str,
    model_prices: dict,
    cache_read_tokens: Optional[float] = None,
    cache_write_tokens: Optional[float] = None,
) -> float:
    """Cost in EUR/USD (same unit as prices dict) for given token counts."""
    return _compute_cost(input_tokens, output_tokens, model, model_prices, cache_read_tokens, cache_write_tokens)


def _compute_cost(
    input_tokens: float,
    output_tokens: float,
    model: str,
    model_prices: dict,
    cache_read_tokens: Optional[float] = None,
    cache_write_tokens: Optional[float] = None,
) -> float:
    price = model_prices.get(model, {})
    input_price = price.get("input", 0.0)
    output_price = price.get("output", 0.0)

    if cache_read_tokens is None:
        cache_read_tokens = 0
    if cache_write_tokens is None:
        cache_write_tokens = 0

    # Input tokens = regular + cache_read + cache_write
    # Cache write tokens cost 1.25x, cache read tokens cost 0.10x, regular cost 1.0x
    regular_input = input_tokens - cache_read_tokens - cache_write_tokens
    cost = (
        regular_input * input_price +
        cache_write_tokens * input_price * 1.25 +
        cache_read_tokens * input_price * 0.10 +
        output_tokens * output_price
    ) / 1_000_000
    return cost
