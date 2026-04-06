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
    ) -> None:
        self._conn.execute(
            "INSERT INTO llm_usage"
            " (agent, model, skill, source, input_tokens, output_tokens, duration_ms, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (agent, model, skill, source, input_tokens, output_tokens, duration_ms, datetime.utcnow().isoformat()),
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
                      SUM(output_tokens) AS output_tokens
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

    def monthly_estimate(
        self,
        scheduled_jobs: list,
        model_prices: dict,
    ) -> list[dict]:
        """
        Estimate monthly cost per scheduled job based on avg tokens/call.

        scheduled_jobs: list of ScheduledJob instances
        model_prices:   {"model_id": {"input": float, "output": float}}

        Returns list of dicts with agent, skill_name, model, calls_per_month, avg_cost, monthly_cost.
        """
        _CALLS_PER_MONTH = {"daily": 30.0, "weekly": 4.33, "monthly": 1.0}
        result = []
        for job in scheduled_jobs:
            if not job.enabled:
                continue
            model = job.model or "claude-haiku-4-5-20251001"
            calls = _CALLS_PER_MONTH.get(job.frequency, 0.0)
            avg = self.avg_cost_per_call(job.agent_name, model, job.skill_name, model_prices)
            result.append({
                "agent": job.agent_name,
                "skill_name": job.skill_name,
                "model": model,
                "calls_per_month": calls,
                "avg_cost_eur": avg,
                "monthly_cost_eur": round(calls * avg, 6),
            })
        return result

    # ------------------------------------------------------------------
    # Benchmark runs
    # ------------------------------------------------------------------

    def record_benchmark(
        self,
        scenario_name: str,
        agent: str,
        model: str,
        skill_name: str,
        input_tokens: int,
        output_tokens: int,
        cost_eur: float,
        label: Optional[str] = None,
        duration_ms: Optional[int] = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO benchmark_runs"
            " (scenario_name, agent, model, skill_name, input_tokens, output_tokens, cost_eur, duration_ms, run_at, label)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                scenario_name,
                agent,
                model,
                skill_name,
                input_tokens,
                output_tokens,
                cost_eur,
                duration_ms,
                datetime.utcnow().isoformat(),
                label,
            ),
        )
        self._conn.commit()

    def get_benchmark_runs(self, scenario_name: Optional[str] = None) -> list[dict]:
        if scenario_name:
            rows = self._conn.execute(
                "SELECT * FROM benchmark_runs WHERE scenario_name = ? ORDER BY run_at DESC",
                (scenario_name,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM benchmark_runs ORDER BY run_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_benchmark_scenarios(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT scenario_name FROM benchmark_runs ORDER BY scenario_name"
        ).fetchall()
        return [r[0] for r in rows]


# ------------------------------------------------------------------
# Cost helper (module-level, reusable)
# ------------------------------------------------------------------

def compute_cost(
    input_tokens: float,
    output_tokens: float,
    model: str,
    model_prices: dict,
) -> float:
    """Cost in EUR/USD (same unit as prices dict) for given token counts."""
    return _compute_cost(input_tokens, output_tokens, model, model_prices)


def _compute_cost(
    input_tokens: float,
    output_tokens: float,
    model: str,
    model_prices: dict,
) -> float:
    price = model_prices.get(model, {})
    input_price = price.get("input", 0.0)
    output_price = price.get("output", 0.0)
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000
