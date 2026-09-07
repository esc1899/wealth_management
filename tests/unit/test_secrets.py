"""Tests for core.secrets — environment-first lookup with macOS keychain fallback.

Every test injects a fake runner; none of them shells out to /usr/bin/security.
The conftest guard enforces that even if one forgets.
"""

import subprocess

import pytest

from core import secrets


class _FakeProc:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


def _runner(returncode=0, stdout="", record=None):
    def run(argv):
        if record is not None:
            record.append(argv)
        return _FakeProc(returncode, stdout)

    return run


@pytest.fixture(autouse=True)
def _clear_cache():
    secrets.reset_cache()
    yield
    secrets.reset_cache()


class TestPrecedence:
    def test_environment_wins_over_keychain(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "from-env")
        calls = []
        got = secrets.get_secret("LLM_API_KEY", runner=_runner(0, "from-keychain\n", calls))
        assert got == "from-env"
        assert calls == [], "keychain must not be consulted when the env var is set"

    def test_empty_environment_value_is_honoured_not_skipped(self, monkeypatch):
        # APP_PASSWORD= means "login gate deliberately off". Falling through to
        # the keychain here would silently re-enable it.
        monkeypatch.setenv("APP_PASSWORD", "")
        calls = []
        got = secrets.get_secret("APP_PASSWORD", runner=_runner(0, "hunter2\n", calls))
        assert got == ""
        assert calls == []

    def test_keychain_used_when_env_absent(self, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        got = secrets.get_secret("TAVILY_API_KEY", runner=_runner(0, "tvly-abc\n"))
        assert got == "tvly-abc"

    def test_default_when_neither_source_has_it(self, monkeypatch):
        monkeypatch.delenv("NOPE", raising=False)
        assert secrets.get_secret("NOPE", "fallback", runner=_runner(44, "")) == "fallback"

    def test_default_is_none_when_unspecified(self, monkeypatch):
        monkeypatch.delenv("NOPE", raising=False)
        assert secrets.get_secret("NOPE", runner=_runner(44, "")) is None


class TestServiceNaming:
    def test_wm_prefix(self):
        assert secrets.service_name("ENCRYPTION_KEY") == "wm-ENCRYPTION_KEY"

    def test_lookup_queries_prefixed_service_and_uses_security_binary(self, monkeypatch):
        monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
        monkeypatch.setenv("USER", "erik")
        calls = []
        secrets.get_secret("ENCRYPTION_KEY", runner=_runner(0, "k\n", calls))

        argv = calls[0]
        assert argv[0] == "/usr/bin/security"
        assert argv[1] == "find-generic-password"
        assert "wm-ENCRYPTION_KEY" in argv
        # The account must match the `-a "$USER"` used at creation time.
        assert argv[argv.index("-a") + 1] == "erik"
        # -w last, so the password is printed rather than prompted for.
        assert argv[-1] == "-w"

    def test_no_neighbouring_project_prefix(self):
        # The keychain is shared with other projects on this machine.
        assert secrets.SERVICE_PREFIX == "wm-"
        for name in secrets.KEYCHAIN_SECRETS:
            svc = secrets.service_name(name)
            assert not svc.startswith("hoa-")
            assert not svc.startswith("curator-")


class TestFailureModes:
    """A missing secret returns None. Nothing here may raise — the caller decides."""

    def test_item_not_found_returns_none(self, monkeypatch):
        monkeypatch.delenv("MISSING", raising=False)
        assert secrets.get_secret("MISSING", runner=_runner(44, "")) is None

    def test_security_binary_absent_returns_none(self, monkeypatch):
        # The dev container is Linux: there is no /usr/bin/security at all.
        monkeypatch.delenv("MISSING", raising=False)

        def boom(argv):
            raise FileNotFoundError(2, "No such file or directory", "/usr/bin/security")

        assert secrets.get_secret("MISSING", runner=boom) is None

    def test_timeout_returns_none(self, monkeypatch):
        # A locked keychain can block on an interactive prompt.
        monkeypatch.delenv("MISSING", raising=False)

        def boom(argv):
            raise subprocess.TimeoutExpired(cmd="security", timeout=10)

        assert secrets.get_secret("MISSING", runner=boom) is None

    def test_empty_keychain_output_is_none_not_empty_string(self, monkeypatch):
        monkeypatch.delenv("MISSING", raising=False)
        assert secrets.get_secret("MISSING", "dflt", runner=_runner(0, "\n")) == "dflt"


class TestValueHandling:
    def test_trailing_newline_stripped(self, monkeypatch):
        monkeypatch.delenv("K", raising=False)
        assert secrets.get_secret("K", runner=_runner(0, "abc123\n")) == "abc123"

    def test_fernet_style_padding_preserved(self, monkeypatch):
        # Fernet keys are urlsafe-base64 and routinely end in '='. A careless
        # .strip() of '=' or whitespace would corrupt the key and make the
        # database undecryptable.
        monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
        key = "dGhpcy1pcy1hLTMyLWJ5dGUtdGVzdC1rZXktb2s="
        assert secrets.get_secret("ENCRYPTION_KEY", runner=_runner(0, key + "\n")) == key


class TestCaching:
    def test_default_runner_result_is_cached(self, monkeypatch):
        monkeypatch.delenv("K", raising=False)
        calls = []
        monkeypatch.setattr(secrets, "_default_runner", _runner(0, "v\n", calls))
        assert secrets.get_secret("K") == "v"
        assert secrets.get_secret("K") == "v"
        assert len(calls) == 1

    def test_injected_runner_does_not_populate_cache(self, monkeypatch):
        # Otherwise one test's fake value would leak into the next test.
        monkeypatch.delenv("K", raising=False)
        secrets.get_secret("K", runner=_runner(0, "injected\n"))
        assert "K" not in secrets._cache

    def test_reset_cache_forces_reread(self, monkeypatch):
        monkeypatch.delenv("K", raising=False)
        calls = []
        monkeypatch.setattr(secrets, "_default_runner", _runner(0, "v\n", calls))
        secrets.get_secret("K")
        secrets.reset_cache()
        secrets.get_secret("K")
        assert len(calls) == 2


class TestConftestGuard:
    def test_real_security_binary_is_unreachable_from_the_suite(self):
        """conftest replaces the runner, so no test can shell out to security."""
        proc = secrets._default_runner(["/usr/bin/security", "find-generic-password"])
        # A real call would either succeed (0) or report not-found (44) *after*
        # executing the binary. The sealed runner returns 44 without executing.
        assert proc.returncode == 44
        assert proc.stdout == ""
        assert secrets._default_runner.__name__ == "_sealed_runner"

    def test_keychain_looks_empty_under_the_guard(self, monkeypatch):
        monkeypatch.delenv("ANY_SECRET", raising=False)
        assert secrets.get_secret("ANY_SECRET") is None


class TestMigrationScope:
    def test_all_seven_credentials_are_covered(self):
        assert set(secrets.KEYCHAIN_SECRETS) == {
            "LLM_API_KEY",
            "OPENAI_API_KEY",
            "TAVILY_API_KEY",
            "LANGFUSE_SECRET_KEY",
            "APP_PASSWORD",
            "MCP_BEARER_TOKEN",
            "ENCRYPTION_KEY",
        }

    def test_configuration_is_not_treated_as_secret(self):
        # Hosts, model names, paths and flags stay in .env — including the
        # Langfuse *public* key, which is public by definition.
        for name in (
            "LLM_BASE_URL",
            "LLM_DEFAULT_MODEL",
            "OPENAI_BASE_URL",
            "OPENAI_MODELS",
            "LANGFUSE_PUBLIC_KEY",
            "LANGFUSE_HOST",
            "OLLAMA_HOST",
            "OLLAMA_MODEL",
            "DB_PATH",
            "DEMO_MODE",
            "SHOW_LEGAL_NOTICE",
            "BACKUP_REPO_PATH",
            "RESTIC_PASSWORD_FILE",
        ):
            assert name not in secrets.KEYCHAIN_SECRETS
