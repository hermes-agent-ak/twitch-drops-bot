#!/usr/bin/env python3
"""Run one poll cycle and exit — for cron/systemd timer usage.

Unlike bot.py (which runs forever), this script:
1. Initializes all dependencies
2. Runs one poll cycle (fetch sources, score, notify)
3. Exits

Usage:
    python run_once.py

Environment:
    TELEGRAM_BOT_TOKEN in .env (from @BotFather)
"""

from dotenv import load_dotenv

load_dotenv()

import asyncio  # noqa: E402
import logging  # noqa: E402
import sys  # noqa: E402

from config import TELEGRAM_BOT_TOKEN  # noqa: E402
from state import StateManager  # noqa: E402
from engine import ConfidenceEngine  # noqa: E402
from health import HealthMonitor  # noqa: E402
from sources.facepunch import FacepunchScraper  # noqa: E402
from sources.steam_news import SteamNewsChecker  # noqa: E402
from core.notifications import NotificationService  # noqa: E402
from core.scheduler import SchedulerService  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("twitch-drops-bot.run_once")


async def main():
    """Run one poll cycle."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error(
            "TELEGRAM_BOT_TOKEN not set. "
            "Copy .env.example to .env and add your token."
        )
        sys.exit(1)

    logger.info("Starting daily drop check...")

    state = StateManager()
    confidence = ConfidenceEngine()
    health_monitor = HealthMonitor(state)
    notification_service = NotificationService()

    sources = {
        "facepunch": FacepunchScraper(),
        "steam_news": SteamNewsChecker(),
    }

    # Build a minimal scheduler for one-shot execution
    scheduler = SchedulerService(
        state=state,
        confidence_engine=confidence,
        health_monitor=health_monitor,
        sources=sources,
        notification_service=notification_service,
        interval_minutes=1440,
    )

    # We need a Telegram Bot to send notifications.
    # python-telegram-bot's Bot class can send messages without polling.
    from telegram import Bot

    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    # Create a fake context with bot attached
    class FakeApp:
        bot = bot

    class FakeContext:
        application = FakeApp()

    try:
        await scheduler.poll(FakeContext())
        logger.info("Daily check complete.")
    except Exception as e:
        logger.error("Daily check failed: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
