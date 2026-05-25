"""Polling scheduler with retry and circuit breaker.

Orchestrates source fetching, confidence scoring, and notification
dispatch. Injected with all dependencies via constructor.
"""

import logging
import time
from telegram.ext import ContextTypes
from state import StateManager
from engine import ConfidenceEngine
from health import HealthMonitor
from sources.base import BaseSource
from core.notifications import NotificationService
from config import ADMIN_CHAT_ID

logger = logging.getLogger("twitch-drops-bot.scheduler")


class SchedulerService:
    """Polls sources and dispatches notifications on a schedule."""

    MAX_RETRIES = 3
    RETRY_BACKOFF = 2  # seconds, exponential
    CIRCUIT_BREAKER_THRESHOLD = 5
    CIRCUIT_BREAKER_COOLDOWN = 300  # 5 minutes

    def __init__(
        self,
        state: StateManager,
        confidence_engine: ConfidenceEngine,
        health_monitor: HealthMonitor,
        sources: dict[str, BaseSource],
        notification_service: NotificationService,
        interval_minutes: int = 15,
    ):
        self.state = state
        self.confidence_engine = confidence_engine
        self.health_monitor = health_monitor
        self.sources = sources
        self.notifications = notification_service
        self.interval_minutes = interval_minutes
        self._circuit_open: dict[str, float] = {}  # source_name → cooldown_until

    async def poll(self, context: ContextTypes.DEFAULT_TYPE):
        """Main poll method — called by job_queue.

        Args:
            context: Telegram job context (provides bot via context.application.bot).
        """
        bot = context.application.bot
        logger.info("Polling %d sources...", len(self.sources))

        # 1. Fetch all sources (with retry + circuit breaker)
        all_campaigns = []
        for name, source in self.sources.items():
            campaigns = await self._fetch_with_retry(name, source)
            all_campaigns.extend(campaigns)

        # 2. Score and upsert
        scored = self.confidence_engine.score(all_campaigns)
        for campaign, confidence in scored:
            self.state.upsert_campaign(
                campaign_id=campaign.compute_id(),
                game=campaign.game,
                campaign_name=campaign.campaign_name,
                source=campaign.source,
                starts_at=campaign.starts_at,
                ends_at=campaign.ends_at,
                confidence=confidence,
            )

        # 3. Send stage-based notifications
        due = self.state.get_campaigns_needing_notification()
        total_sent = 0
        for campaign in due:
            stage = campaign["_next_stage"]
            sent = await self.notifications.send_stage_notification(
                bot, self.state, campaign, stage,
            )
            total_sent += sent
            self.state.advance_stage(campaign["id"], stage)

        # 4. Health alerts
        await self._send_health_alerts(bot)

        logger.info(
            "Poll done: %d campaigns scored, %d notifications sent",
            len(scored), total_sent,
        )

    async def _fetch_with_retry(
        self, name: str, source: BaseSource,
    ) -> list:
        """Fetch from a source with retry and circuit breaker."""
        now = time.time()

        # Circuit breaker check
        if name in self._circuit_open:
            if now < self._circuit_open[name]:
                logger.warning(
                    "Circuit breaker open for %s — skipping (cooldown %ds remaining)",
                    name, int(self._circuit_open[name] - now),
                )
                return []
            else:
                logger.info("Circuit breaker for %s closed — retrying", name)
                del self._circuit_open[name]

        # Retry with backoff
        last_error = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                campaigns = await source.fetch()
                await self.health_monitor.record_success(name)
                logger.debug(
                    "Source %s: %d campaigns (attempt %d)",
                    name, len(campaigns), attempt,
                )
                return campaigns
            except Exception as e:
                last_error = e
                wait = self.RETRY_BACKOFF ** attempt
                logger.warning(
                    "Source %s attempt %d/%d failed: %s (retry in %ds)",
                    name, attempt, self.MAX_RETRIES, e, wait,
                )
                if attempt < self.MAX_RETRIES:
                    import asyncio
                    await asyncio.sleep(wait)

        # All retries exhausted
        await self.health_monitor.record_failure(name, str(last_error))
        unhealthy = self.state.get_unhealthy_sources(
            self.CIRCUIT_BREAKER_THRESHOLD
        )
        for src in unhealthy:
            if src["source_name"] == name:
                self._circuit_open[name] = now + self.CIRCUIT_BREAKER_COOLDOWN
                logger.error(
                    "Circuit breaker OPEN for %s (cooldown %ds)",
                    name, self.CIRCUIT_BREAKER_COOLDOWN,
                )

        return []

    async def _send_health_alerts(self, bot):
        """Send health alerts for failing sources."""
        if not ADMIN_CHAT_ID:
            return

        try:
            admin_id = int(ADMIN_CHAT_ID)
        except ValueError:
            logger.warning("Invalid ADMIN_CHAT_ID: %s", ADMIN_CHAT_ID)
            return

        unhealthy = self.state.get_unhealthy_sources(3)
        for src in unhealthy:
            await self.notifications.send_health_alert(
                bot, admin_id,
                src["source_name"],
                src["consecutive_failures"],
                src.get("last_error", "unknown"),
            )
