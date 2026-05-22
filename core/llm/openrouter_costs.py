"""Fetch actual billed costs from OpenRouter API."""

import logging
from typing import Optional

import requests

_logger = logging.getLogger(__name__)
_TIMEOUT = 5


def fetch_generation_cost(api_key: str, base_url: str, generation_id: str) -> Optional[float]:
    """Return actual cost in USD for one OpenRouter generation, or None on error."""
    url = f"{base_url.rstrip('/')}/generation"
    try:
        resp = requests.get(
            url,
            params={"id": generation_id},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=_TIMEOUT,
        )
        if resp.status_code == 200:
            return resp.json().get("data", {}).get("total_cost")
    except Exception as exc:
        _logger.warning("OpenRouter cost fetch failed for %s: %s", generation_id, exc)
    return None


def fetch_account_usage(api_key: str, base_url: str) -> Optional[float]:
    """Return total cumulative account spend in USD from OpenRouter key info."""
    url = f"{base_url.rstrip('/')}/auth/key"
    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=_TIMEOUT,
        )
        if resp.status_code == 200:
            return resp.json().get("data", {}).get("usage")
    except Exception as exc:
        _logger.warning("OpenRouter account usage fetch failed: %s", exc)
    return None


def fetch_and_store_costs(api_key: str, base_url: str, records: list[dict], repo) -> int:
    """
    Fetch actual costs for a list of uncosted records and store them in the repo.
    Returns the number of successfully updated records.
    """
    updated = 0
    for rec in records:
        cost = fetch_generation_cost(api_key, base_url, rec["generation_id"])
        if cost is not None:
            repo.update_actual_cost(rec["id"], cost)
            updated += 1
    return updated
