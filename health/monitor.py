"""Health monitoring for drop sources.

Tracks source reliability and alerts when sources fail repeatedly.
"""

import logging
from typing import Callable, Awaitable

from config import HEALTH_FAILURE_THRESHOLD
from state import StateManager

logger = logging.getLogger(__name__)


class HealthMonitor:
    """Monitors source health and triggers alerts."""

    def __init__(self, state: StateManager):
        self.state = state
        self._alert_callbacks: list[Callable[[str, str], Awaitable[None]]] = []

    def on_alert(self, callback: Callable[[str, str], Awaitable[None]]):
        """Register a callback for health alerts.
        
        Callback receives (source_name, message).
        """
        self._alert_callbacks.append(callback)

    async def record_success(self, source_name: str):
        """Record a successful source check."""
        self.state.record_success(source_name)
        logger.debug("Health OK: %s", source_name)

    async def record_failure(self, source_name: str, error: str):
        """Record a failed source check and alert if threshold reached."""
        self.state.record_failure(source_name, error)
        unhealthy = self.state.get_unhealthy_sources(HEALTH_FAILURE_THRESHOLD)

        for src in unhealthy:
            if src["source_name"] == source_name:
                msg = (
                    f"⚠️ Source Health Alert\n"
                    f"Source: {source_name}\n"
                    f"Consecutive failures: {src['consecutive_failures']}\n"
                    f"Last error: {src.get('last_error', 'unknown')}"
                )
                logger.warning("Health alert: %s", msg)
                for cb in self._alert_callbacks:
                    await cb(source_name, msg)

    async def check_all(self, sources: dict) -> dict[str, bool]:
        """Run health checks on all sources.
        
        Args:
            sources: dict of {source_name: source_instance}
            
        Returns:
            dict of {source_name: is_healthy}
        """
        results = {}
        for name, source in sources.items():
            try:
                healthy = await source.health_check()
                if healthy:
                    await self.record_success(name)
                else:
                    await self.record_failure(name, "health_check returned False")
                results[name] = healthy
            except Exception as e:
                await self.record_failure(name, str(e))
                results[name] = False
        return results
