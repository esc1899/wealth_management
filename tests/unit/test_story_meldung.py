"""Der Story-Check als Meldung auf der Startseite (Dienste Schritt 15, 26.09.2026)."""

from datetime import datetime, timezone

from core.story_meldung import durchgang, story_meldung


def _t(tag: int, stunde: int = 9) -> datetime:
    return datetime(2026, 9, tag, stunde, 0)          # naives UTC wie created_at


URTEILE = {1: ("intact", _t(20)), 2: ("intact", _t(20, 10)), 3: ("gemischt", _t(21)),
           4: ("gefaehrdet", _t(21, 11))}


def test_die_summe_der_urteile_mit_link_auf_den_checker():
    m = story_meldung(URTEILE, [1, 2, 3, 4])
    assert m["text"] == "Story-Check: 2 intakt · 1 gemischt · 1 gefährdet"
    assert m["zustand"] == "schlecht"                 # ein gefährdetes Urteil färbt die Meldung
    assert (m["lauf"], m["von"], m["ziel"]) == ("Story-Check", "2026-09-21", "storychecker")
    assert m["schluessel"] == "2026-09-20T09:00:00+00:00"   # das älteste jüngste Urteil


def test_ohne_gefaehrdet_ein_hinweis_und_die_null_steht_da():
    m = story_meldung({1: ("intact", _t(20)), 2: ("gemischt", _t(20))}, [1, 2])
    assert m["text"] == "Story-Check: 1 intakt · 1 gemischt · 0 gefährdet"
    assert m["zustand"] == "hinweis"


def test_nicht_durch_heisst_keine_meldung():
    assert story_meldung(URTEILE, [1, 2, 3, 4, 5]) is None   # Position 5 noch ohne Urteil
    assert story_meldung({}, []) is None


def test_verworfen_gilt_nur_fuer_diesen_durchgang():
    schluessel = story_meldung(URTEILE, [1, 2, 3, 4])["schluessel"]
    assert story_meldung(URTEILE, [1, 2, 3, 4], verworfen=schluessel) is None
    # Einzelne Positionen neu geprüft: derselbe Durchgang, bleibt verworfen
    teils = {**URTEILE, 3: ("intact", _t(25))}
    assert story_meldung(teils, [1, 2, 3, 4], verworfen=schluessel) is None
    # Alle neu geprüft: ein neuer Durchgang, eine neue Meldung
    neu = {i: (v, _t(28)) for i, (v, _) in URTEILE.items()}
    assert story_meldung(neu, [1, 2, 3, 4], verworfen=schluessel)["von"] == "2026-09-28"


def test_der_durchgang_waechst_nur_mit_der_letzten_position():
    assert durchgang(URTEILE, [1, 2, 3, 4]) == datetime(2026, 9, 20, 9, tzinfo=timezone.utc)
    assert durchgang({**URTEILE, 1: ("intact", _t(26))}, [1, 2, 3, 4]) == datetime(
        2026, 9, 20, 10, tzinfo=timezone.utc)


def test_ein_unbekanntes_urteil_wird_gezaehlt_nicht_versteckt():
    m = story_meldung({1: ("intact", _t(20)), 2: ("unknown", _t(20))}, [1, 2])
    assert m["text"].endswith("· 1 ohne Urteil")


def test_das_x_traegt_den_durchgang():
    m = story_meldung(URTEILE, [1, 2, 3, 4])
    assert m["verwerfen"] == "kacheln/wealth/verwerfen?story=2026-09-20T09%3A00%3A00%2B00%3A00"


def test_der_empfaenger_merkt_und_nimmt_die_meldung_aus_der_kachel(tmp_path):
    import json
    import sys
    import threading
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    import meldungen_dienst as md

    m = story_meldung(URTEILE, [1, 2, 3, 4])
    datei = tmp_path / "wealth.json"
    datei.write_text(json.dumps({"zeilen": ["x"], "meldungen": [m]}), encoding="utf-8")
    gemerkt = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), md.handler(merken=gemerkt.append, datei=lambda: datei))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    basis = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        assert urllib.request.urlopen(basis + "/health").read() == b"ok"
        pfad = m["verwerfen"].removeprefix("kacheln/wealth")      # Caddy schneidet das Präfix ab
        r = urllib.request.urlopen(urllib.request.Request(basis + pfad, method="POST"))
        assert r.status == 204
        assert gemerkt == [m["schluessel"]]
        assert "meldungen" not in json.loads(datei.read_text(encoding="utf-8"))
        # Ein zweites x ändert nichts, eines ohne Durchgang wird abgelehnt
        urllib.request.urlopen(urllib.request.Request(basis + pfad, method="POST"))
        try:
            urllib.request.urlopen(urllib.request.Request(basis + "/verwerfen", method="POST"))
            assert False, "ohne story haette es scheitern muessen"
        except urllib.error.HTTPError as e:
            assert e.code == 400
    finally:
        server.shutdown()
