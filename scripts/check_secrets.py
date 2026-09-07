#!/usr/bin/env python
"""Zeigt, woher jedes Geheimnis aktuell kommt — ohne je einen Wert auszugeben.

Der Umzug in den Schlüsselbund wirkt erst, wenn die Zeile aus der .env
verschwunden ist: solange sie dort steht, gewinnt die Umgebung (so gebaut, damit
Tests, CI und ein Container unverändert laufen).  Dieses Skript macht genau das
sichtbar — es unterscheidet "kommt noch aus der .env" von "kommt wirklich aus dem
Schlüsselbund".

    python scripts/check_secrets.py

Ausgegeben werden nur Herkunft und Länge, nie der Wert selbst.  Das Skript ist
damit gefahrlos in einem geteilten Terminal oder in einem Screenshot.
"""

import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from core.secrets import KEYCHAIN_SECRETS, keychain_get, service_name  # noqa: E402

ENV_FILE = _PROJECT_ROOT / ".env"

# Zusätzlich geprüft: ein echter Zugang, der auf der Umzugsliste fehlte.
ALSO_CHECK = ("DEEPSEEK_API_KEY",)


def names_in_env_file() -> set:
    """Welche Namen stehen noch in der .env? Nur Namen, keine Werte."""
    if not ENV_FILE.exists():
        return set()
    found = set()
    for line in ENV_FILE.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, _ = line.partition("=")
        found.add(name.strip().removeprefix("export "))
    return found


def main() -> int:
    in_env_file = names_in_env_file()

    # Die .env ist beim Import von config bereits geladen; hier nur der Rohzustand
    # der Prozessumgebung vor load_dotenv wäre irreführend, deshalb bewusst nach
    # dem Laden geprüft.
    from dotenv import load_dotenv

    load_dotenv(ENV_FILE)

    rows = []
    for name in list(KEYCHAIN_SECRETS) + list(ALSO_CHECK):
        env_value = os.getenv(name)
        still_in_env_file = name in in_env_file
        kc_value = keychain_get(name)

        if env_value is not None and still_in_env_file:
            source = "· .env (Umzug offen)"
            state = "!"
        elif env_value is not None:
            source = "· Umgebung"
            state = "·"
        elif kc_value is not None:
            source = "✓ Schlüsselbund"
            state = "✓"
        else:
            source = "× nirgends"
            state = "×"

        effective = env_value if env_value is not None else kc_value
        length = f"{len(effective)} Z." if effective else "leer"
        has_kc = "ja" if kc_value is not None else "—"
        rows.append((state, name, source, length, has_kc))

    width = max(len(r[1]) for r in rows)
    print(f"\n{'':2} {'Variable':<{width}}  {'Wirksame Quelle':<22} {'Länge':<8} {'wm-Eintrag da?'}")
    print("─" * (width + 56))
    for state, name, source, length, has_kc in rows:
        print(f"{state:2} {name:<{width}}  {source:<22} {length:<8} {has_kc}")

    open_moves = [r[1] for r in rows if r[0] == "!"]
    missing = [r[1] for r in rows if r[0] == "×"]

    print()
    if open_moves:
        print("! Noch aus der .env bedient — der Schlüsselbund wird hier nicht benutzt:")
        for n in open_moves:
            print(f"    {n}   (Eintrag: {service_name(n)})")
        print("  → Zeile aus der .env löschen, dann App neu starten.")
    if missing:
        print("× Weder in .env/Umgebung noch im Schlüsselbund:")
        for n in missing:
            print(f"    {n}")
    if not open_moves and not missing:
        print("✓ Alle Geheimnisse kommen aus dem Schlüsselbund oder der Umgebung.")

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
