"""
Cost alert helper — compute today's and this month's API costs
and check them against configured limits.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from core.storage.usage import compute_cost


def get_period_costs(usage_repo, model_prices: dict) -> dict:
    """
    Return {'today': float, 'month': float} in USD.
    Uses all rows (no reset filter needed — alerts are absolute).
    """
    today_str = date.today().isoformat()
    month_str = today_str[:7]  # "YYYY-MM"

    rows = usage_repo._conn.execute(
        """SELECT model, input_tokens, output_tokens, date(created_at) AS day
           FROM llm_usage
           WHERE model NOT IN ('qwen3:8b', 'llama3.2')"""
    ).fetchall()

    cost_today = 0.0
    cost_month = 0.0
    for r in rows:
        cost = compute_cost(r["input_tokens"], r["output_tokens"], r["model"], model_prices)
        if r["day"] == today_str:
            cost_today += cost
        if r["day"].startswith(month_str):
            cost_month += cost

    return {"today": cost_today, "month": cost_month}


def check_alerts(costs: dict, limits: dict) -> list[dict]:
    """
    Returns list of triggered alerts: [{'period': 'daily'|'monthly', 'cost': float, 'limit': float}]
    """
    alerts = []
    if limits.get("daily", 0) > 0 and costs["today"] >= limits["daily"]:
        alerts.append({"period": "daily", "cost": costs["today"], "limit": limits["daily"]})
    if limits.get("monthly", 0) > 0 and costs["month"] >= limits["monthly"]:
        alerts.append({"period": "monthly", "cost": costs["month"], "limit": limits["monthly"]})
    return alerts
