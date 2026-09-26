#!/usr/bin/env python
"""Der Empfänger für das x an der Meldung auf der Startseite des Mac mini.

    python scripts/meldungen_dienst.py            # 127.0.0.1:8656
    python scripts/meldungen_dienst.py --port 0   # irgendein freier Port (Tests)

Die Startseite schickt beim x ein POST an den Pfad, den die Meldung in `verwerfen`
mitbringt (`kacheln/wealth/verwerfen?story=<Durchgang>`). Streamlit kann das nicht
annehmen, darum dieser Prozess: nur Standardbibliothek, nur 127.0.0.1, Caddy leitet
`/kacheln/wealth/*` hierher und schneidet das Präfix ab (Registry der Dienste,
`zugang = "lokal"`). ops-core startet ihn als Dienst (`jobs.toml`, services.meldungen).

Ein x merkt sich den verworfenen Durchgang in der App (`app_config`), damit der stündliche
Kachel-Lauf die Meldung nicht wiederbringt, und nimmt sie sofort aus der Kachel-Datei —
die Startseite holt die Kachel direkt danach neu. Ein zweites x auf denselben Durchgang
ändert nichts. Gerechnet wird hier nichts; die Datei wird nur gefiltert.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from core.story_meldung import VERWORFEN_KEY  # noqa: E402


def kachel_datei() -> Path:
    return Path(os.environ.get("DIENSTE_HOME") or Path.home() / ".dienste") / "www" / "kacheln" / "wealth.json"


def _merken(schluessel: str) -> None:
    from config import config
    from core.storage.app_config import AppConfigRepository
    from core.storage.base import get_connection

    conn = get_connection(config.DB_PATH)
    try:
        AppConfigRepository(conn).set(VERWORFEN_KEY, schluessel)
    finally:
        conn.close()


def aus_der_kachel(datei: Path, schluessel: str) -> bool:
    """Die Meldung dieses Durchgangs aus der Kachel-Datei nehmen. True, wenn sich etwas
    geändert hat. Atomar ersetzt, damit die Startseite nie eine halbe Datei liest."""
    try:
        daten = json.loads(datei.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    vorher = daten.get("meldungen") or []
    nachher = [m for m in vorher if m.get("schluessel") != schluessel]
    if len(nachher) == len(vorher):
        return False
    if nachher:
        daten["meldungen"] = nachher
    else:
        daten.pop("meldungen", None)
    tmp = datei.with_suffix(".tmp")
    tmp.write_text(json.dumps(daten, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(datei)
    return True


def handler(merken=_merken, datei=kachel_datei):
    class Handler(BaseHTTPRequestHandler):
        def _antwort(self, code: int, text: str = "") -> None:
            body = text.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if urlsplit(self.path).path == "/health":
                return self._antwort(200, "ok")
            self._antwort(404, "nicht hier")

        def do_POST(self) -> None:  # noqa: N802
            teile = urlsplit(self.path)
            if teile.path != "/verwerfen":
                return self._antwort(404, "nicht hier")
            story = (parse_qs(teile.query).get("story") or [""])[0]
            if not story:
                return self._antwort(400, "welche Meldung?")
            try:
                merken(story)
            except Exception as exc:   # ohne Gedächtnis käme sie in einer Stunde wieder
                print(f"Verwerfen nicht gemerkt: {exc}", file=sys.stderr)
                return self._antwort(500, "nicht gemerkt")
            aus_der_kachel(datei(), story)
            self._antwort(204)

        def log_message(self, fmt: str, *args) -> None:
            print(f"{self.command} {self.path} -> {args[1] if len(args) > 1 else ''}", file=sys.stderr)

    return Handler


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Empfänger für das x an der Meldung auf der Startseite")
    p.add_argument("--port", type=int, default=8656)
    args = p.parse_args(argv)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler())
    print(f"hört auf 127.0.0.1:{server.server_address[1]}", file=sys.stderr)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
