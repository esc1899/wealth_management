"""Der Portfolio Checker: das Depot als Ganzes gegen die Portfolio-Story, lokal (Ollama).

Er prüft keinen Titel, sondern liest, was die Checks über die Titel gesagt haben -- seit
11.10.2026 die Urteile **aller gewählten** Depot-Checks (``core/pruefung.py``), vorher nur die
des Storycheckers. Zwei Wege rufen ihn: der Knopf auf der Seite Portfolio-Story und das Ende
des Jobs "Depot prüfen" (``core/scheduler.py::durchgaenge_nachziehen``). Beide bauen ihre
Eingabe hier, damit sie dasselbe fragen.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional, Sequence

from core.portfolio_snapshot import build_portfolio_snapshot
from core.storage.models import PortfolioStoryAnalysis


def urteilszeilen(positionen: Sequence, urteile: dict, checks: Sequence[str],
                  name_von: Callable[[str], str] = str, ausstehend: str = "noch nicht geprüft") -> str:
    """Je Titel eine Zeile, darunter je gewähltem Check Urteil und Satz.
    ``urteile``: ``{check: {position_id: PositionAnalysis}}``."""
    zeilen = []
    for p in positionen:
        if p.id is None:
            continue
        zeilen.append(f"- {p.name} ({p.ticker or '—'})")
        for check in checks:
            u = urteile.get(check, {}).get(p.id)
            if u is None:
                zeilen.append(f"  - {name_von(check)}: {ausstehend}")
            else:
                satz = f" — {u.summary}" if u.summary else ""
                zeilen.append(f"  - {name_von(check)}: {u.verdict or '?'}{satz}")
    return "\n".join(zeilen)


async def story_check(agent, story, positionen: Sequence, bewertungen: Sequence, urteile: dict,
                      checks: Sequence[str], name_von: Callable[[str], str] = str,
                      leer: str = "", ausstehend: str = "noch nicht geprüft",
                      keine: str = "") -> PortfolioStoryAnalysis:
    """Ein Lauf gegen die Story; gibt die Analyse zum Speichern zurück (speichert nicht)."""
    snapshot = (build_portfolio_snapshot(list(positionen), list(bewertungen)) if positionen
                else "## Portfolio\n" + leer + "\n")
    ergebnis = await agent.analyze_story_and_performance(
        story=story,
        portfolio_snapshot=snapshot,
        position_verdicts=urteilszeilen(positionen, urteile, checks, name_von, ausstehend) or keine,
    )
    return PortfolioStoryAnalysis(
        verdict=ergebnis.verdict,
        summary=ergebnis.summary,
        perf_verdict=ergebnis.perf_verdict,
        perf_summary=ergebnis.perf_summary,
        stability_verdict=None,
        stability_summary=None,
        full_text=ergebnis.full_text,
        created_at=datetime.now(timezone.utc),
    )


def urteile_der_checks(analyses_repo, positionen: Sequence, checks: Sequence[str]) -> dict:
    """``{check: {position_id: jüngstes Urteil}}`` für die Titel."""
    ids = [p.id for p in positionen if p.id is not None]
    return {c: analyses_repo.get_latest_bulk(ids, c) for c in checks} if ids else {}


def juengste(story_repo) -> Optional[PortfolioStoryAnalysis]:
    return story_repo.get_latest_analysis() if story_repo is not None else None
