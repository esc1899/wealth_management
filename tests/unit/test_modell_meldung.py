"""Ein neueres Claude-Modell als Meldung auf der Startseite (29.09.2026)."""

from core import house_models
from core.modell_meldung import agenten_modelle, modell_meldung

KATALOG = {
    "current": ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-4-5-20251001"],
    "names": {"claude-opus-5": "Claude Opus 5", "claude-opus-5-5": "Claude Opus 5.5",
              "claude-sonnet-5": "Claude Sonnet 5", "claude-sonnet-5-5": "Claude Sonnet 5.5",
              "claude-haiku-4-5-20251001": "Claude Haiku 4.5"},
    "stand": "2026-09-29T06:53:00+02:00",
}


def test_ein_agent_auf_dem_alten_sonnet():
    m = modell_meldung({"Story Checker": "claude-sonnet-5", "News-Digest": "claude-sonnet-5",
                        "Investment-Suche": "claude-opus-5-5"}, KATALOG)
    assert m["text"] == "Neueres Claude-Modell: Sonnet 5.5"
    assert m["zusatz"] == "Sonnet 5 noch bei Story Checker, News-Digest"
    assert (m["zustand"], m["lauf"], m["von"], m["ziel"]) == (
        "hinweis", "Modellkatalog", "2026-09-29", "settings")
    assert "verwerfen" not in m                      # ein Zustand, kein x


def test_zwei_familien():
    m = modell_meldung({"A": "claude-sonnet-5", "B": "claude-opus-5"}, KATALOG)
    assert m["text"] == "Neuere Claude-Modelle: Sonnet 5.5, Opus 5.5"
    assert m["zusatz"] == "Sonnet 5 noch bei A; Opus 5 noch bei B"


def test_stumm_wenn_aktuell_home_fremd_oder_unbekannt():
    assert modell_meldung({"A": "claude-sonnet-5-5", "B": "home", "C": "deepseek/deepseek-v3",
                           "D": "claude-haiku-4-5", "E": "claude-alt-1"}, KATALOG) is None
    assert modell_meldung({"A": "claude-sonnet-5"}, {}) is None     # ohne Katalog


def test_die_einstellung_wie_state_llm():
    gespeichert = {"model_public_news": "claude-sonnet-5", "model_claude_search": "claude-opus-5"}
    modelle = agenten_modelle(gespeichert.get, standard="claude-opus-5-5")
    assert modelle["News-Digest"] == "claude-sonnet-5"
    assert modelle["Investment-Suche"] == "claude-opus-5"           # alter Schlüssel
    assert modelle["Story Checker"] == "claude-opus-5-5"             # nichts gespeichert


def test_der_katalog_liefert_namen_und_stand(tmp_path):
    pfad = tmp_path / "katalog.toml"
    pfad.write_text('[claude]\nstand = "2026-09-29T06:53:00+02:00"\n'
                    'aktuell = ["claude-sonnet-5-5"]\n'
                    '[claude.preise."claude-sonnet-5-5"]\nname = "Claude Sonnet 5.5"\n'
                    'eingabe = 3\nausgabe = 15\n', encoding="utf-8")
    k = house_models.load_catalog(path=pfad)
    assert k["names"] == {"claude-sonnet-5-5": "Claude Sonnet 5.5"}
    assert k["stand"] == "2026-09-29T06:53:00+02:00"
