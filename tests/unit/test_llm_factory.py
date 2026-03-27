import pytest
from core.llm.factory import create_llm, LLMBackend
from core.llm.local import OllamaProvider
from core.llm.claude import ClaudeProvider


def test_factory_creates_ollama():
    provider = create_llm(
        LLMBackend.LOCAL, host="http://localhost:11434", model="llama3.2"
    )
    assert isinstance(provider, OllamaProvider)
    assert provider.model == "llama3.2"


def test_factory_creates_claude():
    provider = create_llm(LLMBackend.CLAUDE, api_key="test_key")
    assert isinstance(provider, ClaudeProvider)
    assert provider.model == "claude-sonnet-4-6"


def test_factory_claude_custom_model():
    provider = create_llm(
        LLMBackend.CLAUDE, api_key="test_key", model="claude-opus-4-6"
    )
    assert provider.model == "claude-opus-4-6"


def test_factory_unknown_backend_raises():
    with pytest.raises(ValueError, match="Unknown LLM backend"):
        create_llm("unknown_backend")
