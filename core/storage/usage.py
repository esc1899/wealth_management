"""
Repository for LLM token usage tracking.
"""

import sqlite3
from datetime import datetime, date
from typing import Optional



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
        web_search_requests: Optional[int] = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO llm_usage"
            " (agent, model, skill, source, input_tokens, output_tokens, duration_ms, position_count, cache_read_tokens, cache_write_tokens, web_search_requests, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (agent, model, skill, source, input_tokens, output_tokens, duration_ms, position_count, cache_read_tokens, cache_write_tokens, web_search_requests, datetime.utcnow().isoformat()),
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
                      SUM(cache_write_tokens) AS cache_write_tokens,
                      SUM(web_search_requests) AS web_search_requests,
                      COUNT(*) AS calls
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
                      AVG(duration_ms) AS avg_duration_ms,
                      SUM(cache_read_tokens) AS cache_read_tokens,
                      SUM(cache_write_tokens) AS cache_write_tokens,
                      SUM(web_search_requests) AS web_search_requests
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

    def monthly_totals_by_model(self) -> list[dict]:
        """Monthly totals grouped by month/agent/model/source — all time, cost-computable."""
        rows = self._conn.execute(
            f"""SELECT strftime('%Y-%m', created_at) AS month,
                      agent, model, source,
                      SUM(input_tokens) AS input_tokens,
                      SUM(output_tokens) AS output_tokens,
                      SUM(COALESCE(cache_read_tokens, 0)) AS cache_read_tokens,
                      SUM(COALESCE(cache_write_tokens, 0)) AS cache_write_tokens,
                      SUM(COALESCE(web_search_requests, 0)) AS web_search_requests,
                      COUNT(*) AS calls
               FROM llm_usage lu
               WHERE {self._RESET_FILTER}
               GROUP BY month, agent, model, source
               ORDER BY month ASC"""
        ).fetchall()
        return [dict(r) for r in rows]

    def daily_totals_by_model(self, days: int = 30) -> list[dict]:
        """Daily totals grouped by day/model/source for the last N days — cost-computable."""
        rows = self._conn.execute(
            f"""SELECT date(created_at) AS day,
                      model, source,
                      SUM(input_tokens) AS input_tokens,
                      SUM(output_tokens) AS output_tokens,
                      SUM(COALESCE(cache_read_tokens, 0)) AS cache_read_tokens,
                      SUM(COALESCE(cache_write_tokens, 0)) AS cache_write_tokens,
                      SUM(COALESCE(web_search_requests, 0)) AS web_search_requests,
                      COUNT(*) AS calls
               FROM llm_usage lu
               WHERE {self._RESET_FILTER}
                 AND date(created_at) >= date('now', ?)
               GROUP BY day, model, source
               ORDER BY day ASC""",
            (f"-{days} days",),
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
            f"""SELECT AVG(input_tokens) AS avg_in, AVG(output_tokens) AS avg_out, AVG(web_search_requests) AS avg_web_search
               FROM llm_usage lu
               WHERE agent = ? AND model = ? {skill_filter}
                 AND {self._RESET_FILTER}""",
            params,
        ).fetchone()
        if not rows or rows["avg_in"] is None:
            return 0.0
        avg_web_search = rows["avg_web_search"] or 0
        return _compute_cost(rows["avg_in"], rows["avg_out"], model, model_prices, web_search_requests=avg_web_search)

    def get_recent_calls(self, limit: int = 50) -> list[dict]:
        """Last N LLM calls (newest first), regardless of reset filters."""
        rows = self._conn.execute(
            """SELECT created_at, agent, skill, model, source, input_tokens, output_tokens, duration_ms, cache_read_tokens, cache_write_tokens, web_search_requests
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
    web_search_requests: Optional[float] = None,
) -> float:
    """Cost in EUR/USD (same unit as prices dict) for given token counts."""
    return _compute_cost(input_tokens, output_tokens, model, model_prices, cache_read_tokens, cache_write_tokens, web_search_requests)


def _compute_cost(
    input_tokens: float,
    output_tokens: float,
    model: str,
    model_prices: dict,
    cache_read_tokens: Optional[float] = None,
    cache_write_tokens: Optional[float] = None,
    web_search_requests: Optional[float] = None,
) -> float:
    price = model_prices.get(model, {})
    input_price = price.get("input", 0.0)
    output_price = price.get("output", 0.0)

    if cache_read_tokens is None:
        cache_read_tokens = 0
    if cache_write_tokens is None:
        cache_write_tokens = 0
    if web_search_requests is None:
        web_search_requests = 0

    # Anthropic returns input_tokens for regular (non-cached) tokens only.
    # cache_write_tokens (1.25x) and cache_read_tokens (0.10x) are billed separately.
    # Web search requests: $10 per 1000 requests = $0.01 per request
    cost = (
        input_tokens * input_price +
        cache_write_tokens * input_price * 1.25 +
        cache_read_tokens * input_price * 0.10 +
        output_tokens * output_price
    ) / 1_000_000
    cost += web_search_requests * 0.01
    return cost
