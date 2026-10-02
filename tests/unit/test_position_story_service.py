"""Der Story-Entwurf: aktuell (Websuche), nie leer, nur die These."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.services.position_story_service import PositionStoryService


def _service():
    return PositionStoryService(api_key="test", model="claude-haiku-4-5")


def _antwort(provider, text):
    provider.return_value.chat_with_tools = AsyncMock(return_value=MagicMock(content=text))
    return provider.return_value.chat_with_tools


@pytest.mark.parametrize("text", ["", "   \n", None, "<these> </these>"])
def test_leere_antwort_ist_ein_fehler(text):
    with patch("core.services.position_story_service.ClaudeProvider") as provider:
        _antwort(provider, text)
        with pytest.raises(RuntimeError, match="keinen Text"):
            _service().generate_position_story(name="X", existing_story="alte Story")


def test_nur_die_these_ohne_zwischentext():
    with patch("core.services.position_story_service.ClaudeProvider") as provider:
        _antwort(provider, "Ich suche nach aktuellen Meldungen.\n<these>\nNeue These.\n</these>")
        assert _service().generate_position_story(name="X") == "Neue These."


def test_ohne_marken_zaehlt_der_ganze_text():
    with patch("core.services.position_story_service.ClaudeProvider") as provider:
        _antwort(provider, "  Neue These.\n")
        assert _service().generate_position_story(name="X") == "Neue These."


def test_sucht_im_web_mit_heutigem_datum_und_budget():
    with patch("core.services.position_story_service.ClaudeProvider") as provider:
        aufruf = _antwort(provider, "<these>T</these>")
        _service().generate_position_story(name="Kongsberg", ticker="KOG.OL")
        kw = aufruf.call_args.kwargs
        assert any(t.get("name") == "web_search" for t in kw["tools"])
        assert "Heute ist der" in kw["system"]
        assert kw["max_tokens"] >= 2000
