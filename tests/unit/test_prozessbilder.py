"""Die Prozessbilder unter `deploy/n8n/ablaeufe/` zeigen noch auf echten Code (06.10.2026).

Ein Prozessbild ist ein Ablauf in n8n ohne Webhook (heimnetzwerk: Karte,
Nachtrag 06.10.2026; ops-core Schritt 24): Es zeichnet, wie ein Prozess im
Code der App laeuft, und laeuft selbst nie. Es enthaelt Struktur, keine
Daten -- darum darf es auch hier liegen. Doku, die nicht laeuft, luegt
irgendwann -- darum nennt jeder Knoten in seiner Notiz die Stelle im Code
(`Code: pfad` oder `Code: pfad::name`, relativ zur Wurzel des Repos), und
dieser Test prueft, dass es Datei und Namen noch gibt. Neue Schritte findet
er nicht, verschwundene schon. Gesucht wird, wo der Import sucht:
`deploy/**/n8n/ablaeufe/`; ein Ablauf mit Webhook ist kein Bild.

Dieselbe Pruefung steht in heimnetzwerk und im Kurator -- als Kopie, mit
Absicht: Jedes System prueft seine eigenen Bilder. Import und Export:
`heimnetzwerk/deploy/ops-core/n8n-ablaeufe.sh`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CODE = re.compile(r"^Code: (?P<pfad>[\w./-]+)(?:::(?P<name>\w+))?$", re.MULTILINE)
GEZEICHNET = {"n8n-nodes-base.noOp", "n8n-nodes-base.if"}


def _bilder() -> list[Path]:
    alle = sorted(REPO.glob("deploy/**/n8n/ablaeufe/*.json"))
    return [p for p in alle
            if not any(n["type"] == "n8n-nodes-base.webhook" for n in json.loads(p.read_text())["nodes"])]


BILDER = _bilder()


def test_es_gibt_bilder() -> None:
    assert BILDER, "keine Prozessbilder unter deploy/**/n8n/ablaeufe/"


@pytest.mark.parametrize("datei", BILDER, ids=lambda p: p.stem)
def test_ein_bild_laeuft_nie(datei: Path) -> None:
    wf = json.loads(datei.read_text())
    arten = {n["type"] for n in wf["nodes"]} - {"n8n-nodes-base.stickyNote"}
    assert arten <= GEZEICHNET, f"{datei.name}: {arten - GEZEICHNET} gehört nicht in ein Bild"
    assert wf["settings"].get("saveDataSuccessExecution") == "none"


@pytest.mark.parametrize("datei", BILDER, ids=lambda p: p.stem)
def test_jeder_schritt_nennt_seinen_code(datei: Path) -> None:
    for n in json.loads(datei.read_text())["nodes"]:
        if n["type"] in GEZEICHNET:
            assert CODE.search(n.get("notes", "")), f"{datei.name}: „{n['name']}“ nennt keinen Code"


@pytest.mark.parametrize("datei", BILDER, ids=lambda p: p.stem)
def test_den_code_gibt_es_noch(datei: Path) -> None:
    fehlt = []
    for n in json.loads(datei.read_text())["nodes"]:
        for m in CODE.finditer(n.get("notes", "")):
            quelle = REPO / m["pfad"]
            if not quelle.is_file():
                fehlt.append(f"„{n['name']}“: {m['pfad']} gibt es nicht")
            elif m["name"] and not re.search(
                rf"^\s*(?:def|class|async def) {m['name']}\b|^{m['name']}\b.*=",
                quelle.read_text(encoding="utf-8"), re.MULTILINE,
            ):
                fehlt.append(f"„{n['name']}“: {m['name']} steht nicht in {m['pfad']}")
    assert not fehlt, f"{datei.name}: " + "; ".join(fehlt)
