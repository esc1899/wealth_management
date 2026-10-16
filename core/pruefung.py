"""Welche Checks zu einer Prüfung gehören -- je Liste (Depot, Watchlist) eine Auswahl.

Eine Prüfung eines Titels ist ein **Durchgang**: alle gewählten Checks, ein Datum
(``core/storage/durchgaenge.py``). Was gewählt ist, steht in ``app_config`` unter
``pruefung_auswahl_<liste>`` und wird auf der Seite Einstellungen bearbeitet; die Kacheln und
die Titelseite zeigen genau diese Checks, auch die, die für einen Titel nie liefen.

Möglich ist je Liste eine feste Reihe in fester Reihenfolge. Devil's Advocate gehört nur auf
die Watchlist (Erik, 11.10.2026): Er sucht Gründe, einen Titel *nicht* zu kaufen. Die dritte
Liste sind die Kandidaten der Suche (``core/kandidaten.py``): dieselben Checks wie die
Watchlist, eigene Auswahl, nur per Knopf "Genauer prüfen" -- kein Job.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable, Optional

#: Was je Liste gewählt werden kann, in Anzeigereihenfolge.
MOEGLICH: dict[str, tuple[str, ...]] = {
    "depot": ("storychecker", "fundamental_analyzer", "consensus_gap", "capital_allocator"),
    "watchlist": ("watchlist_checker", "devils_advocate", "fundamental_analyzer",
                  "capital_allocator", "consensus_gap", "storychecker"),
}
MOEGLICH["kandidaten"] = MOEGLICH["watchlist"]

#: Läuft lokal und liest die Urteile der anderen -- darum im Durchgang zuletzt.
ZULETZT = ("watchlist_checker",)

_SCHLUESSEL = "pruefung_auswahl_{}"


def auswahl(app_cfg, liste: str) -> tuple[str, ...]:
    """Die gewählten Checks der Liste in fester Reihenfolge; nie gewählt = alles Mögliche.
    Ein gespeicherter Name, den es nicht mehr gibt, fällt still weg."""
    moeglich = MOEGLICH[liste]
    gespeichert = app_cfg.get_json(_SCHLUESSEL.format(liste)) if app_cfg is not None else None
    if not isinstance(gespeichert, list):
        return moeglich
    return tuple(c for c in moeglich if c in gespeichert)


def pruefbar(position) -> bool:
    """Ob die Checks zu dem Titel etwas sagen können. Sie beurteilen Unternehmen und Fonds
    (These, Zahlen, Konsens, Kapitalverwendung); ein Rohstoff hat nichts davon (Erik,
    16.10.2026). Das sagt die Klasse (``pruefbar`` in config/asset_classes.yaml); eine
    unbekannte gilt als prüfbar. Kein Lauf nimmt den Titel, keine Kachel zeigt ein Urteil."""
    from core.asset_class_config import get_asset_class_registry

    cfg = get_asset_class_registry().get(getattr(position, "asset_class", None) or "")
    return cfg is None or cfg.pruefbar


def auswahl_setzen(app_cfg, liste: str, checks: Iterable[str]) -> tuple[str, ...]:
    """Speichert die Auswahl (nur Mögliches, feste Reihenfolge) und gibt sie zurück."""
    gewaehlt = set(checks)
    reihe = tuple(c for c in MOEGLICH[liste] if c in gewaehlt)
    app_cfg.set_json(_SCHLUESSEL.format(liste), list(reihe))
    return reihe


def reihenfolge(checks: Iterable[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(zuerst, danach): die Cloud-Checks parallel, dann die, die deren Urteile lesen."""
    checks = tuple(checks)
    return (tuple(c for c in checks if c not in ZULETZT),
            tuple(c for c in checks if c in ZULETZT))


#: Checks mit eigenem Skill und der Skill-Bereich dazu. Der Storychecker nimmt den Skill der
#: Position (``story_skill``), der Watchlist Checker keinen.
SKILL_BEREICH = {
    "fundamental_analyzer": "fundamental_analyzer",
    "consensus_gap": "consensus_gap",
    "capital_allocator": "capital_allocator",
    "devils_advocate": "devils_advocate",
}

_SKILLS = "pruefung_skills_{}"


def skills(app_cfg, liste: str) -> dict[str, str]:
    """Je Check der gewählte Skill (Name); fehlt einer, gilt der Standard."""
    gespeichert = app_cfg.get_json(_SKILLS.format(liste)) if app_cfg is not None else None
    return {k: v for k, v in (gespeichert or {}).items() if k in SKILL_BEREICH and v}


def skills_setzen(app_cfg, liste: str, je_check: dict[str, str]) -> None:
    app_cfg.set_json(_SKILLS.format(liste),
                     {k: v for k, v in je_check.items() if k in SKILL_BEREICH and v})


def skill_fuer(app_cfg, skills_repo, liste: str, check: str) -> tuple[str, str]:
    """(Name, Prompt) des Skills, mit dem ``check`` in dieser Liste läuft."""
    from core.constants import AGENT_SKILL_DEFAULTS

    name = skills(app_cfg, liste).get(check)
    if name and skills_repo is not None:
        skill = skills_repo.get_by_name(name)
        if skill:
            return skill.name, skill.prompt or ""
    return AGENT_SKILL_DEFAULTS.get(check, "Standard"), ""


# ------------------------------------------------------------------
# Ein Cloud-Modell je Bereich (Erik, 11.10.2026, mit Blick auf Lotsee: so einfach wie möglich)
# ------------------------------------------------------------------

#: Die drei Bereiche nach Datengrenze und die Agenten, deren Eintrag je Agent (``model_public_*``)
#: der Bereich mitschreibt. Die Checks stehen im Depot, weil das ihr Rückfall ist; auf der
#: Watchlist bekommen sie das Modell der Watchlist ausdrücklich (Knopf und Job). Devil's Advocate
#: prüft nur die Watchlist.
BEREICHE: dict[str, tuple[str, ...]] = {
    "depot": ("storychecker", "fundamental_analyzer", "consensus_gap", "capital_allocator",
              "news", "sector_rotation", "position_story"),
    "watchlist": ("devils_advocate",),
    "research": ("search", "structural_scan", "research"),
}

#: Woher ein Bereich sein Modell nimmt, solange er noch keins gespeichert hat.
_BISHER = {"depot": "storychecker", "watchlist": "devils_advocate", "research": "research"}


def modell(app_cfg, bereich: str) -> str:
    """Das Cloud-Modell des Bereichs; "" = Standard der App. Kandidaten prüfen mit dem Modell
    der Watchlist -- es sind deren Checks, und wer übernimmt, soll dasselbe Urteil sehen."""
    if app_cfg is None:
        return ""
    if bereich == "kandidaten":
        bereich = "watchlist"
    return (app_cfg.get(f"model_bereich_{bereich}")
            or app_cfg.get(f"model_public_{_BISHER[bereich]}") or "")


def modell_setzen(app_cfg, bereich: str, wert: str) -> None:
    """Speichert das Modell des Bereichs und schreibt es in die Einträge seiner Agenten, die
    alle übrigen Wege lesen (state_llm, background_jobs, scheduler)."""
    app_cfg.set(f"model_bereich_{bereich}", wert)
    for agent in BEREICHE[bereich]:
        app_cfg.set(f"model_public_{agent}", wert)


#: Die lokalen Agenten (Ollama). Seit 11.10.2026 ein Modell für alle -- lokal sieht jeder alles,
#: eine Datengrenze zwischen ihnen gibt es nicht, und ein zweites Modell verdrängte das erste
#: aus dem geteilten Speicher.
LOKALE_AGENTEN = ("portfolio", "portfolio_story", "watchlist_checker",
                  "portfolio_robustness", "rebalance", "dividend_calendar", "tax_loss_harvesting",
                  "skill_generator")


def lokales_modell(app_cfg, standard: str = "") -> str:
    """Das eine lokale Modell; ohne Eintrag das des Portfolio Checkers, sonst ``standard``."""
    if app_cfg is None:
        return standard
    return app_cfg.get("model_ollama") or app_cfg.get("model_ollama_portfolio_story") or standard


def lokales_modell_setzen(app_cfg, wert: str) -> None:
    """Speichert das lokale Modell und schreibt es in die Einträge aller lokalen Agenten."""
    app_cfg.set("model_ollama", wert)
    for agent in LOKALE_AGENTEN:
        app_cfg.set(f"model_ollama_{agent}", wert)


# ------------------------------------------------------------------
# Die eingeplanten Jobs: einer je Liste statt einer je Check
# ------------------------------------------------------------------

#: Der Job, der die Auswahl einer Liste für alle Titel laufen lässt.
JOB = {"depot": "pruefung_depot", "watchlist": "pruefung_watchlist"}
LISTE_DES_JOBS = {v: k for k, v in JOB.items()}

#: Die Jobs je Check von früher; seit Schritt 2 abgeschaltet (Erik löscht sie selbst).
ALTE_JOBS = ("storychecker", "fundamental_analyzer", "consensus_gap", "devils_advocate",
             "capital_allocator")

_UMGESTELLT = "pruefung_jobs_umgestellt"


def jobs_umstellen(jobs_repo, app_cfg) -> bool:
    """Einmal: die Jobs je Liste anlegen, Skills der alten Jobs übernehmen, alte abschalten.
    "Depot prüfen" bekommt Takt und an/aus des Storychecker-Jobs (Erik, 11.10.2026), "Watchlist
    prüfen" ist aus. Gibt True zurück, wenn diesmal umgestellt wurde."""
    from core.storage.models import ScheduledJob

    if app_cfg.get(_UMGESTELLT):
        return False
    alle = jobs_repo.get_all()
    vorhanden = {j.agent_name for j in alle}

    vorlage = next((j for j in alle if j.agent_name == "storychecker"), None)
    if JOB["depot"] not in vorhanden:
        takt = dict(frequency="monthly", run_hour=6, run_minute=0, run_day=1, enabled=True)
        if vorlage is not None and vorlage.frequency != "manual":
            takt = dict(frequency=vorlage.frequency, run_hour=vorlage.run_hour,
                        run_minute=vorlage.run_minute, run_weekday=vorlage.run_weekday,
                        run_day=vorlage.run_day, run_month=vorlage.run_month,
                        enabled=vorlage.enabled)
        jobs_repo.add(ScheduledJob(agent_name=JOB["depot"], skill_name="", skill_prompt="", **takt))
    if JOB["watchlist"] not in vorhanden:
        jobs_repo.add(ScheduledJob(agent_name=JOB["watchlist"], skill_name="", skill_prompt="",
                                   frequency="monthly", run_hour=6, run_minute=30, run_day=1,
                                   enabled=False))

    # Skills: was ein alter Job eingestellt hatte, gilt für beide Listen, die den Check kennen.
    for liste in MOEGLICH:
        je_check = skills(app_cfg, liste)
        for j in alle:
            if (j.agent_name in SKILL_BEREICH and j.agent_name in MOEGLICH[liste]
                    and j.skill_name and j.agent_name not in je_check):
                je_check[j.agent_name] = j.skill_name
        skills_setzen(app_cfg, liste, je_check)

    for j in alle:
        if j.agent_name in ALTE_JOBS and j.enabled:
            jobs_repo.set_enabled(j.id, False)
    app_cfg.set(_UMGESTELLT, "1")
    return True


def depot_kontext(portfolio: list, story_analyse=None, stabilitaet: str = "Stabilität:",
                  leer: str = "") -> tuple[str, Optional[str]]:
    """Was der Watchlist Checker über das Depot erfährt: die Verteilung nach Anlageklasse und
    die jüngste Analyse der Portfolio-Story. Beides lokal (Ollama), nie in die Cloud."""
    snapshot = "## Portfolio Allocation (Josef's Regel)\n"
    if portfolio:
        zahl = Counter(p.asset_class for p in portfolio if p.asset_class)
        gesamt = len(portfolio)
        for klasse, n in zahl.most_common():
            snapshot += f"- {klasse}: {n} Positionen ({100 * n / gesamt:.0f}%)\n"
    else:
        snapshot += leer + "\n"

    if story_analyse is None:
        return snapshot, None
    a = story_analyse
    return snapshot, f"""## Portfolio Story Context
Story: {a.verdict}
Summary: {a.summary}
Performance: {a.perf_verdict} - {a.perf_summary}
{stabilitaet} {a.stability_verdict} - {a.stability_summary}

Full Analysis:
{a.full_text}
"""
