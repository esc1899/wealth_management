import pytest
import os

import core.secrets as _secrets

# ---------------------------------------------------------------------------
# Keychain guard — installed at import time, on purpose.
#
# config.py resolves its secrets in the class body, i.e. the moment it is first
# imported, which happens during pytest *collection* — before any fixture, even
# an autouse session-scoped one, has had a chance to run.  A fixture-based guard
# would therefore be installed too late to stop the first lookup.  Assigning the
# module attribute here runs while conftest itself is imported, which pytest does
# before collecting anything.
#
# core.secrets.keychain_get() resolves `_default_runner` at call time, so
# replacing the attribute is enough.
# ---------------------------------------------------------------------------


class _ItemNotFound:
    """What `security find-generic-password` returns for a missing item."""

    returncode = 44
    stdout = ""


def _sealed_runner(argv):
    """Stand in for /usr/bin/security without ever executing it.

    Modelling an *empty* keychain rather than raising is deliberate.  Tests that
    want to assert "no Tavily key is configured" do so by unsetting the
    environment variable; with the keychain fallback in place, that only means
    what they intend if the keychain is also empty.  A clean machine — a fresh
    checkout, CI, the Linux dev container — is exactly that, so this is the
    honest model, and it keeps those tests testing the real invariant ("no key
    from any source") instead of an accident of lookup order.

    The seal is the point: the real binary is unreachable from the suite, so no
    test can be slow, machine-dependent, or blocked on a keychain unlock dialog.
    """
    return _ItemNotFound()


_secrets._default_runner = _sealed_runner
_secrets.reset_cache()

# Set test environment variables before any imports.
#
# Deliberately NOT extended to the other keychain-backed secrets.  config.py
# calls load_dotenv(), which does not override variables that are already set,
# so a setdefault("OPENAI_API_KEY", "") here would shadow the developer's .env
# and silently change what the suite sees.  The sealed runner above is what
# keeps the keychain out of reach; pinning env values is not needed for that.
os.environ.setdefault("LLM_API_KEY", "test_key")
os.environ.setdefault("ENCRYPTION_KEY", "test_encryption_key_32bytes_long!!")
os.environ.setdefault("DB_PATH", ":memory:")

# Hart gesetzt, nicht setdefault: Entwicklungs-Sitzungen laufen mit
# DEMO_MODE=true, damit ad-hoc ausgeführter Code data/portfolio.db gar nicht
# erst öffnet.  Für die Testsuite wäre das falsch — config.DB_PATH ignoriert
# DB_PATH, sobald DEMO_MODE gesetzt ist (config.py:69), und die Tests landeten
# dann auf data/demo.db statt auf :memory:.  Die Suite bestimmt ihre Datenbank
# selbst; portfolio.db erreicht sie so oder so nie.
os.environ["DEMO_MODE"] = "false"
