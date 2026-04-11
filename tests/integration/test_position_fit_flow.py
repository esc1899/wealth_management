"""Test: Position Fit Flow (generate → save → load)"""
import asyncio
import pytest
from datetime import datetime, date
from core.storage.models import PortfolioStory, Position, PositionAnalysis
from agents.portfolio_story_agent import PortfolioStoryAgent


class MockLLM:
    """Mock LLM that returns parseable position fit output"""
    def __init__(self):
        self.skill_context = None
    
    async def complete(self, prompt, max_tokens=None):
        # Return response in expected format (TICKERS, not names!)
        return """MSFT: stärkt | Technologie-Leadership aligned mit Wachstum
BUNL: neutral | Stabilisierender Faktor"""


@pytest.mark.asyncio
async def test_analyze_positions_generates_fits():
    """Test that analyze_positions() generates position fit verdicts"""
    
    # Setup
    story = PortfolioStory(
        story="Wachstum über 10 Jahre",
        target_year=2035,
        liquidity_need=None,
        priority="Wachstum",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    
    # Create test positions
    positions = [
        Position(
            id=1,
            asset_class="Aktie", investment_type="stock",
            name="Microsoft", ticker="MSFT", unit="Stück",
            added_date=date.today()
        ),
        Position(
            id=2,
            asset_class="Anleihe", investment_type="bond",
            name="Bundesanleihe", ticker="BUNL", unit="Stück",
            added_date=date.today()
        ),
    ]
    
    # Empty verdicts dict
    verdicts = {1: {}, 2: {}}
    
    # Create agent with mock LLM
    agent = PortfolioStoryAgent(MockLLM(), None, None)
    
    # Run analyze_positions
    fits = await agent.analyze_positions(story, positions, verdicts)
    
    # Assertions
    assert fits is not None, "analyze_positions() should return a list"
    assert len(fits) == 2, f"Should parse 2 fits, got {len(fits)}"
    assert fits[0].position_id == 1
    assert fits[0].fit_verdict == "stärkt"
    assert fits[1].position_id == 2
    assert fits[1].fit_verdict == "neutral"

