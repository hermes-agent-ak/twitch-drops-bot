"""Application factory for the Twitch Drops Bot.

Creates a fully configured telegram.ext.Application with all
dependencies injected — no globals, no singletons.
"""

import logging
from telegram.ext import Application

from config import TELEGRAM_BOT_TOKEN, POLL_INTERVAL_MINUTES
from state import StateManager
from engine import ConfidenceEngine
from health import HealthMonitor
from sources.facepunch import FacepunchScraper
from sources.steam_news import SteamNewsChecker
from core.scheduler import SchedulerService
from core.notifications import NotificationService
from handlers import register_handlers

logger = logging.getLogger("twitch-drops-bot.app")


def create_app() -> Application:
    """Build and configure the bot application.

    Returns:
        Application: Fully wired telegram bot application.
    """
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN not set. "
            "Copy .env.example to .env and add your token from @BotFather. "
            "Or set TELEGRAM_TOKEN_RUST in your environment."
        )

    # --- Dependencies (Dependency Injection) ---
    state = StateManager()
    confidence = ConfidenceEngine()
    health_monitor = HealthMonitor(state)

    sources = {
        "facepunch": FacepunchScraper(),
        "steam_news": SteamNewsChecker(),
    }

    notification_service = NotificationService()

    scheduler = SchedulerService(
        state=state,
        confidence_engine=confidence,
        health_monitor=health_monitor,
        sources=sources,
        notification_service=notification_service,
        interval_minutes=POLL_INTERVAL_MINUTES,
    )

    # --- Build Application ---
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Store dependencies in bot_data for handlers to access
    app.bot_data["state"] = state
    app.bot_data["scheduler"] = scheduler
    app.bot_data["notification_service"] = notification_service

    # Register command handlers
    register_handlers(app)

    # Start scheduler via job_queue
    app.job_queue.run_repeating(
        scheduler.poll,
        interval=POLL_INTERVAL_MINUTES * 60,
        first=5,
    )
    logger.info(
        "Application built — scheduler every %d min, %d sources",
        POLL_INTERVAL_MINUTES, len(sources),
    )

    return app
