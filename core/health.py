"""Setup health checks — static configuration and dynamic connectivity checks."""

from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse


class Severity(str, Enum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class HealthCheck:
    key: str
    severity: Severity
    detail: str = ""


_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def is_local_url(url: str) -> bool:
    """Return True if the URL points to localhost / 127.0.0.1 / ::1."""
    try:
        return urlparse(url).hostname in _LOCAL_HOSTS
    except Exception:
        return True


def run_static_checks(config) -> list[HealthCheck]:
    """Return health checks based on configuration only (no network I/O)."""
    checks: list[HealthCheck] = []

    # Private agents use Ollama — if it's remote, portfolio data leaves the machine
    if not is_local_url(config.OLLAMA_HOST):
        checks.append(HealthCheck("ollama_remote", Severity.ERROR, config.OLLAMA_HOST))

    # Langfuse traces contain prompts with portfolio data
    langfuse_enabled = bool(config.LANGFUSE_SECRET_KEY and config.LANGFUSE_PUBLIC_KEY)
    if langfuse_enabled and not is_local_url(config.LANGFUSE_HOST):
        checks.append(HealthCheck("langfuse_cloud", Severity.WARNING, config.LANGFUSE_HOST))

    # Corporate proxy: all Claude requests are routed through a third party
    if config.ANTHROPIC_BASE_URL:
        checks.append(HealthCheck("anthropic_proxy", Severity.WARNING, config.ANTHROPIC_BASE_URL))

    # Demo mode: data is stored in the demo DB and can be reset at any time
    if config.DEMO_MODE:
        checks.append(HealthCheck("demo_mode", Severity.WARNING))

    return checks


def check_ollama_connectivity(host: str) -> HealthCheck:
    """Try to reach Ollama. Returns an OK or ERROR HealthCheck."""
    import requests  # local import — only used when called
    try:
        url = f"{host.rstrip('/')}/api/tags"
        resp = requests.get(url, timeout=3)
        if resp.status_code == 200:
            return HealthCheck("ollama_ok", Severity.OK, host)
        return HealthCheck("ollama_unreachable", Severity.ERROR, host)
    except Exception:
        return HealthCheck("ollama_unreachable", Severity.ERROR, host)
