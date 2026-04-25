"""
PortfolioService — centralized portfolio and position querying.

Replaces patterns across pages:
- Portfolio + Watchlist combination queries
- Portfolio context snapshot building
"""

from typing import List

from core.storage.positions import PositionsRepository
from core.storage.models import Position, PublicPosition


class PortfolioService:
    """Service for portfolio-level position queries and aggregations."""

    def __init__(self, positions_repo: PositionsRepository):
        self._positions = positions_repo

    def get_all_positions(
        self,
        include_portfolio: bool = True,
        include_watchlist: bool = False,
        require_story: bool = False,
        require_ticker: bool = False,
    ) -> List[Position]:
        """Get positions from portfolio and/or watchlist with optional filtering.

        Replaces scattered patterns like:
        ```python
        portfolio = positions_repo.get_portfolio()
        watchlist = positions_repo.get_watchlist()
        positions = portfolio + watchlist  # common pattern
        ```

        Args:
            include_portfolio: Include portfolio positions
            include_watchlist: Include watchlist positions
            require_story: Only return positions with investment story
            require_ticker: Only return positions with ticker symbol

        Returns:
            List of Position objects matching criteria
        """
        result = []
        if include_portfolio:
            result.extend(self._positions.get_portfolio())
        if include_watchlist:
            result.extend(self._positions.get_watchlist())

        if require_story:
            result = [p for p in result if p.story]
        if require_ticker:
            result = [p for p in result if p.ticker]

        return result

    def get_portfolio_positions(self) -> List[Position]:
        """Get all portfolio positions (convenience method)."""
        return self._positions.get_portfolio()

    def get_watchlist_positions(self) -> List[Position]:
        """Get all watchlist positions (convenience method)."""
        return self._positions.get_watchlist()

    def get_public_positions(
        self,
        include_portfolio: bool = True,
        include_watchlist: bool = True,
        require_story: bool = False,
        require_ticker: bool = False,
    ) -> List[PublicPosition]:
        """Get positions stripped of private data. Safe for cloud/public agents.

        Removes: quantity, purchase_price, notes, extra_data, in_portfolio, in_watchlist.
        Keeps: ticker, name, asset_class, story (investment thesis), isin, wkn, anlageart.

        Args:
            include_portfolio: Include portfolio positions
            include_watchlist: Include watchlist positions
            require_story: Only return positions with investment story
            require_ticker: Only return positions with ticker symbol

        Returns:
            List of PublicPosition objects (no private financial data)
        """
        positions = self.get_all_positions(
            include_portfolio=include_portfolio,
            include_watchlist=include_watchlist,
            require_story=require_story,
            require_ticker=require_ticker,
        )
        return [
            PublicPosition(
                id=p.id,
                name=p.name,
                ticker=p.ticker,
                isin=p.isin,
                asset_class=p.asset_class,
                anlageart=p.anlageart,
                story=p.story,
                story_skill=p.story_skill,
            )
            for p in positions
        ]
