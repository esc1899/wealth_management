"""Letzte Läufe: welcher Job wann mit welchem Modell was gekostet hat (Statistik, 17.10.2026).

Die Summen je Monat und je Agent sagen, *wofür* Geld ausgegeben wurde, nicht *wann* und durch
welchen Lauf. Erik sah die Kosten des Jobs ``kurse`` nur im Maschinenraum und wusste nicht, dass
er ein Sprachmodell ruft. Mit Blick auf Lotsee muss die App das selbst zeigen, ohne das Haus.

Ein Lauf ist, was ``llm_usage.lauf`` zusammenhält: die run_id eines ops-core-Jobs oder die
batch_id eines Batches. Aufrufe aus der App haben keinen Lauf; sie werden je Tag und Agent zu
einer Zeile "von Hand" zusammengefasst. Aufrufe von vor dem 17.10.2026 haben ebenfalls keinen
und stehen darum je Tag, Agent und Weg da, ohne Job. Gerechnet wird mit der Kostenfunktion der
Seite (Listenpreis); ein Modell ohne Preis zählt als "offen", nie als 0.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Iterable, Optional

from core.modell_meldung import AGENTEN

#: Wie ein Mensch die Agenten liest; was hier fehlt, steht mit seinem Schlüssel da.
NAMEN = {**dict(AGENTEN), "news_digest": "News-Digest", "search_agent": "Investment-Suche",
         "fundamental": "Fundamentalwert", "skill_generator": "Skill-Generator"}

#: So heißen die Wege in der Spalte "Wie".
JOB, BATCH, HAND = "job", "batch", "hand"


def _zeit(created_at: str) -> datetime:
    t = datetime.fromisoformat(created_at)
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).astimezone()


def _wie(quelle: Optional[str]) -> str:
    return BATCH if quelle == "batch" else HAND if quelle in (None, "manual") else JOB


def _schluessel(r: dict, wann: datetime) -> tuple:
    if r.get("lauf"):
        return ("lauf", r["lauf"])
    return ("ohne", r.get("agent"), _wie(r.get("source")), wann.date())


def laeufe(aufrufe: Iterable[dict], kosten: Callable[[dict], Optional[float]],
           limit: int = 50) -> list[dict]:
    """Je Lauf eine Zeile, neueste zuerst.

    ``kosten(aufruf)`` gibt den Betrag eines Aufrufs oder ``None``, wenn sein Modell keinen
    Preis hat. Jede Zeile: ``wann`` (erster Aufruf, Ortszeit), ``job`` (ops-core, sonst None),
    ``wie`` (job, batch, hand), ``agenten`` und ``modelle`` (in der Reihenfolge des ersten
    Aufrufs), ``aufrufe``, ``kosten`` (ohne die offenen) und ``offen`` (Aufrufe ohne Preis)."""
    gruppen: dict[tuple, dict] = {}
    for r in aufrufe:
        wann = _zeit(r["created_at"])
        g = gruppen.setdefault(_schluessel(r, wann), {
            "wann": wann, "job": r.get("job"), "quellen": set(),
            "agenten": {}, "modelle": {}, "aufrufe": 0, "kosten": 0.0, "offen": 0})
        g["wann"] = min(g["wann"], wann)
        g["quellen"].add(r.get("source"))
        g["agenten"].setdefault(NAMEN.get(r.get("agent"), r.get("agent") or "?"), None)
        g["modelle"].setdefault(r.get("model") or "?", None)
        g["aufrufe"] += 1
        betrag = kosten(r)
        if betrag is None:
            g["offen"] += 1
        else:
            g["kosten"] += betrag
    aus = []
    for g in gruppen.values():
        wie = {_wie(q) for q in g["quellen"]}
        wie = wie.pop() if len(wie) == 1 else JOB
        if wie == HAND or g["job"] == "interaktiv":
            wie, g["job"] = HAND, None
        aus.append({"wann": g["wann"], "job": g["job"], "wie": wie,
                    "agenten": list(g["agenten"]), "modelle": list(g["modelle"]),
                    "aufrufe": g["aufrufe"], "kosten": g["kosten"], "offen": g["offen"]})
    aus.sort(key=lambda z: z["wann"], reverse=True)
    return aus[:limit]
