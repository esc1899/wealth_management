"""Ein neueres Claude-Modell als Meldung auf der Startseite des Mac mini (29.09.2026).

Die Cloud-Agenten tragen ihr Modell einzeln (Einstellungen, "Modellauswahl"). Erscheint
ein neueres derselben Familie, markierte bisher nur die Auswahl das alte als "nicht mehr
aktuell" — sichtbar erst, wenn man dort hinschaut. Jetzt legt der Kachel-Job einen Hinweis
auf die Kachel, wie der Maschinenraum für den Haus-Standard: "Neueres Claude-Modell:
Sonnet 5.5 — Sonnet 5 noch bei Story Checker, News-Digest", mit Link auf die Einstellungen.

Gefragt wird die Einstellung, nicht das Run-Log: Die App bucht ihre Aufrufe nicht dort,
und was ein Agent beim nächsten Lauf nimmt, sagt die Einstellung. Ein Agent auf ``home``
folgt dem Haus — den meldet der Maschinenraum, hier nicht ein zweites Mal. Kein x: Die
Meldung ist ein Zustand und verschwindet mit dem nächsten Kachel-Lauf nach dem Umstellen.
"""

from __future__ import annotations

import re
from typing import Callable, Optional

#: Die Cloud-Agenten der Einstellungsseite, Schlüssel und Name wie dort.
AGENTEN = (
    ("news", "News-Digest"), ("search", "Investment-Suche"),
    ("storychecker", "Story Checker"), ("structural_scan", "Strukturwandel-Scanner"),
    ("consensus_gap", "Konsens-Lücken"), ("fundamental_analyzer", "Fundamentalwert"),
    ("capital_allocator", "Capital Allocator"), ("sector_rotation", "Sektor Rotation"),
    ("devils_advocate", "Devil's Advocate"),
)

_FAMILIE = re.compile(r"^Claude (\w+) (\d+)(?:\.(\d+))?$")
_DATUM = re.compile(r"-\d{8}$")


def agenten_modelle(get: Callable[[str], Optional[str]], standard: str = "") -> dict[str, str]:
    """Je Agent das Modell, das er beim nächsten Lauf nimmt — dieselbe Reihenfolge wie
    ``state_llm._get_public_agent_model``, ohne Streamlit."""
    aus = {}
    for key, name in AGENTEN:
        modell = (get(f"model_public_{key}") or get(f"model_openai_{key}")
                  or get(f"model_claude_{key}") or standard)
        if modell:
            aus[name] = modell.strip()
    return aus


def _version(name: Optional[str]):
    m = _FAMILIE.match((name or "").strip())
    return (m.group(1), (int(m.group(2)), int(m.group(3) or 0))) if m else None


def _name(modell: str, namen: dict[str, str]) -> Optional[str]:
    if modell in namen:
        return namen[modell]
    basis = _DATUM.sub("", modell)
    return next((n for m, n in namen.items() if _DATUM.sub("", m) == basis), None)


def modell_meldung(modelle: dict[str, str], katalog: dict) -> Optional[dict]:
    """Die Meldung im Schema der Startseite — oder None.

    `modelle`: je Agent sein Modell (``agenten_modelle``); `katalog`: ``load_catalog``.
    Ein Modell ohne Namen im Katalog oder aus einer Familie ohne aktuelles Modell bleibt
    stumm — ein Hinweis braucht ein Ziel."""
    namen = katalog.get("names") or {}
    neueste: dict[str, tuple] = {}
    for m in katalog.get("current") or []:
        if (v := _version(namen.get(m))) and (v[0] not in neueste or v[1] > neueste[v[0]][0]):
            neueste[v[0]] = (v[1], namen[m])
    wer: dict[str, list[str]] = {}
    ziel: dict[str, str] = {}
    for agent, modell in modelle.items():
        if not modell.startswith("claude-"):
            continue
        name = _name(modell, namen)
        v = _version(name)
        if not v or v[0] not in neueste or neueste[v[0]][0] <= v[1]:
            continue
        wer.setdefault(name, []).append(agent)
        ziel[name] = neueste[v[0]][1]
    if not wer:
        return None
    kurz = lambda n: n.removeprefix("Claude ")  # noqa: E731
    ziele = list(dict.fromkeys(kurz(ziel[n]) for n in wer))
    return {"text": ("Neueres Claude-Modell: " if len(ziele) == 1
                     else "Neuere Claude-Modelle: ") + ", ".join(ziele),
            "zusatz": "; ".join(f"{kurz(n)} noch bei {', '.join(a)}" for n, a in wer.items()),
            "zustand": "hinweis", "lauf": "Modellkatalog",
            "von": (katalog.get("stand") or "")[:10] or None, "ziel": "settings"}
