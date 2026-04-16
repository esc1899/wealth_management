"""
AnalysisService — centralized access to verdict analysis data.

Replaces repeated patterns across pages:
- get_latest_bulk() calls (5 pages doing this independently)
- Pre-flight coverage checks
"""

from typing import Dict, List, Optional

from core.storage.analyses import PositionAnalysesRepository
from core.storage.models import Position, PositionAnalysis


class AnalysisService:
    """Service for managing position analysis verdicts across agents."""

    def __init__(self, analyses_repo: PositionAnalysesRepository):
        self._analyses = analyses_repo

    def get_verdicts(
        self, position_ids: List[int], agent: str
    ) -> Dict[int, PositionAnalysis]:
        """Get verdicts for a list of positions from a specific agent.

        Args:
            position_ids: List of position IDs
            agent: Agent name (e.g., 'storychecker', 'consensus_gap', 'fundamental_analyzer')

        Returns:
            Dict mapping position_id to PositionAnalysis (missing positions not included)
        """
        return self._analyses.get_latest_bulk(position_ids, agent)

    def get_all_verdicts(
        self, position_ids: List[int]
    ) -> Dict[str, Dict[int, PositionAnalysis]]:
        """Get all verdicts for a list of positions — all 3 agents in one coordinated call.

        Replaces:
        ```python
        storychecker_verdicts = analyses_repo.get_latest_bulk(ids, "storychecker")
        consensus_verdicts = analyses_repo.get_latest_bulk(ids, "consensus_gap")
        fundamental_verdicts = analyses_repo.get_latest_bulk(ids, "fundamental_analyzer")
        ```

        Args:
            position_ids: List of position IDs

        Returns:
            Dict with keys ['storychecker', 'consensus_gap', 'fundamental_analyzer'],
            each mapping position_id to PositionAnalysis (missing positions not included)
        """
        return {
            "storychecker": self._analyses.get_latest_bulk(position_ids, "storychecker"),
            "consensus_gap": self._analyses.get_latest_bulk(position_ids, "consensus_gap"),
            "fundamental_analyzer": self._analyses.get_latest_bulk(position_ids, "fundamental_analyzer"),
        }

    def get_coverage(
        self, positions: List[Position], agents: List[str]
    ) -> Dict[str, int]:
        """Count positions missing analysis for each agent.

        Used for pre-flight status checks to determine if analysis is stale.

        Args:
            positions: List of Position objects
            agents: List of agent names to check

        Returns:
            Dict mapping agent name to count of positions without a verdict
        """
        ids = [p.id for p in positions]
        result = {}
        for agent in agents:
            verdicts = self._analyses.get_latest_bulk(ids, agent)
            missing_count = len([p for p in positions if p.id not in verdicts])
            result[agent] = missing_count
        return result

    def has_verdict(self, position_id: int, agent: str) -> bool:
        """Check if a position has a verdict from a specific agent."""
        verdicts = self._analyses.get_latest_bulk([position_id], agent)
        return position_id in verdicts

    def get_verdict(
        self, position_id: int, agent: str
    ) -> Optional[PositionAnalysis]:
        """Get verdict for a single position from a specific agent."""
        verdicts = self._analyses.get_latest_bulk([position_id], agent)
        return verdicts.get(position_id)
