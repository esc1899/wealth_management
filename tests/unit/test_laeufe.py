"""Letzte Läufe in der Statistik (core/laeufe.py): je Lauf eine Zeile, die App je Tag."""

from __future__ import annotations

from core import laeufe


def _a(ts, agent="bewegung", model="claude-haiku-4-5", source="scheduled", lauf=None, job=None):
    return {"created_at": ts, "agent": agent, "model": model, "source": source,
            "lauf": lauf, "job": job, "input_tokens": 1, "output_tokens": 1}


def test_ein_lauf_eine_zeile_neueste_zuerst():
    aufrufe = [
        _a("2026-10-16T16:05:00", lauf="R1", job="kurse"),
        _a("2026-10-16T16:06:00", lauf="R1", job="kurse"),
        _a("2026-10-17T07:00:00", agent="storychecker", model="claude-sonnet-5-5", lauf="R2",
           job="agenten"),
    ]
    zeilen = laeufe.laeufe(aufrufe, lambda r: 0.1)
    assert [(z["job"], z["aufrufe"], z["wie"]) for z in zeilen] == [("agenten", 1, "job"), ("kurse", 2, "job")]
    assert zeilen[1]["agenten"] == ["Kursbewegung"] and round(zeilen[1]["kosten"], 6) == 0.2


def test_batch_ist_ein_lauf_auch_wenn_agenten_ihn_abholt():
    zeilen = laeufe.laeufe([_a("2026-10-17T07:05:00", source="batch", lauf="msgbatch_1", job="agenten"),
                            _a("2026-10-17T07:05:01", source="batch", lauf="msgbatch_1", job="agenten")],
                           lambda r: 0.05)
    assert len(zeilen) == 1 and zeilen[0]["wie"] == laeufe.BATCH and zeilen[0]["aufrufe"] == 2


def test_app_je_tag_und_agent_und_ohne_preis_offen():
    aufrufe = [_a("2026-10-17T09:00:00", agent="research", source="manual", job="interaktiv"),
               _a("2026-10-17T11:00:00", agent="research", source="manual", job="interaktiv",
                  model="mistral/x"),
               _a("2026-10-16T11:00:00", agent="research", source="manual", job="interaktiv")]
    zeilen = laeufe.laeufe(aufrufe, lambda r: None if r["model"] == "mistral/x" else 0.01)
    assert [(z["wie"], z["job"], z["aufrufe"], z["offen"]) for z in zeilen] == [
        ("hand", None, 2, 1), ("hand", None, 1, 0)]
    assert zeilen[0]["modelle"] == ["claude-haiku-4-5", "mistral/x"]


def test_alte_aufrufe_ohne_lauf_nach_weg_getrennt():
    zeilen = laeufe.laeufe([_a("2026-10-15T09:00:00", source="scheduled"),
                            _a("2026-10-15T09:01:00", source="batch")], lambda r: 0.0)
    assert sorted(z["wie"] for z in zeilen) == ["batch", "job"]
