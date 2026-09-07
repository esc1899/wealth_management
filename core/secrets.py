"""Secret lookup: environment first, macOS keychain second.

Why this exists
---------------
Credentials used to live in plaintext in ``.env``.  They now live in the login
keychain, one generic-password item per secret, named with a ``wm-`` prefix.

Two rules shape this module, and both are deliberate:

1. **Environment wins over keychain.**  ``os.getenv`` is consulted first and its
   answer is returned even when it is the empty string.  Tests, CI, a shell
   ``export`` and a future container therefore keep working unchanged — anything
   that can set an environment variable never touches the keychain at all.
   An explicit ``FOO=`` in the environment means "deliberately empty", not
   "fall through"; ``APP_PASSWORD=`` disabling the login gate must stay
   expressible.

2. **Reads go through /usr/bin/security, not a Python library.**  macOS grants
   keychain access per item to the *application that created it*.  These items
   are created with ``security add-generic-password``, so ``security`` is the
   trusted reader.  A different binary — a ``keyring``-backed Python process —
   is an unknown application to the ACL and triggers an interactive "allow
   access?" dialog.  That is fatal for scheduled and unattended runs, which have
   no one to click it.

Creating an item (the ``-w`` goes last, with no value, so the secret is typed at
a prompt instead of landing in shell history and the process list)::

    security add-generic-password -U -a "$USER" -s wm-ENCRYPTION_KEY -w

Missing item, no macOS, no ``security`` binary: this returns ``None``.  It never
raises.  Deciding whether a missing secret is fatal belongs to the caller —
``Config.validate()`` already does that for the required ones.
"""

from __future__ import annotations

import getpass
import os
import subprocess
from typing import Callable, Optional

# Shared machine, shared keychain: neighbouring projects use their own prefixes
# (hoa-, curator-).  Do not widen this to a bare name.
SERVICE_PREFIX = "wm-"

_SECURITY_BIN = "/usr/bin/security"

# A keychain read is a fork+exec of a small binary; it answers in milliseconds.
# The timeout only exists so a wedged keychain (locked, prompting, corrupt)
# cannot hang app startup forever.
_TIMEOUT_SECONDS = 10

#: Secrets kept in the keychain.  Configuration — hosts, model names, URLs, the
#: Langfuse *public* key, paths, feature flags — deliberately stays in ``.env``.
KEYCHAIN_SECRETS = (
    "LLM_API_KEY",
    "OPENAI_API_KEY",
    "TAVILY_API_KEY",
    "LANGFUSE_SECRET_KEY",
    "APP_PASSWORD",
    "MCP_BEARER_TOKEN",
    "ENCRYPTION_KEY",
)

#: Signature of an injectable runner.  Takes the argv list, returns something
#: with ``returncode`` and ``stdout`` — i.e. a ``subprocess.CompletedProcess``.
Runner = Callable[[list], "subprocess.CompletedProcess"]

# Populated only for lookups that used the default runner, so an injected runner
# in a test can never poison the cache a later test reads.
_cache: dict = {}


def _default_runner(argv: list) -> "subprocess.CompletedProcess":
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        # No shell: argv goes to execve untouched, so a service name can never
        # be reinterpreted as shell syntax.
        shell=False,
    )


def service_name(name: str) -> str:
    """``ENCRYPTION_KEY`` -> ``wm-ENCRYPTION_KEY``."""
    return f"{SERVICE_PREFIX}{name}"


def _account() -> str:
    # Matches the ``-a "$USER"`` used at creation time.
    return os.getenv("USER") or getpass.getuser()


def keychain_get(name: str, runner: Optional[Runner] = None) -> Optional[str]:
    """Read one secret from the login keychain.  ``None`` if absent.

    Never raises: a missing item, a missing ``security`` binary (any non-macOS
    host, including the dev container), a locked keychain or a timeout all
    return ``None``.
    """
    use_default = runner is None
    if use_default and name in _cache:
        return _cache[name]

    run = runner or _default_runner
    argv = [_SECURITY_BIN, "find-generic-password", "-a", _account(), "-s", service_name(name), "-w"]

    try:
        proc = run(argv)
    except (OSError, subprocess.SubprocessError):
        # OSError covers FileNotFoundError — no /usr/bin/security, i.e. not macOS.
        # SubprocessError covers TimeoutExpired.
        value = None
    else:
        # 44 is "item not found"; treat every non-zero the same way.
        if proc.returncode != 0:
            value = None
        else:
            # ``-w`` prints the password followed by a newline.  Strip only that
            # newline — a secret could legitimately end in a space, and Fernet
            # keys end in '='.
            value = (proc.stdout or "").rstrip("\n")
            if not value:
                value = None

    if use_default:
        _cache[name] = value
    return value


def get_secret(
    name: str,
    default: Optional[str] = None,
    runner: Optional[Runner] = None,
) -> Optional[str]:
    """Environment first, then keychain, then ``default``.

    See the module docstring for why the order is this way and why an
    environment value of ``""`` is honoured rather than skipped.
    """
    env_value = os.getenv(name)
    if env_value is not None:
        return env_value

    found = keychain_get(name, runner=runner)
    if found is not None:
        return found

    return default


def reset_cache() -> None:
    """Drop memoised keychain answers.  For tests, and after rotating a secret
    in a long-running process."""
    _cache.clear()
