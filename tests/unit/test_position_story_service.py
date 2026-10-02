"""Ein leerer Story-Entwurf darf die bestehende Story nie ersetzen."""

from unittest.mock import AsyncMock, patch

import pytest

from core.services.position_story_service import PositionStoryService


def _service():
    return PositionStoryService(api_key="test", model="claude-haiku-4-5")


@pytest.mark.parametrize("antwort", ["", "   \n", None])
def test_leere_antwort_ist_ein_fehler(antwort):
    with patch("core.services.position_story_service.ClaudeProvider") as provider:
        provider.return_value.complete = AsyncMock(return_value=antwort)
        with pytest.raises(RuntimeError, match="keinen Text"):
            _service().generate_position_story(name="X", existing_story="alte Story")


def test_entwurf_wird_getrimmt_und_mit_budget_geholt():
    with patch("core.services.position_story_service.ClaudeProvider") as provider:
        provider.return_value.complete = AsyncMock(return_value="  Neue These.\n")
        assert _service().generate_position_story(name="X") == "Neue These."
        assert provider.return_value.complete.call_args.kwargs["max_tokens"] >= 2000
