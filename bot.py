#!/usr/bin/env python3
"""Twitch Drops Telegram Bot — Entry Point.

Monitors Twitch Drops for games and notifies subscribed users via Telegram.
Uses SOLID architecture with dependency injection.

Usage:
    python bot.py

Requirements:
    TELEGRAM_BOT_TOKEN in .env (from @BotFather with /newbot)
"""

from dotenv import load_dotenv
load_dotenv()

import logging  # noqa: E402
import sys  # noqa: E402

from core.app import create_app  # noqa: E402

# Structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("twitch-drops-bot")


def main():
    """Wire dependencies and start the bot."""
    try:
        app = create_app()
    except RuntimeError as e:
        logger.error("%s", e)
        sys.exit(1)

    logger.info("Bot starting — press Ctrl+C to stop")
    app.run_polling()


if __name__ == "__main__":
    main()
