"""Executable architecture guards (FEAT-60).

These tests turn the project's prose invariants (CLAUDE.md / ARCHITECTURE.md) into
code that fails in CI instead of relying on human review. The most critical one is
the **Privacy boundary**: sensitive portfolio data (encrypted ``Position`` with
``story``/``notes``/``extra_data``) must never reach a cloud LLM agent.

Closed feedback loops:
  1. ``test_every_agent_is_classified`` — a *new* agent file forces the author to
     put the class in exactly one bucket (cloud / local / non-LLM). Until then the
     test fails. This is what makes guards 2+3 reach every future agent.
  2. ``test_cloud_agents_never_accept_private_position`` — cloud agents may only take
     ``PublicPosition`` as input, never the encrypted ``Position``. StorycheckerAgent
     is the single documented exception (it needs ``name`` + ``story``).
  3. ``test_agent_classification_matches_llm_provider`` — anti-misclassification:
     a cloud agent cannot be hidden in the local bucket to dodge guard 2, because its
     ``llm`` parameter type is cross-checked against the bucket.
  4. ``test_resolve_provider_kind_matches_documented_table`` — the routing rule.
  5. ``test_pages_only_import_from_state_facade`` — the DI layering rule.
"""

import importlib
import inspect
import pkgutil
import re
from pathlib import Path

import pytest

import agents as agents_pkg
from core.llm.router import resolve_provider_kind

# --- The documented provider table (CLAUDE.md "Privacy-Grenze") ------------------
# Cloud agents talk to a cloud LLM (Claude API or OpenRouter) → may only see public
# data. Local agents run on Ollama → may see everything. Non-LLM agents do pure
# computation (net-worth / market data) and never call any LLM.

from agents.capital_allocator_agent import CapitalAllocatorAgent
from agents.consensus_gap_agent import ConsensusGapAgent
from agents.devils_advocate_agent import DevilsAdvocateAgent
from agents.fundamental_analyzer_agent import FundamentalAnalyzerAgent
from agents.news_agent import NewsAgent
from agents.research_agent import ResearchAgent
from agents.search_agent import SearchAgent
from agents.sector_rotation_agent import SectorRotationAgent
from agents.storychecker_agent import StorycheckerAgent
from agents.structural_change_agent import StructuralChangeAgent

from agents.dividend_calendar_agent import DividendCalendarAgent
from agents.portfolio_agent import PortfolioAgent
from agents.portfolio_robustness_agent import PortfolioRobustnessAgent
from agents.portfolio_story_agent_v2 import PortfolioStoryAgentV2
from agents.rebalance_agent import RebalanceAgent
from agents.tax_loss_harvesting_agent import TaxLossHarvestingAgent
from agents.watchlist_checker_agent import WatchlistCheckerAgent

from agents.market_data_agent import MarketDataAgent
from agents.wealth_snapshot_agent import WealthSnapshotAgent

CLOUD_AGENTS = [
    CapitalAllocatorAgent,
    ConsensusGapAgent,
    DevilsAdvocateAgent,
    FundamentalAnalyzerAgent,
    NewsAgent,
    ResearchAgent,
    SearchAgent,
    SectorRotationAgent,
    StorycheckerAgent,
    StructuralChangeAgent,
]

LOCAL_AGENTS = [
    DividendCalendarAgent,
    PortfolioAgent,
    PortfolioRobustnessAgent,
    PortfolioStoryAgentV2,
    RebalanceAgent,
    TaxLossHarvestingAgent,
    WatchlistCheckerAgent,
]

# Agents that never call an LLM (pure computation: market data, net-worth snapshots).
NON_LLM_AGENTS = [
    MarketDataAgent,
    WealthSnapshotAgent,
]

# StorycheckerAgent is the documented privacy exception (CLAUDE.md §1, footnote):
# it deliberately sends position.name + position.story to the cloud to validate the
# investment thesis. A *new* exception must be added here consciously — which is the
# point: an accidental one fails the test below.
PRIVACY_EXCEPTIONS = {StorycheckerAgent}

# Matches a standalone ``Position`` token. Does NOT match ``PublicPosition`` (no word
# boundary after "Public") nor ``PositionsRepository`` / ``PositionAnalysesRepository``
# (no word boundary after "Position" because a letter follows).
_PRIVATE_POSITION_RE = re.compile(r"\bPosition\b")


def _annotation_str(annotation) -> str:
    """Normalise a parameter annotation to a string for both string- and class-form.

    16 of the agent modules use ``from __future__ import annotations`` (annotations are
    plain strings); the rest expose real classes. ``str()`` covers both, and typing
    generics like ``List[Position]`` stringify with the inner name intact.
    """
    return annotation if isinstance(annotation, str) else str(annotation)


def _public_methods(cls):
    """Public methods declared on the agent (skips dunders incl. ``__init__``)."""
    for name, member in inspect.getmembers(cls, predicate=inspect.isfunction):
        if not name.startswith("_"):
            yield name, member


def _all_agent_classes():
    """Every ``*Agent*`` class defined anywhere in the ``agents`` package.

    Walks the package (not the import list above) so a new agent in a new file is
    discovered even if nobody remembered to register it — that is the failing signal.
    """
    found = {}
    for modinfo in pkgutil.iter_modules(agents_pkg.__path__, agents_pkg.__name__ + "."):
        module = importlib.import_module(modinfo.name)
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if "Agent" in cls.__name__ and cls.__module__.startswith("agents."):
                found[cls] = cls.__name__
    return set(found)


def _llm_param_annotation(cls) -> str:
    """Stringified annotation of the ``__init__`` ``llm`` parameter ('' if none)."""
    try:
        sig = inspect.signature(cls.__init__)
    except (ValueError, TypeError):
        return ""
    param = sig.parameters.get("llm")
    if param is None or param.annotation is inspect.Parameter.empty:
        return ""
    return _annotation_str(param.annotation)


# --- Guard 1: classification completeness (the loop-closer) ----------------------

def test_every_agent_is_classified():
    """A new agent must be placed in exactly one provider bucket.

    This is what makes the privacy/routing guards reach future code: an unclassified
    agent fails here, forcing the author to choose cloud vs local — and a cloud choice
    then drags it through the privacy guard.
    """
    classified = set(CLOUD_AGENTS) | set(LOCAL_AGENTS) | set(NON_LLM_AGENTS)
    discovered = _all_agent_classes()

    unclassified = discovered - classified
    assert not unclassified, (
        "New agent(s) not classified in test_architecture_guards.py — add each to "
        "CLOUD_AGENTS, LOCAL_AGENTS, or NON_LLM_AGENTS (cloud agents are then held to "
        f"the privacy guard): {sorted(c.__name__ for c in unclassified)}"
    )

    # No double-counting and no stale entries pointing at deleted classes.
    stale = classified - discovered
    assert not stale, (
        "Registry lists agents that no longer exist in the agents package: "
        f"{sorted(c.__name__ for c in stale)}"
    )
    buckets = [CLOUD_AGENTS, LOCAL_AGENTS, NON_LLM_AGENTS]
    for cls in classified:
        in_n = sum(cls in b for b in buckets)
        assert in_n == 1, f"{cls.__name__} must be in exactly one bucket, found in {in_n}"


# --- Guard 2: privacy boundary (the critical invariant) --------------------------

@pytest.mark.parametrize("agent_cls", CLOUD_AGENTS, ids=lambda c: c.__name__)
def test_cloud_agents_never_accept_private_position(agent_cls):
    """Cloud agents may only take PublicPosition — never the encrypted Position."""
    if agent_cls in PRIVACY_EXCEPTIONS:
        pytest.skip(f"{agent_cls.__name__} is a documented privacy exception")

    offenders = []
    for method_name, method in _public_methods(agent_cls):
        sig = inspect.signature(method)
        for pname, param in sig.parameters.items():
            if param.annotation is inspect.Parameter.empty:
                continue
            if _PRIVATE_POSITION_RE.search(_annotation_str(param.annotation)):
                offenders.append(f"{method_name}({pname}: {_annotation_str(param.annotation)})")

    assert not offenders, (
        f"Cloud agent {agent_cls.__name__} accepts the encrypted Position (story/notes "
        f"leak to the cloud) — use PublicPosition instead: {offenders}"
    )


def test_storychecker_is_still_an_exception():
    """Self-check: the whitelisted exception must actually take Position.

    If StorycheckerAgent ever stops taking Position, drop it from PRIVACY_EXCEPTIONS so
    the whitelist can't silently mask a future real leak.
    """
    found = any(
        _PRIVATE_POSITION_RE.search(_annotation_str(p.annotation))
        for _, method in _public_methods(StorycheckerAgent)
        for p in inspect.signature(method).parameters.values()
        if p.annotation is not inspect.Parameter.empty
    )
    assert found, (
        "StorycheckerAgent no longer takes Position — remove it from PRIVACY_EXCEPTIONS "
        "so the whitelist does not hide a future leak."
    )


# --- Guard 3: classification matches the actual provider type --------------------

@pytest.mark.parametrize("agent_cls", CLOUD_AGENTS, ids=lambda c: c.__name__)
def test_cloud_agent_llm_is_not_ollama(agent_cls):
    """A cloud agent's llm must not be the local OllamaProvider (anti-misclassification)."""
    ann = _llm_param_annotation(agent_cls)
    assert "OllamaProvider" not in ann, (
        f"{agent_cls.__name__} is classified cloud but takes OllamaProvider — "
        "it is local; move it to LOCAL_AGENTS."
    )


@pytest.mark.parametrize(
    "agent_cls", LOCAL_AGENTS + NON_LLM_AGENTS, ids=lambda c: c.__name__
)
def test_local_agent_llm_is_not_cloud(agent_cls):
    """A local/non-LLM agent must not take a cloud provider — else it would dodge guard 2."""
    ann = _llm_param_annotation(agent_cls)
    assert "ClaudeProvider" not in ann and "OpenAICompatibleProvider" not in ann, (
        f"{agent_cls.__name__} is classified local but takes a cloud provider ({ann}) — "
        "move it to CLOUD_AGENTS so the privacy guard applies."
    )


# --- Guard 4: routing rule -------------------------------------------------------

@pytest.mark.parametrize(
    "model,has_anthropic,has_deepseek,has_openai_base,expected",
    [
        # Claude models route to Claude when the key is present.
        ("claude-opus-4-8", True, False, False, "claude"),
        ("claude-haiku-4-5-20251001", True, True, True, "claude"),
        # DeepSeek-direct only when no Claude match and DeepSeek key present.
        ("deepseek-chat", False, True, False, "deepseek"),
        # OpenAI-compatible (OpenRouter) catches everything else with a base url.
        ("mistralai/mistral-large-2512", False, False, True, "openai"),
        ("deepseek-chat", False, False, True, "openai"),
        # Fallback to Claude when no credentials match the model.
        ("claude-opus-4-8", False, False, False, "claude"),
        ("some-unknown-model", False, False, False, "claude"),
    ],
)
def test_resolve_provider_kind_matches_documented_table(
    model, has_anthropic, has_deepseek, has_openai_base, expected
):
    assert (
        resolve_provider_kind(
            model,
            has_anthropic=has_anthropic,
            has_deepseek=has_deepseek,
            has_openai_base=has_openai_base,
        )
        == expected
    )


# --- Guard 5: DI layering --------------------------------------------------------

_FORBIDDEN_PAGE_IMPORTS = re.compile(
    r"\b(?:import|from)\s+(state_agents|state_repos|state_db|state_services|state_llm)\b"
)


def test_pages_only_import_from_state_facade():
    """Pages import the singletons via the ``state`` facade, never the impl modules."""
    pages_dir = Path(__file__).resolve().parents[2] / "pages"
    offenders = []
    for page in sorted(pages_dir.glob("*.py")):
        text = page.read_text(encoding="utf-8")
        for m in _FORBIDDEN_PAGE_IMPORTS.finditer(text):
            offenders.append(f"{page.name}: imports {m.group(1)}")
    assert not offenders, (
        "Pages must import singletons from `state`, not the implementation modules: "
        f"{offenders}"
    )
