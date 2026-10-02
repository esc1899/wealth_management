"""Der Story-Entwurf: aktuell (Websuche), nie leer, nur die These."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.position_story_service import PositionStoryService


def _service(llm):
    return PositionStoryService(provider_factory=lambda: llm)


def _antwort(text):
    llm = MagicMock(_model="claude-haiku-4-5")
    llm.chat_with_tools = AsyncMock(return_value=MagicMock(content=text))
    return llm


@pytest.mark.parametrize("text", ["", "   \n", None, "<these> </these>"])
def test_leere_antwort_ist_ein_fehler(text):
    with pytest.raises(RuntimeError, match="keinen Text"):
        _service(_antwort(text)).generate_position_story(name="X", existing_story="alte Story")


def test_nur_die_these_ohne_zwischentext():
    llm = _antwort("Ich suche nach aktuellen Meldungen.\n<these>\nNeue These.\n</these>")
    assert _service(llm).generate_position_story(name="X") == "Neue These."


def test_ohne_marken_zaehlt_der_ganze_text():
    assert _service(_antwort("  Neue These.\n")).generate_position_story(name="X") == "Neue These."


def test_sucht_im_web_mit_heutigem_datum_und_budget():
    llm = _antwort("<these>T</these>")
    _service(llm).generate_position_story(name="Kongsberg", ticker="KOG.OL")
    kw = llm.chat_with_tools.call_args.kwargs
    assert any(t.get("name") == "web_search" for t in kw["tools"])
    assert "Heute ist der" in kw["system"]
    assert kw["max_tokens"] >= 2000
